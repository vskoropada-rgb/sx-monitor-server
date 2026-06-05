"""
POST /api/metrics — main ingestion endpoint: agent sends data every 60 seconds.
Stores numeric time-series, updates the metrics snapshot, persists RDP events,
and triggers async alert analysis.

POST /api/metrics — головний endpoint прийому метрик: агент надсилає дані кожну хвилину.
Зберігає числові ряди, оновлює snapshot метрик, зберігає RDP-події
і запускає фоновий аналіз алертів.
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from database import get_db
from models import Server, Metric, MetricsSnapshot, RdpLog
from auth import get_server
from config import settings

router = APIRouter(prefix="/api", tags=["metrics"])


@router.post("/metrics")
def receive_metrics(
    payload: dict,
    background: BackgroundTasks,
    server: Server = Depends(get_server),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()

    # Update last_seen and agent version / Оновлюємо last_seen і версію агента
    server.last_seen = now
    if payload.get("agent_version"):
        server.agent_version = payload["agent_version"]
    db.add(server)

    # Persist numeric time-series for Grafana charts.
    # Зберігаємо числові метрики для Grafana.
    _save_numeric_metrics(db, server.id, payload, now)

    # Upsert the latest snapshot used for fast bot status display.
    # Upsert останнього snapshot для швидкого відображення в боті.
    stmt = insert(MetricsSnapshot).values(
        server_id=server.id,
        data=payload,
        updated_at=now,
    ).on_conflict_do_update(
        index_elements=["server_id"],
        set_={"data": payload, "updated_at": now},
    )
    db.execute(stmt)
    db.commit()

    # Persist new RDP login events (duplicates filtered by UNIQUE constraint).
    # Зберігаємо нові RDP-входи (дублікати відфільтровуються UNIQUE constraint).
    _save_rdp_events(db, server.id, payload.get("recent_logins", []))

    # Run alert analysis in the background so the agent is not blocked.
    # Аналіз і відправка алертів — у фоні щоб не блокувати агента.
    background.add_task(_analyze_and_alert, server.id, server.name, payload)

    return {"ok": True}


def _save_rdp_events(db: Session, server_id: str, logins: list):
    """Persist RDP login events, converting agent local time to UTC.
    Зберігає RDP-події, конвертуючи локальний час агента в UTC."""
    for entry in logins:
        time_str = entry.get("time", "")
        if not time_str:
            continue
        try:
            # Agent sends local time; subtract offset to normalise to UTC for storage.
            # Агент надсилає локальний час; віднімаємо offset для нормалізації до UTC.
            event_time = (datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                          - timedelta(hours=settings.report_utc_offset))
        except ValueError:
            continue
        try:
            db.add(RdpLog(
                server_id=server_id,
                username=entry.get("username", ""),
                ip=entry.get("ip", ""),
                is_new_ip=1 if entry.get("is_new_ip") else 0,
                event_time=event_time,
            ))
            db.commit()
        except Exception:
            db.rollback()   # UNIQUE violation — duplicate event, skip / дублікат — пропускаємо


def _save_numeric_metrics(db: Session, server_id: str, payload: dict, now: datetime):
    """Extract and bulk-insert scalar metrics from the payload.
    Витягує та масово вставляє числові метрики з payload."""
    rows = []

    cpu = payload.get("cpu", {})
    if "percent" in cpu:
        rows.append(Metric(server_id=server_id, metric_name="cpu_percent",
                           value=cpu["percent"], recorded_at=now))

    ram = payload.get("ram", {})
    if "percent" in ram:
        rows.append(Metric(server_id=server_id, metric_name="ram_percent",
                           value=ram["percent"],
                           extra={"free_gb": ram.get("free_gb")},
                           recorded_at=now))

    for disk in payload.get("disks", []):
        if "free_pct" in disk:
            # Normalise the path to a metric name safe key.
            # Нормалізуємо шлях у ключ для назви метрики.
            path_key = disk["path"].rstrip("\\").replace(":", "").replace("\\", "_")
            rows.append(Metric(server_id=server_id,
                               metric_name=f"disk_free_{path_key}",
                               value=disk["free_pct"],
                               extra={"free_gb": disk.get("free_gb"),
                                      "total_gb": disk.get("total_gb")},
                               recorded_at=now))

    if payload.get("latest_size_bytes"):
        rows.append(Metric(server_id=server_id, metric_name="backup_size_mb",
                           value=payload["latest_size_bytes"] / 1e6,
                           recorded_at=now))

    if rows:
        db.bulk_save_objects(rows)


def _analyze_and_alert(server_id: str, server_name: str, payload: dict):
    """Background task: run the analyzer and send alerts or accumulate pending ones.
    Фоновий таск: запускає аналізатор і відправляє алерти або накопичує pending."""
    db = None
    try:
        import analyzer
        import notifier
        import storage_helpers as storage

        db = next(get_db())
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            return

        # Skip alert analysis during maintenance windows.
        # Пропускаємо аналіз у режимі обслуговування.
        if server.maintenance_until and server.maintenance_until > datetime.utcnow():
            return

        from config import settings
        config = {
            "SERVER_ID":              server.id,
            "COMPANY_NAME":           server.name,
            "TG_BOT_TOKEN":           settings.tg_bot_token,
            "TG_GROUP_ID":            settings.tg_group_id,
            "TG_TOPIC_ID":            server.tg_topic_id or "",
            "OPENAI_API_KEY":         settings.openai_api_key,
            "OPENAI_MODEL":           settings.openai_model,
            "ALERT_COOLDOWN_MIN":     str(settings.alert_cooldown_min),
            "DAILY_REPORT_HOUR":      str(settings.daily_report_hour),
            "REPORT_UTC_OFFSET":      str(settings.report_utc_offset),
            "DISK_WARNING_PERCENT":   str(settings.disk_warning_percent),
            "DISK_CRITICAL_PERCENT":  str(settings.disk_critical_percent),
            "CPU_WARNING_PERCENT":    str(settings.cpu_warning_percent),
            "RAM_WARNING_PERCENT":    str(settings.ram_warning_percent),
        }

        decision = analyzer.analyze(payload, config)

        # Daily report — checked on every metric push regardless of alert state.
        # Щоденний звіт — перевіряємо при кожному push незалежно від наявності алертів.
        utc_offset = int(config.get("REPORT_UTC_OFFSET", 0))
        now = datetime.utcnow() + timedelta(hours=utc_offset)
        if now.hour == int(config["DAILY_REPORT_HOUR"]) and now.minute < 2:
            if storage.can_send_alert(db, server_id, "daily_report", 22 * 60):
                pending = storage.get_pending_alerts(db, server_id)
                try:
                    import disk_forecast as _df
                    forecasts = _df.get_all_forecasts(db, server_id)
                except Exception:
                    forecasts = None
                notifier.send_daily_report(payload, config, pending_alerts=pending,
                                           forecasts=forecasts or None)
                storage.clear_pending_alerts(db, server_id)
                storage.record_alert(db, server_id, "daily_report", "report", "info", "sent")

        if not decision or not decision.get("should_alert"):
            return

        alert_key = decision.get("alert_key", "generic")
        severity  = decision.get("severity", "info")

        cooldown = int(config.get("ALERT_COOLDOWN_MIN", 30))
        if not storage.can_send_alert(db, server_id, alert_key, cooldown):
            return

        if severity == "critical":
            # Critical alerts fire immediately to Telegram.
            # Критичні алерти відправляємо одразу в Telegram.
            notifier.send_alert(decision, payload, config)
            storage.record_alert(db, server_id, alert_key,
                                 decision.get("tags", [""])[0], severity,
                                 decision.get("title", ""))
        else:
            # Non-critical alerts accumulate in the pending queue for the daily report.
            # Некритичні алерти накопичуються в pending-черзі для щоденного звіту.
            storage.add_pending_alert(db, server_id, alert_key,
                                      decision.get("title", "Подія"),
                                      decision.get("analysis", ""), severity)
            storage.record_alert(db, server_id, alert_key,
                                 decision.get("tags", [""])[0], severity,
                                 decision.get("title", ""))

    except Exception as e:
        import logging
        logging.getLogger(__name__).error("analyze_and_alert error: %s", e)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
