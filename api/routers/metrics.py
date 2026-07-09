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

    # Pair logon/logoff into user sessions with duration.
    # Парування вхід/вихід у сесії користувачів з тривалістю.
    _save_rdp_sessions(db, server.id,
                       payload.get("recent_logins", []),
                       payload.get("recent_logoffs", []))

    # Run alert analysis in the background so the agent is not blocked.
    # Аналіз і відправка алертів — у фоні щоб не блокувати агента.
    background.add_task(_analyze_and_alert, server.id, server.name, payload)
    # Auto-block brute-force IPs in the background as well.
    # Автоблок IP-перебірників — теж у фоні.
    background.add_task(_auto_block_suspicious, server.id, server.name, payload)

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


def _to_utc(time_str: str):
    """Parse an agent local-time string and normalise to naive UTC.
    Парсить локальний час агента і нормалізує до naive UTC."""
    try:
        return (datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                - timedelta(hours=settings.report_utc_offset))
    except (ValueError, TypeError):
        return None


def _save_rdp_sessions(db: Session, server_id: str, logins: list, logoffs: list):
    """Pair logon/logoff events by logon_id into RdpSession rows.
    Парує події вхід/вихід за logon_id у рядки RdpSession.

    Logon opens the session (idempotent by server_id+logon_id); logoff closes
    the matching open session and computes duration. Both are safe to replay:
    a repeated logon is ignored, a logoff for an already-closed or unknown
    session is skipped.
    Вхід відкриває сесію (ідемпотентно за server_id+logon_id); вихід закриває
    відповідну відкриту сесію й рахує тривалість. Обидва безпечні до повторів:
    повторний вхід ігнорується, вихід для вже закритої/невідомої сесії — пропуск.
    """
    from models import RdpSession

    # 1) Open sessions from logon events / Відкриваємо сесії з подій входу
    for entry in logins:
        logon_id = (entry.get("logon_id") or "").strip()
        logon_time = _to_utc(entry.get("time", ""))
        if not logon_id or logon_time is None:
            continue
        exists = (
            db.query(RdpSession)
            .filter(RdpSession.server_id == server_id,
                    RdpSession.logon_id == logon_id)
            .first()
        )
        if exists:
            continue
        try:
            db.add(RdpSession(
                server_id=server_id,
                logon_id=logon_id,
                username=entry.get("username", ""),
                ip=entry.get("ip", ""),
                logon_time=logon_time,
            ))
            db.commit()
        except Exception:
            db.rollback()   # concurrent duplicate — skip / паралельний дубль — пропуск

    # 2) Close sessions from logoff events / Закриваємо сесії з подій виходу
    for entry in logoffs:
        logon_id = (entry.get("logon_id") or "").strip()
        logoff_time = _to_utc(entry.get("time", ""))
        if not logon_id or logoff_time is None:
            continue
        row = (
            db.query(RdpSession)
            .filter(RdpSession.server_id == server_id,
                    RdpSession.logon_id == logon_id,
                    RdpSession.logoff_time.is_(None))
            .first()
        )
        if not row:
            continue  # no matching open RDP session — orphan logoff, skip
                      # немає відкритої RDP-сесії — «сирітський» вихід, пропуск
        # Guard against clock skew producing negative durations.
        # Захист від від'ємної тривалості через розбіжність годинника.
        dur = int((logoff_time - row.logon_time).total_seconds())
        row.logoff_time = logoff_time
        row.duration_sec = max(0, dur)
        try:
            db.commit()
        except Exception:
            db.rollback()


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


