"""
Centralised Telegram bot for all monitored servers.
Handles getUpdates polling, callback button actions, /status and /login commands,
heartbeat checks, and the weekly SLA report.

Централізований Telegram-бот для всіх серверів.
Обробляє getUpdates-опитування, callback-кнопки, команди /status і /login,
heartbeat-перевірки та щотижневий SLA-звіт.
"""
import io
import logging
import time
import json
import requests
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from config import settings
from database import SessionLocal, init_db
from models import Server, MetricsSnapshot
from routers.commands import create_command

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("bot")

BASE_URL = f"https://api.telegram.org/bot{settings.tg_bot_token}"


def _api(method: str, payload: dict, timeout: int = 10) -> dict:
    """Make a Telegram Bot API call and return the parsed JSON response.
    Виконує виклик Telegram Bot API і повертає розпарсену JSON-відповідь."""
    try:
        r = requests.post(f"{BASE_URL}/{method}", json=payload, timeout=timeout)
        return r.json()
    except Exception as e:
        logger.error("%s error: %s", method, e)
        return {"ok": False}


def _send(chat_id: str, text: str, topic_id: str = None,
          keyboard: dict = None, message_id: int = None) -> dict:
    payload = {"chat_id": chat_id, "text": text,
               "parse_mode": "HTML", "disable_web_page_preview": True}
    if topic_id:
        payload["message_thread_id"] = int(topic_id)
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)

    if message_id:
        payload["message_id"] = message_id
        result = _api("editMessageText", payload)
        if not result.get("ok"):
            err = result.get("description", "")
            if "message is not modified" not in err:
                del payload["message_id"]
                result = _api("sendMessage", payload)
        return result

    return _api("sendMessage", payload)


def _send_photo(chat_id: str, topic_id: str, photo_bytes: bytes, caption: str = ""):
    payload = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
    if topic_id:
        payload["message_thread_id"] = int(topic_id)
    try:
        r = requests.post(
            f"{BASE_URL}/sendPhoto",
            data=payload,
            files={"photo": ("chart.png", photo_bytes, "image/png")},
            timeout=30,
        )
        return r.json()
    except Exception as e:
        logger.error("sendPhoto error: %s", e)
        return {"ok": False}


def _generate_cpu_ram_chart(server_id: str, hours: int) -> bytes | None:
    """Render a CPU & RAM line chart as PNG bytes for the given time window.
    Рендерить графік CPU & RAM у вигляді PNG-байтів для вказаного проміжку."""
    db: Session = SessionLocal()
    try:
        from models import Metric
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        rows = db.query(Metric).filter(
            Metric.server_id == server_id,
            Metric.metric_name.in_(["cpu_percent", "ram_percent"]),
            Metric.recorded_at >= cutoff,
        ).order_by(Metric.recorded_at).all()
    finally:
        db.close()

    if not rows:
        return None

    cpu_times, cpu_vals = [], []
    ram_times, ram_vals = [], []
    for r in rows:
        if r.metric_name == "cpu_percent":
            cpu_times.append(r.recorded_at)
            cpu_vals.append(r.value)
        else:
            ram_times.append(r.recorded_at)
            ram_vals.append(r.value)

    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 4))
    if cpu_times:
        ax.plot(cpu_times, cpu_vals, color='cyan', linewidth=1.5, label='CPU %')
    if ram_times:
        ax.plot(ram_times, ram_vals, color='orange', linewidth=1.5, label='RAM %')
    ax.set_ylim(0, 100)
    ax.set_ylabel('%', color='white')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    fig.autofmt_xdate()
    ax.legend(facecolor='#1a1a2e', edgecolor='gray')
    ax.set_title(f'CPU & RAM — {hours}г', color='white')
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=100, facecolor='#0d1117')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _generate_backup_trend_chart(server_id: str) -> bytes | None:
    db: Session = SessionLocal()
    try:
        from models import Metric
        cutoff = datetime.utcnow() - timedelta(days=30)
        rows = db.query(Metric).filter(
            Metric.server_id == server_id,
            Metric.metric_name == "backup_size_mb",
            Metric.recorded_at >= cutoff,
        ).order_by(Metric.recorded_at).all()
    finally:
        db.close()

    if not rows:
        return None

    times = [r.recorded_at for r in rows]
    vals  = [r.value for r in rows]

    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(times, vals, color='steelblue', width=0.02)
    ax.set_ylabel('MB', color='white')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
    fig.autofmt_xdate()
    ax.set_title('Тренд бекапів (30 днів)', color='white')
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=100, facecolor='#0d1117')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _get_server_by_callback(data: str) -> tuple[Server | None, str]:
    """Parse callback_data of the form 'action_server_id' and return (server, action).
    Розбирає callback_data виду 'action_server_id' і повертає (server, action).

    action may be compound: 'restart_service', 'kill_session', etc. — resolved by
    matching the longest suffix that equals a known server id.
    action може бути складеним: 'restart_service', 'kill_session' тощо — знаходимо
    сервер за суфіксом."""
    parts = data.split("_", 1)
    if len(parts) < 2:
        return None, data
    action, server_id = parts[0], parts[1]
    # Locate server by matching the callback_data suffix against known server IDs.
    # Знаходимо сервер по суфіксу callback_data.
    db: Session = SessionLocal()
    try:
        servers = db.query(Server).all()
        for s in servers:
            if data.endswith(s.id):
                action_part = data[: len(data) - len(s.id) - 1]
                return s, action_part
    finally:
        db.close()
    return None, action


