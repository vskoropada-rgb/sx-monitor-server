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

import logging

from database import get_db
from models import Server, Metric, MetricsSnapshot, RdpLog
from auth import get_server
from config import settings

logger = logging.getLogger(__name__)

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
    # Persist attacker IPs first (updates the rolling 24h totals), then auto-block
    # so the 24h low-and-slow trigger sees this poll's fresh counts.
    # Спершу зберігаємо IP (оновлює лічильники за 24 год), потім автоблок —
    # щоб 24-годинний тригер бачив свіжі дані цього циклу.
    background.add_task(_track_brute_force, server.id, payload)
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

    # Burst candidates: high count within the current 10-min window. Merge both
    # fields the agent may populate (suspicious_ips + brute_force_alerts).
    # Кандидати-сплески: високий count у поточному 10-хв вікні (обидва поля).
    burst: dict = {}
    for entry in (payload.get("suspicious_ips") or []) + (payload.get("brute_force_alerts") or []):
        ip = (entry.get("ip") or "").strip()
        if not ip or entry.get("is_known_network"):
            continue
        cnt = entry.get("count", 0)
        prev = burst.get(ip)
        if prev is None or cnt > prev["count"]:
            burst[ip] = {"count": cnt, "usernames": entry.get("usernames") or []}

    threshold     = settings.auto_block_threshold
    threshold_24h = settings.auto_block_24h_threshold

    db = None
    try:
        from routers.commands import create_command
        from models import Command, BruteForceIp

        db = next(get_db())
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            return

        # Skip auto-actions while the server is in maintenance mode.
        # Не діємо, поки сервер у режимі обслуговування.
        if server.maintenance_until and server.maintenance_until > datetime.utcnow():
            return

        allow_nets      = settings.auto_block_networks
        already_blocked = set(payload.get("blocked_ips") or [])

        # Build the block list from two triggers, keyed by IP.
        # reason ∈ {"burst", "24h"} — щоб у сповіщенні пояснити причину.
        to_block: dict = {}

        # Trigger 1 — burst: more than the per-window threshold right now.
        # Тригер 1 — сплеск: понад поріг у поточному вікні.
        for ip, info in burst.items():
            if info["count"] > threshold:
                to_block[ip] = {"count": info["count"],
                                "usernames": info["usernames"], "reason": "burst"}

        # Trigger 2 — low-and-slow: cumulative 24h total over the threshold.
        # Тригер 2 — повільний перебір: сумарно за 24 год понад поріг.
        cutoff = datetime.utcnow() - timedelta(hours=24)
        slow = (
            db.query(BruteForceIp)
            .filter(BruteForceIp.server_id == server_id,
                    BruteForceIp.total_24h >= threshold_24h,   # ">=": "5 + pause + 5" = 10 trips it
                    BruteForceIp.last_seen >= cutoff)
            .all()
        )
        for r in slow:
            if r.ip not in to_block:
                to_block[r.ip] = {"count": r.total_24h,
                                  "usernames": r.usernames or [], "reason": "24h"}

        if not to_block:
            return
        logger.info("auto_block[%s]: to_block=%s", server_name,
                    {ip: (i["count"], i["reason"]) for ip, i in to_block.items()})

        for ip, info in to_block.items():
            try:
                ip_obj = ipaddress.ip_address(ip)
            except ValueError:
                continue

            # Never block private (RFC1918) or allowlisted addresses.
            # Ніколи не блокуємо приватні (RFC1918) чи allowlist-адреси.
            if ip_obj.is_private:
                logger.info("auto_block[%s]: %s is private — alert only", server_name, ip)
                continue
            if any(ip_obj in net for net in allow_nets):
                logger.info("auto_block[%s]: %s in allowlist — skip", server_name, ip)
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
            _notify_auto_block(server, ip, info["count"], info["usernames"], info["reason"])
            logger.info("auto_block[%s]: BLOCKED %s (%s, %d)",
                        server_name, ip, info["reason"], info["count"])

    except Exception as e:
        logger.error("auto_block error: %s", e)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def _flag_emoji(country_code: str) -> str:
    """Turn a 2-letter ISO country code into its flag emoji ('RU' → '🇷🇺').
    Перетворює 2-літерний ISO-код країни на емодзі прапора ('RU' → '🇷🇺')."""
    cc = (country_code or "").strip().upper()
    if len(cc) != 2 or not cc.isalpha():
        return ""
    return chr(0x1F1E6 + ord(cc[0]) - 65) + chr(0x1F1E6 + ord(cc[1]) - 65)


