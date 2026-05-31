"""
JSON API для React-дашборду. Усе під require_admin (cookie-сесія).
"""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Server, MetricsSnapshot, Alert, Command, PendingAlert
import security

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"],
                   dependencies=[Depends(security.require_admin)])

ONLINE_THRESHOLD = timedelta(minutes=5)


def _is_online(last_seen: datetime | None) -> bool:
    if not last_seen:
        return False
    return datetime.utcnow() - last_seen < ONLINE_THRESHOLD


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    """Картки всіх серверів зі зведеним станом."""
    servers = db.query(Server).all()
    snaps = {s.server_id: s.data for s in db.query(MetricsSnapshot).all()}

    result = []
    for s in servers:
        data = snaps.get(s.id, {}) or {}
        disks = [
            {
                "path": d.get("path"),
                "free_pct": d.get("free_pct"),
                "free_gb": d.get("free_gb"),
                "total_gb": d.get("total_gb"),
            }
            for d in data.get("disks", []) if "free_pct" in d
        ]
        services = [
            {"name": svc.get("name"), "running": svc.get("is_running")}
            for svc in data.get("services", [])
        ]
        result.append({
            "id": s.id,
            "name": s.name,
            "online": _is_online(s.last_seen),
            "last_seen": s.last_seen.isoformat() if s.last_seen else None,
            "cpu": data.get("cpu", {}).get("percent"),
            "ram": data.get("ram", {}).get("percent"),
            "ram_free_gb": data.get("ram", {}).get("free_gb"),
            "disks": disks,
            "services": services,
            "backup": {
                "status": data.get("status"),
                "file": data.get("latest_file"),
                "age_hours": data.get("latest_age_hours"),
                "size_mb": data.get("latest_size_mb"),
            },
            "reboot_required": data.get("reboot_required", False),
        })
    return result


@router.get("/servers/{server_id}")
def server_detail(server_id: str, db: Session = Depends(get_db)):
    s = db.query(Server).filter(Server.id == server_id).first()
    if not s:
        return {"error": "not found"}
    snap = db.query(MetricsSnapshot).filter(
        MetricsSnapshot.server_id == server_id
    ).first()

    alerts = (
        db.query(Alert)
        .filter(Alert.server_id == server_id)
        .order_by(Alert.sent_at.desc())
        .limit(20)
        .all()
    )
    commands = (
        db.query(Command)
        .filter(Command.server_id == server_id)
        .order_by(Command.created_at.desc())
        .limit(20)
        .all()
    )

    return {
        "id": s.id,
        "name": s.name,
        "online": _is_online(s.last_seen),
        "last_seen": s.last_seen.isoformat() if s.last_seen else None,
        "maintenance_until": s.maintenance_until.isoformat() if s.maintenance_until else None,
        "metrics": snap.data if snap else {},
        "recent_alerts": [
            {
                "severity": a.severity,
                "message": a.message,
                "sent_at": a.sent_at.isoformat() if a.sent_at else None,
            }
            for a in alerts
        ],
        "recent_commands": [
            {
                "action": c.action,
                "params": c.params,
                "status": c.status,
                "result": c.result,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "executed_at": c.executed_at.isoformat() if c.executed_at else None,
            }
            for c in commands
        ],
    }


@router.get("/alerts")
def recent_alerts(limit: int = 50, db: Session = Depends(get_db)):
    """Останні відправлені алерти + накопичені (pending)."""
    sent = (
        db.query(Alert)
        .order_by(Alert.sent_at.desc())
        .limit(limit)
        .all()
    )
    pending = db.query(PendingAlert).order_by(PendingAlert.updated_at.desc()).all()
    return {
        "sent": [
            {
                "id": a.id,
                "server_id": a.server_id,
                "alert_key": a.alert_key,
                "severity": a.severity,
                "message": a.message,
                "sent_at": a.sent_at.isoformat() if a.sent_at else None,
            }
            for a in sent
        ],
        "pending": [
            {
                "server_id": p.server_id,
                "alert_key": p.alert_key,
                "title": p.title,
                "body": p.body,
                "severity": p.severity,
                "count": p.count,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in pending
        ],
    }


@router.get("/commands")
def command_log(limit: int = 50, db: Session = Depends(get_db)):
    cmds = (
        db.query(Command)
        .order_by(Command.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": c.id,
            "server_id": c.server_id,
            "action": c.action,
            "params": c.params,
            "status": c.status,
            "result": c.result,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "executed_at": c.executed_at.isoformat() if c.executed_at else None,
        }
        for c in cmds
    ]