def _build_config_map(db: Session) -> dict:
    """Build {server_id: config_dict} for all servers (used by heartbeat and SLA reporters).
    Будує {server_id: config_dict} для всіх серверів (для heartbeat та SLA-звітів)."""
    servers = db.query(Server).all()
    result = {}
    for s in servers:
        result[s.id] = {
            "SERVER_ID":    s.id,
            "COMPANY_NAME": s.name,
            "TG_BOT_TOKEN": settings.tg_bot_token,
            "TG_GROUP_ID":  settings.tg_group_id,
            "TG_TOPIC_ID":  s.tg_topic_id or "",
        }
    return result


def handle_callback(update: dict):
    cb   = update.get("callback_query", {})
    data = cb.get("data", "")
    msg  = cb.get("message", {})
    chat_id    = str(msg.get("chat", {}).get("id", ""))
    message_id = msg.get("message_id")
    topic_id   = str(msg.get("message_thread_id", "")) or None

    # Authorisation: only admin IDs may trigger commands via inline buttons.
    # The bot uses getUpdates and receives updates from any chat or DM —
    # without this check anyone could reboot / block IPs / update agents.
    # Авторизація: керувати агентами через кнопки можуть лише адміни.
    # Бот працює на getUpdates і отримує апдейти з будь-якого чату/DM —
    # без цієї перевірки будь-хто міг би тригерити команди на серверах.
    user_id = cb.get("from", {}).get("id")
    if not settings.admin_ids or user_id not in settings.admin_ids:
        _api("answerCallbackQuery", {
            "callback_query_id": cb.get("id", ""),
            "text": "⛔️ Немає доступу",
            "show_alert": True,
        })
        return

    _api("answerCallbackQuery", {"callback_query_id": cb["id"]})

    # ack|server_id|hours|alert_key — special format parsed directly, not via _get_server_by_callback
    # ack|server_id|hours|alert_key — окремий формат, парситься напряму
    if data.startswith("ack|"):
        parts = data.split("|", 3)
        if len(parts) == 4:
            _, srv_id, hours_str, alert_key = parts
            db: Session = SessionLocal()
            try:
                import storage_helpers as _sh
                _sh.ack_alert(db, srv_id, alert_key, int(hours_str))
            finally:
                db.close()
            _send(chat_id,
                  f"✅ Алерт <b>{alert_key}</b> заглушено на {hours_str} год.",
                  topic_id, message_id=message_id)
        return

    server, action = _get_server_by_callback(data)
    if not server:
        _send(chat_id, "❌ Сервер не знайдено", topic_id, message_id=message_id)
        return

    db: Session = SessionLocal()
    try:
        snap = db.query(MetricsSnapshot).filter(
            MetricsSnapshot.server_id == server.id
        ).first()
        metrics = snap.data if snap else {}
    finally:
        db.close()

    if action == "status":
        _handle_status(chat_id, topic_id, message_id, server, metrics)
    elif action == "sessions":
        _handle_sessions(chat_id, topic_id, message_id, server, metrics)
    elif action == "sessreport":
        _handle_sessions_report_menu(chat_id, topic_id, message_id, server)
    elif action.startswith("sessreport_"):
        try:
            days = int(action.split("_")[1])
        except (IndexError, ValueError):
            days = 7
        _handle_sessions_report(chat_id, topic_id, message_id, server, days)
    elif action == "disk":
        _handle_disk(chat_id, topic_id, message_id, server, metrics)
    elif action == "restart_service":
        _handle_services_menu(chat_id, topic_id, message_id, server, metrics)
    elif action.startswith("svc_restart_"):
        svc_name = action[len("svc_restart_"):]
        _queue_command(chat_id, topic_id, message_id, server,
                       "restart_service", {"service": svc_name})
    elif action == "kill_session":
        _handle_kill_menu(chat_id, topic_id, message_id, server, metrics)
    elif action.startswith("kill_confirm_"):
        session_id = action.replace("kill_confirm_", "")
        _queue_command(chat_id, topic_id, message_id, server,
                       "kick_session", {"session_id": session_id})
    elif action.startswith("block_confirm_"):
        ip = data[len("block_confirm_"):-(len(server.id) + 1)]
        _queue_command(chat_id, topic_id, message_id, server,
                       "block_ip", {"ip": ip})
    elif action == "backup":
        _handle_backup(chat_id, topic_id, message_id, server, metrics)
    elif action.startswith("backup_trend"):
        chart = _generate_backup_trend_chart(server.id)
        if chart:
            _send_photo(chat_id, topic_id, chart, f"📈 Тренд бекапів — {server.name}")
        else:
            _send(chat_id, "📈 Даних ще немає", topic_id, message_id=message_id)
    elif action.startswith("chart_1h"):
        chart = _generate_cpu_ram_chart(server.id, 1)
        if chart:
            _send_photo(chat_id, topic_id, chart, f"📊 CPU & RAM 1г — {server.name}")
        else:
            _send(chat_id, "📊 Даних ще немає", topic_id, message_id=message_id)
    elif action.startswith("chart_24h"):
        chart = _generate_cpu_ram_chart(server.id, 24)
        if chart:
            _send_photo(chat_id, topic_id, chart, f"📊 CPU & RAM 24г — {server.name}")
        else:
            _send(chat_id, "📊 Даних ще немає", topic_id, message_id=message_id)
    elif action.startswith("disk_chart"):
        chart = _generate_cpu_ram_chart(server.id, 24)
        if chart:
            _send_photo(chat_id, topic_id, chart, f"💾 Графік 24г — {server.name}")
        else:
            _send(chat_id, "📊 Даних ще немає", topic_id, message_id=message_id)
    elif action == "bfaudit":
        _handle_bruteforce_audit(chat_id, topic_id, message_id, server)
    elif action == "blocked_ips":
        _handle_blocked_ips(chat_id, topic_id, message_id, server, metrics)
    elif action == "maintenance":
        db: Session = SessionLocal()
        try:
            srv = db.query(Server).filter(Server.id == server.id).first()
            until = datetime.utcnow() + timedelta(hours=2)
            srv.maintenance_until = until
            db.commit()
        finally:
            db.close()
        _send(chat_id,
              f"🔧 <b>{server.name}</b> переведено в режим обслуговування на 2 години.\n"
              f"Алерти призупинено до {(datetime.utcnow() + timedelta(hours=settings.report_utc_offset + 2)).strftime('%H:%M')}",
              topic_id,
              {"inline_keyboard": [[
                  {"text": "✅ Зняти обслуговування", "callback_data": f"maintenance_off_{server.id}"}
              ]]},
              message_id)
    elif action == "maintenance_off":
        db: Session = SessionLocal()
        try:
            srv = db.query(Server).filter(Server.id == server.id).first()
            srv.maintenance_until = None
            db.commit()
        finally:
            db.close()
        _send(chat_id, f"✅ Режим обслуговування знято для {server.name}", topic_id, message_id=message_id)
    elif action.startswith("unblock_confirm_"):
        # Must precede the "unblock_" branch — otherwise startswith("unblock_")
        # would swallow the confirm callback and the queue step is unreachable.
        # Має бути ПЕРЕД гілкою "unblock_" — інакше startswith("unblock_")
        # перехопить callback підтвердження і крок постановки в чергу недосяжний.
        ip = data[len("unblock_confirm_"):-(len(server.id) + 1)]
        _queue_command(chat_id, topic_id, message_id, server, "unblock_ip", {"ip": ip})
    elif action.startswith("unblock_"):
        ip = data[len("unblock_"):-(len(server.id) + 1)]
        keyboard = {"inline_keyboard": [[
            {"text": "✅ Так, розблокувати", "callback_data": f"unblock_confirm_{ip}_{server.id}"},
            {"text": "❌ Скасувати",          "callback_data": f"status_{server.id}"},
        ]]}
        _send(chat_id, f"🔓 Розблокувати IP <b>{ip}</b>?", topic_id, keyboard, message_id)
    elif action == "reboot":
        sessions = metrics.get("active_sessions", [])
        warn = f"\n⚠️ Активних сесій: {len(sessions)}" if sessions else ""
        keyboard = {"inline_keyboard": [[
            {"text": "✅ Так, ребут", "callback_data": f"reboot_confirm_{server.id}"},
            {"text": "❌ Скасувати",  "callback_data": f"reboot_cancel_{server.id}"},
        ]]}
        _send(chat_id, f"⚠️ Перезавантажити {server.name}?{warn}", topic_id, keyboard, message_id)
    elif action == "reboot_confirm":
        _queue_command(chat_id, topic_id, message_id, server, "reboot", {})
    elif action == "reboot_cancel":
        _send(chat_id, "❌ Ребут скасовано", topic_id, message_id=message_id)
    elif action == "update_agent":
        keyboard = {"inline_keyboard": [[
            {"text": "✅ Так, оновити", "callback_data": f"update_agent_confirm_{server.id}"},
            {"text": "❌ Скасувати",    "callback_data": f"status_{server.id}"},
        ]]}
        _send(chat_id,
              f"⬆️ Оновити агента на <b>{server.name}</b>?\n"
              f"Агент завантажить нові файли з GitHub і перезапуститься.",
              topic_id, keyboard, message_id)
    elif action == "update_agent_confirm":
        _queue_command(chat_id, topic_id, message_id, server, "update_agent", {})


