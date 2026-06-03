"""
routers/idrac.py — Redfish Event Service receiver for Dell iDRAC 9.

iDRAC надсилає HTTP POST на /api/idrac/{source_id}/event при кожному
hardware event (диск, PSU, пам'ять, температура тощо).
Аутентифікація — заголовок X-Idrac-Secret (хешується SHA-256).
"""
import hashlib
import hmac
import logging
import uuid
from datetime import datetime
from typing import List, Optional

import requests as http
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Alert, IdracSource, Server
from security import require_admin

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Severity mapping ────────────────────────────────────────────────────────

_SEVERITY: dict[str, str] = {
    "Critical": "critical",
    "Warning":  "warning",
    "OK":       "ok",
}

# ── Hardware category icons based on MessageId prefix ────────────────────────

_ICONS: dict[str, str] = {
    "STOR": "💾", "RAID": "💾",
    "MEM":  "🧠",
    "PSU":  "🔌",
    "FAN":  "🌀",
    "THER": "🌡️",
    "CPU":  "⚙️",
    "PWR":  "🔋",
    "BIOS": "🖥️",
    "PROC": "⚙️",
}


def _icon(msg_id: str) -> str:
    for prefix, icon in _ICONS.items():
        if msg_id.upper().startswith(prefix):
            return icon
    return "🖥️"


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _tg_send(server: Server, severity: str, text: str) -> None:
    """Надіслати повідомлення в Telegram-топік сервера напряму через Bot API."""
    try:
        token = settings.tg_bot_token
        group = settings.tg_group_id
        if not token or not group:
            return
        payload: dict = {
            "chat_id": group,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if server.tg_topic_id:
            payload["message_thread_id"] = int(server.tg_topic_id)
        http.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload,
            timeout=10,
        )
    except Exception as exc:
        logger.error("Telegram iDRAC send error: %s", exc)


# ── Redfish payload schema ───────────────────────────────────────────────────

class RedfishEvent(BaseModel):
    EventType:        Optional[str] = None
    EventId:          Optional[str] = None
    Severity:         Optional[str] = None
    MessageSeverity:  Optional[str] = None
    Message:          Optional[str] = None
    MessageId:        Optional[str] = None
    MessageArgs:      Optional[List] = None
    EventTimestamp:   Optional[str] = None
    OriginOfCondition: Optional[dict] = None


class RedfishPayload(BaseModel):
    Context: Optional[str] = None
    Events:  List[RedfishEvent] = []


# ── Event receiver ───────────────────────────────────────────────────────────

@router.post("/api/idrac/{source_id}/event")
def receive_event(
    source_id: str,
    body: RedfishPayload,
    x_idrac_secret: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Endpoint для Redfish Event Service subscription.
    iDRAC 9 надсилає сюди POST при hardware alerts.
    Повертає 200 OK завжди (навіть при skip), щоб iDRAC не ретраїв нескінченно.
    """
    source = db.query(IdracSource).filter(IdracSource.id == source_id).first()
    if not source:
        # Повертаємо 200 щоб iDRAC не ретраїв — але нічого не робимо
        logger.warning("iDRAC event for unknown source_id=%s", source_id)
        return {"ok": False, "reason": "unknown_source"}

    provided = x_idrac_secret or ""
    if not hmac.compare_digest(_hash(provided), source.secret_hash):
        logger.warning("iDRAC event auth failure for source=%s", source_id)
        raise HTTPException(status_code=403, detail="Invalid secret")

    server = db.query(Server).filter(Server.id == source.server_id).first()
    if not server:
        return {"ok": False, "reason": "server_not_found"}

    processed = 0
    for ev in body.Events:
        # Визначаємо severity
        raw_sev = ev.MessageSeverity or ev.Severity or "Warning"
        severity = _SEVERITY.get(raw_sev, "warning")

        # OK-події ігноруємо (iDRAC шле "OK" при відновленні — не потрібні алерти)
        if severity == "ok":
            continue

        msg_id    = ev.MessageId or ""
        message   = ev.Message or "Hardware event"
        icon      = _icon(msg_id)
        ts_suffix = ""

        if ev.EventTimestamp:
            try:
                dt = datetime.fromisoformat(ev.EventTimestamp.replace("Z", "+00:00"))
                ts_suffix = f" [{dt.strftime('%d.%m %H:%M')}]"
            except Exception:
                pass

        alert_key = f"idrac:{source_id}:{msg_id}:{ev.EventId or ''}"
        full_msg  = f"{icon} {message}{ts_suffix}"

        # Запис в Alert
        db.add(Alert(
            server_id=server.id,
            alert_key=alert_key,
            alert_type="idrac",
            severity=severity,
            message=full_msg,
            sent_at=datetime.utcnow(),
        ))

        # Telegram
        sev_icon = "🔴" if severity == "critical" else "🟡"
        tg_text = (
            f"{sev_icon} <b>iDRAC — {server.name}</b>\n"
            f"{full_msg}\n"
            f"<i>{source.name}</i>"
        )
        _tg_send(server, severity, tg_text)

        logger.info(
            "iDRAC [%s] server=%s msg_id=%s: %s",
            severity, server.name, msg_id, message,
        )
        processed += 1

    db.commit()
    return {"ok": True, "processed": processed}


# ── Dashboard: керування джерелами (потребує авторизації адміна) ─────────────

class SourceCreate(BaseModel):
    server_id: str
    name:      str
    secret:    str  # plaintext — зберігається як SHA-256


@router.get("/api/dashboard/idrac/sources")
def list_sources(
    db: Session = Depends(get_db),
    _: int = Depends(require_admin),
):
    rows = db.query(IdracSource).order_by(IdracSource.created_at.desc()).all()
    return [
        {
            "id":         r.id,
            "server_id":  r.server_id,
            "name":       r.name,
            "created_at": r.created_at.isoformat(),
            "event_url":  f"/api/idrac/{r.id}/event",
        }
        for r in rows
    ]


@router.post("/api/dashboard/idrac/sources", status_code=201)
def create_source(
    body: SourceCreate,
    db: Session = Depends(get_db),
    _: int = Depends(require_admin),
):
    server = db.query(Server).filter(Server.id == body.server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    if len(body.secret) < 16:
        raise HTTPException(status_code=422, detail="Secret must be ≥ 16 characters")

    source = IdracSource(
        id=str(uuid.uuid4()),
        server_id=body.server_id,
        name=body.name,
        secret_hash=_hash(body.secret),
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    logger.info("Created iDRAC source id=%s server=%s", source.id, server.name)
    return {
        "id":         source.id,
        "server_id":  source.server_id,
        "name":       source.name,
        "created_at": source.created_at.isoformat(),
        "event_url":  f"/api/idrac/{source.id}/event",
    }


@router.delete("/api/dashboard/idrac/sources/{source_id}", status_code=204)
def delete_source(
    source_id: str,
    db: Session = Depends(get_db),
    _: int = Depends(require_admin),
):
    source = db.query(IdracSource).filter(IdracSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    db.delete(source)
    db.commit()
