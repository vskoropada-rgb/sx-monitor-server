"""
PostgreSQL-backed alert storage helpers.
Alert cooldown, acknowledgement, pending queue, and record operations.

Хелпери для роботи з алертами в PostgreSQL.
Cooldown алертів, заглушення, черга pending і запис в лог.
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from models import Alert, PendingAlert


def can_send_alert(db: Session, server_id: str, alert_key: str, cooldown_min: int) -> bool:
    """Return True if the alert is not on cooldown and not snoozed.
    Повертає True якщо алерт не на cooldown і не заглушений."""
    row = (
        db.query(Alert)
        .filter(Alert.server_id == server_id, Alert.alert_key == alert_key)
        .order_by(Alert.sent_at.desc())
        .first()
    )
    if not row:
        return True
    if row.acked_until and row.acked_until > datetime.utcnow():
        return False   # snoozed by admin / заглушено адміном
    return datetime.utcnow() - row.sent_at > timedelta(minutes=cooldown_min)


def ack_alert(db: Session, server_id: str, alert_key: str, hours: int):
    """Snooze an alert for the specified number of hours.
    Заглушує алерт на вказану кількість годин."""
    row = (
        db.query(Alert)
        .filter(Alert.server_id == server_id, Alert.alert_key == alert_key)
        .order_by(Alert.sent_at.desc())
        .first()
    )
    until = datetime.utcnow() + timedelta(hours=hours)
    if row:
        row.acked_until = until
    else:
        # Create a placeholder row if the alert was never recorded (edge case).
        # Створюємо placeholder якщо алерт ніколи не записувався (крайній випадок).
        db.add(Alert(
            server_id=server_id,
            alert_key=alert_key,
            alert_type="ack",
            severity="info",
            message=f"acked for {hours}h",
            acked_until=until,
        ))
    db.commit()


def record_alert(db: Session, server_id: str, alert_key: str,
                 alert_type: str, severity: str, message: str):
    """Append an alert record (used for cooldown tracking and history).
    Додає запис алерту (для відстеження cooldown і історії)."""
    db.add(Alert(
        server_id=server_id,
        alert_key=alert_key,
        alert_type=alert_type,
        severity=severity,
        message=message,
    ))
    db.commit()


def add_pending_alert(db: Session, server_id: str, alert_key: str,
                      title: str, body: str, severity: str):
    """Upsert a pending (non-critical) alert, incrementing the occurrence count.
    Upsert pending (некритичного) алерту, збільшуючи лічильник повторень."""
    stmt = insert(PendingAlert).values(
        server_id=server_id,
        alert_key=alert_key,
        title=title,
        body=body or "",
        severity=severity,
    ).on_conflict_do_update(
        constraint="uq_pending_server_key",
        set_={
            "title":      title,
            "body":       body or "",
            "updated_at": datetime.utcnow(),
            "count":      PendingAlert.count + 1,
        },
    )
    db.execute(stmt)
    db.commit()


def get_pending_alerts(db: Session, server_id: str) -> list:
    """Return pending alerts ordered by severity (critical first).
    Повертає pending-алерти відсортовані за серйозністю (critical першими)."""
    sev_order = {"critical": 0, "warning": 1, "info": 2}
    rows = (
        db.query(PendingAlert)
        .filter(PendingAlert.server_id == server_id)
        .order_by(PendingAlert.added_at)
        .all()
    )
    result = [
        {"alert_key": r.alert_key, "title": r.title,
         "body": r.body, "severity": r.severity, "count": r.count}
        for r in rows
    ]
    result.sort(key=lambda x: sev_order.get(x["severity"], 2))
    return result


def clear_pending_alerts(db: Session, server_id: str):
    """Delete all pending alerts for a server (called after the daily report).
    Видаляє всі pending-алерти сервера (викликається після щоденного звіту)."""
    db.query(PendingAlert).filter(PendingAlert.server_id == server_id).delete()
    db.commit()