def _handle_status(chat_id, topic_id, message_id, server: Server, metrics: dict):
    cpu  = metrics.get("cpu", {})
    ram  = metrics.get("ram", {})
    disks = metrics.get("disks", [])

    local_now = datetime.utcnow() + timedelta(hours=settings.report_utc_offset)
    lines = [f"📊 <b>Статус — {server.name}</b>",
             f"🕐 {local_now.strftime('%H:%M:%S')}", ""]

    lines.append(f"🖥 CPU: <b>{cpu.get('percent', '?')}%</b>  "
                 f"RAM: <b>{ram.get('percent', '?')}%</b> "
                 f"(вільно {ram.get('free_gb', '?')} GB)")

    for d in disks:
        icon = "🔴" if d.get("free_pct", 100) < 5 else \
               "⚠️" if d.get("free_pct", 100) < 10 else "💾"
        lines.append(f"{icon} {d['path']} {d.get('free_pct')}% ({d.get('free_gb')} GB)")

    for svc in metrics.get("services", []):
        icon = "✅" if svc["is_running"] else "❌"
        lines.append(f"{icon} {svc['name']}")

    keyboard = {"inline_keyboard": [
        [
            {"text": "🔄 Оновити",       "callback_data": f"status_{server.id}"},
            {"text": "👥 Сесії",         "callback_data": f"sessions_{server.id}"},
        ],
        [
            {"text": "💾 Диски",         "callback_data": f"disk_{server.id}"},
            {"text": "📦 Бекапи",        "callback_data": f"backup_{server.id}"},
        ],
        [
            {"text": "📊 Графік 1г",     "callback_data": f"chart_1h_{server.id}"},
            {"text": "📊 Графік 24г",    "callback_data": f"chart_24h_{server.id}"},
        ],
        [
            {"text": "🔁 Сервіси",       "callback_data": f"restart_service_{server.id}"},
            {"text": "🔒 Заблоковані IP","callback_data": f"blocked_ips_{server.id}"},
        ],
        [
            {"text": "🛡 Аудит перебору", "callback_data": f"bfaudit_{server.id}"},
        ],
        [
            {"text": "🔧 Обслуговування","callback_data": f"maintenance_{server.id}"},
            {"text": "⬆️ Оновити агента","callback_data": f"update_agent_{server.id}"},
        ],
        [
            {"text": "🔴 Ребут",         "callback_data": f"reboot_{server.id}"},
        ],
    ]}
    _send(chat_id, "\n".join(lines), topic_id, keyboard, message_id)


