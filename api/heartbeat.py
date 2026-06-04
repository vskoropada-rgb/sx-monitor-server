"""
heartbeat.py — перевіряє last_seen кожного сервера, шле алерт офлайн/відновлення.
Також записує UptimeEvent при кожній зміні стану (для SLA-розрахунків).
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

import storage_helpers as storage
from config import settings
from models import Server, ServerHeartbeat, UptimeEvent

logger = logging.getLogger(__name__)

OFFLINE_AFTER_MIN = 5   # сервер вважається офлайн якщо мовчить >5хв


def check_heartbeats(db: Session, config_by_server: dict):
    """
    config_by_server: {server_id: config_dict} з TG_BOT_TOKEN, TG_GROUP_ID,
    TG_TOPIC_ID тощо. Викликати з циклу бота раз на хвилину.
    """
    import notifier
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=OFFLINE_AFTER_MIN)

    servers = db.query(Server).all()
    for server in servers:
        if server.maintenance_until and server.maintenance_until > now:
            continue

        is_online = bool(server.last_seen and server.last_seen >= cutoff)

        # отримуємо / створюємо heartbeat-запис
        hb = db.query(ServerHeartbeat).filter(
            ServerHeartbeat.server_id == server.id
        ).first()
        if not hb:
            hb = ServerHeartbeat(
                server_id=server.id,
                online=1 if is_online else 0,
                changed_at=now,
            )
            db.add(hb)
            db.commit()
            continue

        was_online = bool(hb.online)

        if was_online and not is_online:
            # Перехід online → offline
            hb.online = 0
            hb.changed_at = now
            db.add(UptimeEvent(server_id=server.id, event="offline", at=now))
            db.commit()
            cfg = config_by_server.get(server.id, {})
            if cfg and storage.can_send_alert(db, server.id, "heartbeat_offline", 30):
                if server.last_seen:
                    local_dt = server.last_seen + timedelta(hours=settings.report_utc_offset)
                    last_seen_str = local_dt.strftime("%H:%M")
                else:
                    last_seen_str = "невідомо"
                notifier.send_message(
                    f"🔴 <b>{server.name}</b> — агент не відповідає\n"
                    f"Останній зв'язок: {last_seen_str}\n"
                    f"Можливо, сервер недоступний або агент зупинено.",
                    cfg,
                    {"inline_keyboard": [[
                        {"text": "📊 Статус",
                         "callback_data": f"status_{server.id}"},
                    ]]},
                )
                storage.record_alert(
                    db, server.id, "heartbeat_offline", "heartbeat", "critical",
                    f"offline since {last_seen_str} (local)",
                )

        elif not was_online and is_online:
            # Перехід offline → online (відновлення)
            offline_since = hb.changed_at
            downtime_min = int((now - offline_since).total_seconds() / 60)
            hb.online = 1
            hb.changed_at = now
            db.add(UptimeEvent(server_id=server.id, event="online", at=now))
            db.commit()
            cfg = config_by_server.get(server.id, {})
            if cfg and storage.can_send_alert(db, server.id, "heartbeat_online", 5):
                notifier.send_message(
                    f"🟢 <b>{server.name}</b> — агент відновлено\n"
                    f"Простій: {downtime_min} хв",
                    cfg,
                )
                storage.record_alert(
                    db, server.id, "heartbeat_online", "heartbeat", "info",
                    f"recovered after {downtime_min}m",
                )