def _auto_block_suspicious(server_id: str, server_name: str, payload: dict):
    """EN: Automatically block external IPs that exceed the brute-force threshold.
    UK: Автоматично блокуємо зовнішні IP, що перевищили поріг перебору паролів.

    Safeguards / Запобіжники:
      - Private RFC1918 IPs are never blocked — only alerted (via analyzer).
        Приватні RFC1918 IP ніколи не блокуються — лише сповіщення (через analyzer).
      - Allowlisted IPs/CIDRs (office, VPN) are skipped.
        IP/CIDR з allowlist (офіс, VPN) пропускаються.
      - Already-blocked and in-flight IPs are deduplicated.
        Уже заблоковані та ті, що в черзі, дедуплікуються.
      - Blocks are permanent (no TTL) — admin can undo via the Telegram button.
        Блокування безстрокове — адмін може скасувати кнопкою в Telegram.
    """
    import ipaddress
    from config import settings

    if not settings.auto_block_enabled:
        return

    suspicious = payload.get("suspicious_ips") or []
    if not suspicious:
        return

    db = None
    try:
        from routers.commands import create_command
        from models import Command

        db = next(get_db())
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            return

        # Skip auto-actions while the server is in maintenance mode.
        # Не діємо, поки сервер у режимі обслуговування.
        if server.maintenance_until and server.maintenance_until > datetime.utcnow():
            return

        threshold       = settings.auto_block_threshold
        allow_nets      = settings.auto_block_networks
        already_blocked = set(payload.get("blocked_ips") or [])

        for entry in suspicious:
            ip    = (entry.get("ip") or "").strip()
            count = entry.get("count", 0)

            # Threshold is "more than N" — trigger strictly above it.
            # Поріг — «більше за N» — спрацьовуємо строго вище.
            if not ip or count <= threshold:
                continue

            try:
                ip_obj = ipaddress.ip_address(ip)
            except ValueError:
                continue

            # Never block private (RFC1918) or allowlisted addresses.
            # Ніколи не блокуємо приватні (RFC1918) чи allowlist-адреси.
            if ip_obj.is_private:
                continue
            if any(ip_obj in net for net in allow_nets):
                continue

            # Already blocked in the agent's firewall — nothing to do.
            # Уже заблоковано у firewall агента — нічого не робимо.
            if ip in already_blocked:
                continue

            # A block command is already queued/executing for this IP — dedup.
            # Команда блокування для цього IP вже в черзі/виконується — дедуп.
            inflight = (
                db.query(Command)
                .filter(
                    Command.server_id == server_id,
                    Command.action == "block_ip",
                    Command.status.in_(["pending", "executing"]),
                    Command.params["ip"].astext == ip,
                )
                .first()
            )
            if inflight:
                continue

            create_command(db, server_id, "block_ip", {"ip": ip})
            _notify_auto_block(server, ip, count, entry.get("usernames") or [])

    except Exception as e:
        import logging
        logging.getLogger(__name__).error("auto_block error: %s", e)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def _notify_auto_block(server, ip: str, count: int, usernames: list):
    """EN: Send a Telegram notice about an automatic block, with an unblock button.
    UK: Сповіщення в Telegram про автоблокування, з кнопкою розблокування."""
    import json
    import logging
    import requests
    from config import settings

    token = settings.tg_bot_token
    group = settings.tg_group_id
    if not token or not group:
        return

    users = ", ".join(usernames[:5]) if usernames else "—"
    text = (
        f"🚫 <b>Автоблокування — {server.name}</b>\n"
        f"IP <code>{ip}</code> заблоковано назавжди після {count} невдалих спроб входу.\n"
        f"Логіни: {users}"
    )
    keyboard = {"inline_keyboard": [[
        {"text": "🔓 Розблокувати", "callback_data": f"unblock_{ip}_{server.id}"}
    ]]}
    payload = {
        "chat_id":                  group,
        "text":                     text,
        "parse_mode":               "HTML",
        "disable_web_page_preview": True,
        "reply_markup":             json.dumps(keyboard),
    }
    if server.tg_topic_id:
        payload["message_thread_id"] = int(server.tg_topic_id)

    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json=payload, timeout=10)
    except Exception as e:
        logging.getLogger(__name__).error("notify_auto_block error: %s", e)