def _handle_sessions(chat_id, topic_id, message_id, server: Server, metrics: dict):
    sessions = metrics.get("active_sessions", [])
    report_btn = {"text": "📋 Звіт за період", "callback_data": f"sessreport_{server.id}"}

    if not sessions:
        _send(chat_id, "👥 Активних сесій немає", topic_id,
              {"inline_keyboard": [[report_btn]]}, message_id)
        return

    lines = [f"👥 <b>Сесії — {server.name}</b>", ""]
    for s in sessions:
        lines.append(f"• {s.get('username', '?')} [{s.get('state', '?')}] "
                     f"id={s.get('session_id', '?')}")

    btns = [[{"text": f"🚫 Kick {s.get('username','?')}",
              "callback_data": f"kill_confirm_{s.get('session_id', '0')}_{server.id}"}]
            for s in sessions[:5]]
    btns.append([{"text": "🚫 Завершити всіх", "callback_data": f"kill_confirm_all_{server.id}"}])
    btns.append([report_btn])
    _send(chat_id, "\n".join(lines), topic_id, {"inline_keyboard": btns}, message_id)


def _fmt_session_dur(sec) -> str:
    """Format a session duration (seconds) for the Telegram report.
    Форматує тривалість сесії (секунди) для звіту в Telegram."""
    if sec is None:
        return "—"
    if sec < 60:
        return f"{sec}с"
    minutes = sec // 60
    h, m = minutes // 60, minutes % 60
    if h == 0:
        return f"{m}хв"
    return f"{h}г {m}хв" if m else f"{h}г"