def _geoip_country(ip: str) -> str:
    """EN: Best-effort country for an IP → '🇷🇺 Russia', or '' on failure.
    UK: Best-effort країна за IP → '🇷🇺 Russia', або '' при невдачі.

    Only called when actually blocking (rare), so a per-lookup HTTP call to a
    free no-key geolocation service is fine. Two providers for redundancy.
    Викликається лише при блокуванні (рідко), тож HTTP-запит до безкоштовного
    сервісу без ключа прийнятний. Два провайдери для надійності.
    """
    import requests

    # Provider 1 — ipwho.is (HTTPS, no key).
    try:
        d = requests.get(f"https://ipwho.is/{ip}", timeout=6).json()
        if d.get("success"):
            return f"{_flag_emoji(d.get('country_code', ''))} {d.get('country', '')}".strip()
    except Exception:
        pass
    # Provider 2 — ip-api.com (fallback).
    try:
        d = requests.get(f"http://ip-api.com/json/{ip}",
                         params={"fields": "status,country,countryCode"}, timeout=6).json()
        if d.get("status") == "success":
            return f"{_flag_emoji(d.get('countryCode', ''))} {d.get('country', '')}".strip()
    except Exception:
        pass
    return ""


def _notify_auto_block(server, ip: str, count: int, usernames: list, reason: str = "burst"):
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
    # "24h" = low-and-slow (cumulative over a day); "burst" = a single window.
    # «24h» = повільний перебір за добу; «burst» = сплеск в одному вікні.
    detail = (f"{count} спроб за 24 год (повільний перебір)"
              if reason == "24h"
              else f"{count} невдалих спроб входу")
    # Country of the attacker IP (best-effort; omitted if lookup fails).
    # Країна атакуючого IP (best-effort; пропускається при невдачі).
    country = _geoip_country(ip)
    ip_line = f"IP <code>{ip}</code>" + (f" · {country}" if country else "")
    text = (
        f"🚫 <b>Автоблокування — {server.name}</b>\n"
        f"{ip_line}\n"
        f"Заблоковано назавжди після {detail}.\n"
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


def _track_brute_force(server_id: str, payload: dict):
    """EN: Persist external brute-force source IPs for the block-status audit.
    UK: Зберігає зовнішні IP-джерела перебору для аудиту статусу блокування.

    Merges suspicious_ips + brute_force_alerts, keeps external (non-private,
    non-known) IPs, and upserts each with peak attempt count + last_seen.
    Об'єднує suspicious_ips + brute_force_alerts, лишає зовнішні IP і
    оновлює кожен: пік спроб + last_seen.
    """
    import ipaddress
    from models import BruteForceIp

    entries: dict = {}
    for e in (payload.get("suspicious_ips") or []) + (payload.get("brute_force_alerts") or []):
        ip = (e.get("ip") or "").strip()
        if not ip or e.get("is_known_network"):
            continue
        try:
            if ipaddress.ip_address(ip).is_private:
                continue
        except ValueError:
            continue
        cur = entries.setdefault(ip, {"count": 0, "users": set()})
        cur["count"] = max(cur["count"], e.get("count", 0))
        cur["users"].update(e.get("usernames") or [])

    if not entries:
        return

    db = None
    try:
        db = next(get_db())
        now = datetime.utcnow()
        for ip, info in entries.items():
            new_count = info["count"]
            row = (db.query(BruteForceIp)
                   .filter(BruteForceIp.server_id == server_id, BruteForceIp.ip == ip)
                   .first())
            if row:
                # Reset the rolling 24h accumulator once the window ages out.
                # Скидаємо ковзний лічильник за 24 год, коли вікно застаріло.
                if not row.window_reset_at or (now - row.window_reset_at) > timedelta(hours=24):
                    row.total_24h = 0
                    row.last_window_count = 0
                    row.window_reset_at = now
                # Accumulate only the increase over the last reported window count,
                # so rolling 10-min reports of the same burst are not double-counted.
                # Додаємо лише приріст над попереднім count вікна — щоб ковзні
                # 10-хв звіти однієї серії не рахувались двічі.
                prev = row.last_window_count or 0
                if new_count > prev:
                    row.total_24h = (row.total_24h or 0) + (new_count - prev)
                row.last_window_count = new_count
                row.attempts = max(row.attempts or 0, new_count)
                row.last_seen = now
                merged = set(row.usernames or []) | info["users"]
                row.usernames = list(merged)[:10]
            else:
                db.add(BruteForceIp(
                    server_id=server_id, ip=ip,
                    attempts=new_count,
                    total_24h=new_count,
                    last_window_count=new_count,
                    window_reset_at=now,
                    usernames=list(info["users"])[:10],
                    first_seen=now, last_seen=now,
                ))
        db.commit()
    except Exception as e:
        if db is not None:
            db.rollback()
        logger.error("track_brute_force error: %s", e)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
