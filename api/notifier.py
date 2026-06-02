"""
notifier.py — відправка повідомлень в Telegram.
Перенесений з SX_Monitoring, без змін у логіці.
"""
import json
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

SEVERITY_ICONS = {"critical": "🔴", "warning": "⚠️", "info": "ℹ️"}


def send_alert(decision: dict, metrics: dict, config: dict) -> bool:
    icon    = SEVERITY_ICONS.get(decision.get("severity", "info"), "ℹ️")
    title   = decision.get("title", "Подія на сервері")
    tags    = decision.get("tags", [])
    analysis = decision.get("analysis", "")
    now     = datetime.now().strftime("%H:%M")

    lines = [f"{icon} <b>{title}</b>  {now}"]
    if analysis:
        lines.append(analysis)

    raw_suspects = metrics.get("brute_force_alerts") or metrics.get("suspicious_ips") or []
    for entry in [e for e in raw_suspects if e.get("ip")][:3]:
        ip  = entry["ip"]
        geo = _ip_geo(ip)
        geo_str = f" [{geo}]" if geo else ""
        lines.append(f"🔑 {ip}{geo_str} — {entry['count']} спроб")

    if "#new_ip" in tags:
        for login in metrics.get("new_ip_alerts", [])[:3]:
            lines.append(f"🖥 {login['ip']} → {login['username']} ({login.get('time','')})")

    if "#admin" in tags:
        for a in metrics.get("new_admins", [])[:3]:
            lines.append(f"👤 {a['username']} доданий ким: {a['added_by']}")

    if "#usb" in tags:
        for d in metrics.get("new_usb_devices", [])[:3]:
            lines.append(f"🔌 {d.get('name', d.get('instance_id', '?'))}")

    if "#files" in tags:
        for f in metrics.get("changed_files", [])[:3]:
            lines.append(f"📄 {f['path']} ({f.get('modified','')})")

    if "#schtask" in tags:
        for t in metrics.get("new_scheduled_tasks", [])[:3]:
            lines.append(f"⏰ {t.get('name','?')}")

    if "#software" in tags:
        for s in metrics.get("new_software", [])[:3]:
            lines.append(f"📦 {s.get('name','?')}")

    is_security = any(t in tags for t in (
        "#brute_force", "#new_ip", "#admin", "#files", "#usb", "#schtask", "#software"
    ))
    if not is_security:
        block = _metrics_block(metrics)
        if block:
            lines.append(block)

    keyboard = _build_keyboard(decision, config, metrics)
    return _send_message(config, "\n".join(lines), keyboard)


def send_daily_report(metrics: dict, config: dict, pending_alerts: list = None,
                      forecasts: list = None) -> bool:
    company = config.get("COMPANY_NAME", config.get("SERVER_ID", "Server"))
    now     = datetime.now()

    disk_lines = []
    for d in metrics.get("disks", []):
        if "free_pct" in d:
            icon = "🔴" if d["free_pct"] < 10 else "⚠️" if d["free_pct"] < 20 else "✅"
            disk_lines.append(f"  {icon} {d['path']}: {d['free_pct']}% ({d['free_gb']} GB)")

    cpu = metrics.get("cpu", {}).get("percent", "?")
    ram = metrics.get("ram", {}).get("percent", "?")

    b_status = metrics.get("status", "")
    b_icon   = "🔴" if b_status == "critical" else "⚠️" if b_status == "warning" else "✅"
    b_line   = (f"{b_icon} {metrics.get('latest_file', 'н/д')}  "
                f"{metrics.get('latest_size_mb', '?')} MB  "
                f"{metrics.get('latest_age_hours', '?')}г тому")

    reboot_line = ("⚠️ Очікує перезавантаження!"
                   if metrics.get("reboot_required")
                   else "✅ Перезавантаження не потрібне")

    lines = [
        f"📊 <b>Щоденний звіт — {company}</b>",
        f"📅 {now.strftime('%d.%m.%Y %H:%M')}",
        "",
        "💾 <b>Диски:</b>",
        *disk_lines,
        "",
        f"🖥 CPU: <b>{cpu}%</b>  |  RAM: <b>{ram}%</b>",
        "",
        f"📦 <b>Бекап:</b>  {b_line}",
        "",
        f"🔄 {reboot_line}",
    ]

    if metrics.get("issues"):
        lines += ["", "⚠️ <b>Проблеми:</b>"] + [f"  • {i}" for i in metrics["issues"]]

    if pending_alerts:
        lines += ["", "📋 <b>Накопичені сповіщення за добу:</b>"]
        for p in pending_alerts:
            sev_icon   = SEVERITY_ICONS.get(p.get("severity", "warning"), "⚠️")
            count_str  = f" (×{p['count']})" if p.get("count", 1) > 1 else ""
            lines.append(f"  {sev_icon} {p['title']}{count_str}")
            body = (p.get("body") or "").strip()
            if body:
                lines.append(f"     <i>{body}</i>")

    if forecasts:
        lines += ["", "🔮 <b>Прогноз дисків:</b>"]
        for fc in forecasts:
            path_key = fc.get("path_key", "?")
            current_pct = fc.get("current_pct", "?")
            eta_hours = fc.get("eta_hours")
            eta_str = fc.get("eta_str")
            if eta_hours is not None and eta_str:
                lines.append(f"  ⏳ {path_key}: {current_pct}% вільно, заповниться через ~{eta_str}")
            else:
                lines.append(f"  ✅ {path_key}: {current_pct}% вільно, стабільно")

    return _send_message(config, "\n".join(lines))