def _handle_sessions_report_menu(chat_id, topic_id, message_id, server: Server):
    """Show the period picker for the user-sessions report.
    Показує вибір періоду для звіту сесій користувачів."""
    kb = {"inline_keyboard": [
        [
            {"text": "Сьогодні", "callback_data": f"sessreport_1_{server.id}"},
            {"text": "7 днів",   "callback_data": f"sessreport_7_{server.id}"},
            {"text": "30 днів",  "callback_data": f"sessreport_30_{server.id}"},
        ],
        [{"text": "◀️ Назад", "callback_data": f"sessions_{server.id}"}],
    ]}
    _send(chat_id, "📋 Звіт сесій за який період?", topic_id, kb, message_id)


def _handle_sessions_report(chat_id, topic_id, message_id, server: Server, days: int):
    """Render the paired user-session report (user · IP · connect→disconnect · duration).
    Формує звіт сесій (юзер · IP · вхід→вихід · тривалість) за період."""
    from models import RdpSession

    db: Session = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        rows = (
            db.query(RdpSession)
            .filter(RdpSession.server_id == server.id,
                    RdpSession.logon_time >= cutoff)
            .order_by(RdpSession.logon_time.desc())
            .limit(40)
            .all()
        )
    finally:
        db.close()

    label = {1: "сьогодні", 7: "7 днів", 30: "30 днів"}.get(days, f"{days} дн")
    back = {"inline_keyboard": [[{"text": "◀️ Назад", "callback_data": f"sessions_{server.id}"}]]}

    if not rows:
        _send(chat_id, f"📋 <b>Сесії — {server.name}</b> ({label})\n\nСесій за період немає",
              topic_id, back, message_id)
        return

    off = settings.report_utc_offset
    lines = [f"📋 <b>Сесії — {server.name}</b> ({label})", ""]
    for r in rows[:30]:
        lt = (r.logon_time + timedelta(hours=off)).strftime("%d.%m %H:%M")
        if r.logoff_time is None:
            span, dur = lt, "🟢 активна"
        else:
            end = (r.logoff_time + timedelta(hours=off)).strftime("%H:%M")
            span, dur = f"{lt}→{end}", _fmt_session_dur(r.duration_sec)
        lines.append(f"👤 <b>{r.username or '?'}</b> · {r.ip or '—'}\n   {span} · {dur}")

    _send(chat_id, "\n".join(lines), topic_id, back, message_id)


