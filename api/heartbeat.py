"""
Heartbeat monitor — checks each server's last_seen and fires offline/recovery alerts.
Also writes UptimeEvent records on every state transition for SLA calculations.

Монітор heartbeat — перевіряє last_seen кожного сервера і шле алерти офлайн/відновлення.
Також записує UptimeEvent при кожній зміні стану (для SLA-розрахунків).
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

import storage_helpers as storage
from config import settings
from models import Server, ServerHeartbeat, UptimeEvent

logger = logging.getLogger(__name__)

# Server is considered offline if silent for more than this many minutes.
# Сервер вважається офлайн якщо мовчить більше цієї кількості хвилин.
OFFLINE_AFTER_MIN = 5


def check_heartbeats(db: Session, config_by_server: dict):
    """
    Check all servers and fire alerts on state transitions.
    Перевіряє всі сервери і надсилає алерти при зміні стану.

    config_by_server: {server_id: config_dict} with TG_BOT_TOKEN, TG_GROUP_ID,
    TG_TOPIC_ID etc. Call from the bot's run() loop once per minute.
    config_by_server: {server_id: config_dict} з TG_BOT_TOKEN, TG_GROUP_ID,
    TG_TOPIC_ID тощо. Викликати з циклу бота раз на хвилину.
    """
    import notifier
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=OFFLINE_AFTER_MIN)

    servers = db.query(Server).all()
    for server in servers:
        # Skip servers in maintenance mode — no offline alerts during planned downtime.
        # Пропускаємо сервери в режимі обслуговування — немає офлайн-алертів.
        if server.maintenance_until and server.maintenance_until > now:
            continue

        is_online = bool(server.last_seen and server.last_seen >= cutoff)

        # Get or create the heartbeat record for this server.
        # Отримуємо або створюємо heartbeat-запис для цього сервера.
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
            # Transition: online → offline / Перехід: online → offline
            hb.online = 0
            hb.changed_at = now
            db.add(UptimeEvent(server_id=server.id, event="offline", at=now))
            db.commit()
            cfg = config_by_server.get(server.id, {})
            if cfg and storage.can_send_alert(db, server.id, "heartbeat_offline", 30):
                if server.last_seen:
                    # Convert UTC last_seen to local display time.
                    # Конвертуємо UTC last_seen у локальний час для відображення.
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
            # Transition: offline → online (recovery) / Перехід: offline → online (відновлення)
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
