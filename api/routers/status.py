"""
Статус серверів для Telegram бота і дашборду.
"""
import logging
import secrets as _secrets

import requests
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import security
from auth import hash_api_key
from config import settings
from database import get_db
from models import Server, MetricsSnapshot

logger = logging.getLogger("status")

router = APIRouter(prefix="/api", tags=["status"])


def _tg_post(method: str, payload: dict) -> dict:
    token = settings.tg_bot_token
    if not token:
        return {"ok": False}
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json=payload, timeout=10,
        )
        return r.json()
    except Exception as e:
        logger.error("%s виняток: %s", method, e)
        return {"ok": False}


def _create_forum_topic(name: str) -> str | None:
    """Створює Forum Topic і повертає message_thread_id або None."""
    group_id = settings.tg_group_id
    if not settings.tg_bot_token or not group_id:
        logger.warning("createForumTopic: TG_BOT_TOKEN/TG_GROUP_ID не задані")
        return None
    data = _tg_post("createForumTopic", {"chat_id": group_id, "name": name})
    if not data.get("ok"):
        logger.error("createForumTopic помилка: %s", data.get("description"))
        return None
    return str(data["result"]["message_thread_id"])


def _send_registration_message(name: str, topic_id: str, action: str):
    """Відправляє повідомлення в топік після реєстрації агента."""
    group_id = settings.tg_group_id
    if not settings.tg_bot_token or not group_id or not topic_id:
        return
    emoji = "🆕" if action == "created" else "🔄"
    text = f"{emoji} <b>{name}</b>\nАгент {'зареєстровано' if action == 'created' else 'оновлено'}. Моніторинг активний."
    data = _tg_post("sendMessage", {
        "chat_id": group_id,
        "message_thread_id": int(topic_id),
        "text": text,
        "parse_mode": "HTML",
    })
    if not data.get("ok"):
        logger.warning("sendMessage до топіку %s помилка: %s", topic_id, data.get("description"))



@router.get("/servers")
def list_servers(db: Session = Depends(get_db), _: int = Depends(security.require_admin)):
    servers = db.query(Server).all()
    return [
        {
            "id":        s.id,
            "name":      s.name,
            "last_seen": s.last_seen.isoformat() if s.last_seen else None,
        }
        for s in servers
    ]


@router.get("/status/{server_id}")
def server_status(server_id: str, db: Session = Depends(get_db), _: int = Depends(security.require_admin)):
    snap = db.query(MetricsSnapshot).filter(
        MetricsSnapshot.server_id == server_id
    ).first()
    if not snap:
        return {"error": "No data yet"}
    return snap.data


@router.get("/status")
def all_status(db: Session = Depends(get_db), _: int = Depends(security.require_admin)):
    snaps = db.query(MetricsSnapshot).all()
    return {s.server_id: s.data for s in snaps}


class RegisterPayload(BaseModel):
    server_id:   str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    api_key:     str = Field(min_length=32, max_length=128)
    name:        str | None = Field(default=None, max_length=128)
    tg_topic_id: str | None = Field(default=None, max_length=64)


@router.post("/servers/register")
def register_server(
    payload: RegisterPayload,
    x_register_secret: str = Header(default=""),
    db: Session = Depends(get_db),
):
    """
    Реєстрація нового агента. Захищено REGISTER_SECRET.

    Якщо tg_topic_id не передано — сервер сам створює Forum Topic у
    Telegram-групі під назвою компанії (бо токен бота лише на сервері).
    """
    if not settings.register_secret or not _secrets.compare_digest(
        x_register_secret, settings.register_secret
    ):
        raise HTTPException(status_code=403, detail="Invalid register secret")

    from models import Server as ServerModel
    name = payload.name or payload.server_id

    existing = db.query(ServerModel).filter(
        ServerModel.id == payload.server_id
    ).first()

    if existing:
        existing.name = name
        if not existing.tg_topic_id:
            existing.tg_topic_id = _create_forum_topic(existing.name)
        db.commit()
        _send_registration_message(existing.name, existing.tg_topic_id, "updated")
        return {"ok": True, "action": "updated", "tg_topic_id": existing.tg_topic_id}

    # Нова реєстрація — сервер завжди сам створює топік
    topic_id = _create_forum_topic(name)

    server = ServerModel(
        id=payload.server_id,
        name=name,
        api_key=hash_api_key(payload.api_key),
        tg_topic_id=topic_id,
    )
    db.add(server)
    db.commit()
    _send_registration_message(name, topic_id, "created")
    return {"ok": True, "action": "created", "tg_topic_id": topic_id}