def _handle_disk(chat_id, topic_id, message_id, server: Server, metrics: dict):
    lines = [f"💾 <b>Диски — {server.name}</b>", ""]
    for d in metrics.get("disks", []):
        delta = f" ↓{abs(d['delta_1h']):.1f}%/г" if d.get("delta_1h", 0) < 0 else ""
        lines.append(f"{d['path']}: {d.get('free_pct')}% вільно "
                     f"({d.get('free_gb')} / {d.get('total_gb')} GB){delta}")
    keyboard = {"inline_keyboard": [[
        {"text": "📊 Графік диску 24г", "callback_data": f"disk_chart_{server.id}"},
        {"text": "◀️ Назад", "callback_data": f"status_{server.id}"},
    ]]}
    _send(chat_id, "\n".join(lines), topic_id, keyboard, message_id)


def _handle_backup(chat_id, topic_id, message_id, server: Server, metrics: dict):
    status = metrics.get("status", "?")
    icon = "✅" if status == "ok" else "⚠️" if status == "warning" else "🔴"
    lines = [f"📦 <b>Бекапи — {server.name}</b>", ""]
    lines.append(f"{icon} Статус: <b>{status}</b>")
    if metrics.get("latest_file"):
        lines.append(f"📄 {metrics['latest_file']}")
        lines.append(f"📅 {metrics.get('latest_time','?')}  ({metrics.get('latest_age_hours','?')}г тому)")
        lines.append(f"📦 {metrics.get('latest_size_mb','?')} MB")
    for issue in metrics.get("issues", []):
        lines.append(f"⚠️ {issue}")
    keyboard = {"inline_keyboard": [[
        {"text": "📈 Тренд 30д", "callback_data": f"backup_trend_{server.id}"},
        {"text": "📊 Статус", "callback_data": f"status_{server.id}"},
    ]]}
    _send(chat_id, "\n".join(lines), topic_id, keyboard, message_id)


def _handle_blocked_ips(chat_id, topic_id, message_id, server: Server, metrics: dict):
    blocked = metrics.get("blocked_ips", [])
    if not blocked:
        _send(chat_id, "🔒 Заблокованих IP немає", topic_id, message_id=message_id)
        return
    lines = [f"🔒 <b>Заблоковані IP — {server.name}</b>", ""]
    for ip in blocked[:10]:
        lines.append(f"• {ip}")
    btns = [[{"text": f"🔓 {ip}", "callback_data": f"unblock_{ip}_{server.id}"}]
            for ip in blocked[:8]]
    _send(chat_id, "\n".join(lines), topic_id, {"inline_keyboard": btns}, message_id)