def send_sla_report(db, config_by_server: dict, servers: list,
                    week_start: datetime, week_end: datetime) -> None:
    """Надсилає щотижневий SLA-звіт для кожного сервера у відповідний топік."""
    import sla as _sla
    for server in servers:
        cfg = config_by_server.get(server.id)
        if not cfg:
            continue
        try:
            result = _sla.compute_sla(db, server.id, week_start, week_end)
            uptime = result.get("uptime_pct", 100.0)
            downtime_min = result.get("downtime_min", 0)
            incidents = result.get("incidents", [])

            icon = "✅" if uptime >= 99.9 else "⚠️" if uptime >= 99.0 else "🔴"
            lines = [
                f"📈 <b>SLA звіт — {server.name}</b>",
                f"📅 {week_start.strftime('%d.%m')} — {week_end.strftime('%d.%m.%Y')}",
                "",
                f"{icon} Uptime: <b>{uptime}%</b>",
                f"⏱ Простій: {downtime_min} хв",
            ]
            if incidents:
                lines += ["", "📋 <b>Інциденти:</b>"]
                for inc in incidents[:5]:
                    lines.append(
                        f"  • {inc['from'][:16]} — {inc['to'][11:16]} "
                        f"({inc['duration_min']} хв)"
                    )
                if len(incidents) > 5:
                    lines.append(f"  ... ще {len(incidents) - 5} інцидентів")
            _send_message(cfg, "\n".join(lines))
        except Exception as e:
            logger.error("SLA report error for %s: %s", server.id, e)


def send_message(text: str, config: dict, keyboard=None) -> bool:
    return _send_message(config, text, keyboard)


def _metrics_block(metrics: dict) -> str:
    parts = []
    for d in metrics.get("disks", []):
        if "free_pct" in d:
            delta = f" ↓{abs(d['delta_1h']):.1f}%/г" if d.get("delta_1h", 0) < 0 else ""
            parts.append(f"💾 {d['path']} {d['free_pct']}% ({d['free_gb']}GB){delta}")
    if "cpu" in metrics:
        parts.append(f"CPU {metrics['cpu']['percent']}% · RAM {metrics['ram']['percent']}%")
    stopped = [s["name"] for s in metrics.get("services", []) if not s["is_running"]]
    if stopped:
        parts.append("❌ " + ", ".join(stopped))
    return "\n".join(parts)


def _ip_geo(ip: str) -> str:
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=country,city,status", timeout=2)
        d = r.json()
        if d.get("status") == "success":
            return ", ".join(p for p in [d.get("country", ""), d.get("city", "")] if p)
    except Exception:
        pass
    return ""


def _build_keyboard(decision: dict, config: dict, metrics: dict = None) -> dict:
    tags      = decision.get("tags", [])
    server_id = config.get("SERVER_ID", "server")
    metrics   = metrics or {}

    row1 = [
        {"text": "📊 Статус", "callback_data": f"status_{server_id}"},
        {"text": "👥 Сесії",  "callback_data": f"sessions_{server_id}"},
    ]
    row2 = []

    if "#service" in tags:
        row2.append({"text": "🔄 Перезапустити", "callback_data": f"restart_service_{server_id}"})
    if "#rdp" in tags or "#new_ip" in tags:
        row2.append({"text": "🔒 Завершити сесію", "callback_data": f"kill_session_{server_id}"})
    if "#disk" in tags:
        row2.append({"text": "💾 Деталі диску", "callback_data": f"disk_{server_id}"})

    block_ips = []
    if "#brute_force" in tags or "#new_ip" in tags or "#security" in tags:
        for a in metrics.get("brute_force_alerts", [])[:3]:
            if a.get("ip"):
                block_ips.append(a["ip"])
        if not block_ips:
            for a in metrics.get("new_ip_alerts", [])[:2]:
                block_ips.append(a["ip"])
    for ip in block_ips:
        row2.append({"text": f"🚫 {ip}", "callback_data": f"block_confirm_{ip}_{server_id}"})

    buttons = [row1]
    if row2:
        for i in range(0, len(row2), 2):
            buttons.append(row2[i:i+2])

    alert_key = decision.get("alert_key", "generic")
    buttons.append([
        {"text": "✅ Зрозуміло (6г)", "callback_data": f"ack|{server_id}|6|{alert_key}"},
        {"text": "✅ Зрозуміло (24г)", "callback_data": f"ack|{server_id}|24|{alert_key}"},
    ])

    return {"inline_keyboard": buttons}


def _send_message(config: dict, text: str, keyboard=None) -> bool:
    token    = config.get("TG_BOT_TOKEN")
    group_id = config.get("TG_GROUP_ID")
    topic_id = config.get("TG_TOPIC_ID")

    payload = {
        "chat_id":                  group_id,
        "text":                     text,
        "parse_mode":               "HTML",
        "disable_web_page_preview": True,
    }
    if topic_id:
        payload["message_thread_id"] = int(topic_id)
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)

    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json=payload, timeout=10)
        if r.status_code != 200:
            logger.error("Telegram error: %s — %s", r.status_code, r.text)
            return False
        return True
    except Exception as e:
        logger.error("send_message failed: %s", e)
        return False