def _handle_bruteforce_audit(chat_id, topic_id, message_id, server: Server):
    """Audit of brute-force source IPs with block status + block buttons.
    Аудит IP-джерел перебору зі статусом блокування та кнопками блокування."""
    from models import BruteForceIp, MetricsSnapshot

    db: Session = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=30)
        rows = (
            db.query(BruteForceIp)
            .filter(BruteForceIp.server_id == server.id,
                    BruteForceIp.last_seen >= cutoff)
            .order_by(BruteForceIp.attempts.desc())
            .limit(20)
            .all()
        )
        snap = (db.query(MetricsSnapshot)
                .filter(MetricsSnapshot.server_id == server.id).first())
        blocked = set((snap.data or {}).get("blocked_ips", [])) if snap else set()
        items = [(r.ip, r.attempts, r.ip in blocked) for r in rows]
    finally:
        db.close()

    back = {"inline_keyboard": [[{"text": "◀️ Назад", "callback_data": f"status_{server.id}"}]]}
    if not items:
        _send(chat_id, f"🛡 <b>Аудит перебору — {server.name}</b>\n\nСпроб не зафіксовано",
              topic_id, back, message_id)
        return

    lines = [f"🛡 <b>Аудит перебору — {server.name}</b>", ""]
    btns = []
    for ip, attempts, is_blocked in items:
        mark = "🔒" if is_blocked else "⚠️"
        suffix = " — заблоковано" if is_blocked else ""
        lines.append(f"{mark} <code>{ip}</code> · {attempts} спроб{suffix}")
        # Block button only for not-yet-blocked IPs (cap to keep keyboard small).
        # Кнопка блокування лише для незаблокованих (обмежуємо розмір клавіатури).
        if not is_blocked and len(btns) < 8:
            btns.append([{"text": f"🚫 Заблокувати {ip}",
                          "callback_data": f"block_confirm_{ip}_{server.id}"}])
    btns.append([{"text": "◀️ Назад", "callback_data": f"status_{server.id}"}])
    _send(chat_id, "\n".join(lines), topic_id, {"inline_keyboard": btns}, message_id)


def _handle_kill_menu(chat_id, topic_id, message_id, server: Server, metrics: dict):
    sessions = metrics.get("active_sessions", [])
    if not sessions:
        _send(chat_id, "Активних сесій немає", topic_id, message_id=message_id)
        return
    btns = [[{"text": f"❌ {s.get('username','?')} (id={s.get('session_id','?')})",
              "callback_data": f"kill_confirm_{s.get('session_id','0')}_{server.id}"}]
            for s in sessions[:5]]
    btns.append([{"text": "❌ Всі сесії", "callback_data": f"kill_confirm_all_{server.id}"}])
    _send(chat_id, "Оберіть сесію для завершення:", topic_id,
          {"inline_keyboard": btns}, message_id)


def _handle_services_menu(chat_id, topic_id, message_id, server: Server, metrics: dict):
    services = metrics.get("services", [])
    if not services:
        _send(chat_id, "Немає даних про сервіси", topic_id, message_id=message_id)
        return
    # stopped first
    sorted_svcs = sorted(services, key=lambda s: (1 if s.get("is_running") else 0))
    btns = []
    for svc in sorted_svcs:
        icon = "✅" if svc.get("is_running") else "❌"
        name = svc.get("name", "?")
        btns.append([{"text": f"{icon} {name}",
                      "callback_data": f"svc_restart_{name}_{server.id}"}])
    _send(chat_id, "Оберіть сервіс для перезапуску:", topic_id,
          {"inline_keyboard": btns}, message_id)


def _queue_command(chat_id, topic_id, message_id, server: Server,
                   action: str, params: dict):
    db: Session = SessionLocal()
    try:
        create_command(db, server.id, action, params, chat_id, message_id,
                       tg_topic_id=topic_id)
        icons = {"block_ip": "🚫", "kick_session": "👤",
                 "restart_service": "🔄", "reboot": "🔴"}
        icon = icons.get(action, "⏳")
        _send(chat_id,
              f"{icon} Команда <b>{action}</b> поставлена в чергу для {server.name}\n"
              f"Виконається протягом 5-10 секунд...",
              topic_id, message_id=message_id)
    finally:
        db.close()


def handle_message(update: dict):
    msg      = update.get("message", {})
    text     = (msg.get("text") or "").strip()
    chat_id  = str(msg.get("chat", {}).get("id", ""))
    topic_id = str(msg.get("message_thread_id", "")) or None
    user_id  = msg.get("from", {}).get("id")

    if text.startswith("/status"):
        # /status показує метрики сервера — лише для адмінів.
        if not settings.admin_ids or user_id not in settings.admin_ids:
            _send(chat_id, "⛔️ У вас немає доступу.", topic_id)
            return
        db: Session = SessionLocal()
        try:
            if topic_id:
                server = db.query(Server).filter(Server.tg_topic_id == topic_id).first()
            else:
                servers = db.query(Server).all()
                server = servers[0] if len(servers) == 1 else None

            if not server:
                _send(chat_id, "❌ Сервер не знайдено для цього топіку.", topic_id)
                return

            snap = db.query(MetricsSnapshot).filter(
                MetricsSnapshot.server_id == server.id
            ).first()
            metrics = snap.data if snap else {}
        finally:
            db.close()

        _handle_status(chat_id, topic_id, None, server, metrics)
        return

    if not text.startswith("/login"):
        return

    if user_id not in settings.admin_ids:
        _send(chat_id, "⛔️ У вас немає доступу до дашборду.")
        return

    # Просимо API згенерувати одноразовий magic-link (внутрішня мережа docker)
    try:
        r = requests.post(
            "http://api:8000/api/auth/login-token",
            json={"admin_id": user_id},
            headers={"X-Internal-Secret": settings.effective_internal_secret},
            timeout=5,
        )
        if r.status_code != 200:
            _send(chat_id, "❌ Не вдалося створити посилання. Спробуйте пізніше.")
            return
        url = r.json()["url"]
    except Exception as e:
        logger.error("login-token error: %s", e)
        _send(chat_id, "❌ Сервер недоступний.")
        return

    ttl = settings.login_token_ttl_min
    _send(chat_id,
          f"🔐 <b>Вхід у дашборд</b>\n\n"
          f"Посилання дійсне {ttl} хв і працює один раз:\n\n"
          f"{url}\n\n"
          f"<i>Нікому не пересилайте це посилання.</i>")


def run():
    import heartbeat as _hb
    import notifier
    import sla as _sla

    init_db()
    logger.info("Bot started")
    offset = 0
    _last_hb_check = 0.0
    _last_sla_report_day = -1   # порядковий день тижня (0=пн) коли вже надіслали SLA

    while True:
        try:
            result = _api("getUpdates", {"offset": offset, "timeout": 30,
                                         "allowed_updates": ["callback_query", "message"]},
                          timeout=35)
            if not result.get("ok"):
                desc = result.get("description", "")
                if "409" in desc or "conflict" in desc.lower():
                    logger.warning("getUpdates conflict — паралельний екземпляр!")
                time.sleep(5)
                continue

            for upd in result.get("result", []):
                offset = upd["update_id"] + 1
                try:
                    if "callback_query" in upd:
                        handle_callback(upd)
                    elif "message" in upd:
                        handle_message(upd)
                except Exception as e:
                    logger.error("handle update error: %s", e)

            # Heartbeat check — once per minute / раз на хвилину
            now_ts = time.time()
            if now_ts - _last_hb_check >= 60:
                _last_hb_check = now_ts
                try:
                    _hb_db = SessionLocal()
                    try:
                        cfg_map = _build_config_map(_hb_db)
                        _hb.check_heartbeats(_hb_db, cfg_map)
                    finally:
                        _hb_db.close()
                except Exception as e:
                    logger.error("heartbeat check error: %s", e)

                # Weekly SLA report — Monday at 10:00 local time (UTC + offset)
                # Щотижневий SLA-звіт — у понеділок о 10:00 UTC+offset
                try:
                    utc_offset = settings.report_utc_offset
                    local_now = datetime.utcnow() + timedelta(hours=utc_offset)
                    # weekday()==0 → Monday; toordinal guard prevents duplicate sends on the same day
                    # weekday()==0 — понеділок; toordinal запобігає подвійному надсиланню
                    if (local_now.weekday() == 0
                            and local_now.hour == 10
                            and local_now.toordinal() != _last_sla_report_day):
                        _last_sla_report_day = local_now.toordinal()
                        _sla_db = SessionLocal()
                        try:
                            servers = _sla_db.query(Server).all()
                            cfg_map = _build_config_map(_sla_db)
                            # Previous week: Mon–Sun / Минулий тиждень: пн..нд
                            week_end = local_now.replace(
                                hour=0, minute=0, second=0, microsecond=0
                            )
                            week_start = week_end - timedelta(days=7)
                            notifier.send_sla_report(
                                _sla_db, cfg_map, servers,
                                week_start, week_end,
                            )
                        finally:
                            _sla_db.close()
                except Exception as e:
                    logger.error("weekly SLA report error: %s", e)

        except Exception as e:
            logger.error("polling error: %s", e)
            time.sleep(5)


if __name__ == "__main__":
    run()
