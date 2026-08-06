"""
SQLAlchemy ORM models — all tables for the monitoring platform.
SQLAlchemy ORM-моделі — всі таблиці платформи моніторингу.
"""
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Text, DateTime,
    ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from database import Base


class Server(Base):
    """Registered monitoring agent (one row per Windows server).
    Зареєстрований агент моніторингу (один рядок на Windows-сервер)."""
    __tablename__ = "servers"

    id                = Column(String, primary_key=True)
    name              = Column(String, nullable=False)
    api_key           = Column(String, nullable=False, unique=True)  # SHA-256 hex / SHA-256 hex
    tg_topic_id       = Column(String)
    maintenance_until = Column(DateTime, nullable=True)
    agent_version     = Column(String, nullable=True)
    last_seen         = Column(DateTime)
    created_at        = Column(DateTime, default=datetime.utcnow)


class Metric(Base):
    """Time-series numeric metrics (CPU, RAM, disk free %) for Grafana charts.
    Числові метрики у часі (CPU, RAM, вільний % диску) для графіків Grafana."""
    __tablename__ = "metrics"
    __table_args__ = (
        Index("idx_metrics_server_name_time", "server_id", "metric_name", "recorded_at"),
    )

    id          = Column(Integer, primary_key=True, autoincrement=True)
    server_id   = Column(String, ForeignKey("servers.id"), nullable=False)
    metric_name = Column(String, nullable=False)
    value       = Column(Float, nullable=False)
    extra       = Column(JSONB)
    recorded_at = Column(DateTime, default=datetime.utcnow)


class Alert(Base):
    """Sent alert log — used for cooldown deduplication.
    Журнал відправлених алертів — використовується для дедуплікації за cooldown."""
    __tablename__ = "alerts"
    __table_args__ = (
        Index("idx_alerts_server_key_time", "server_id", "alert_key", "sent_at"),
    )

    id          = Column(Integer, primary_key=True, autoincrement=True)
    server_id   = Column(String, ForeignKey("servers.id"), nullable=False)
    alert_key   = Column(String, nullable=False)
    alert_type  = Column(String)
    severity    = Column(String, nullable=False)
    message     = Column(Text)
    sent_at     = Column(DateTime, default=datetime.utcnow)
    acked_until = Column(DateTime, nullable=True)  # snoozed until / заглушено до


class PendingAlert(Base):
    """Accumulated non-critical alerts, flushed in the daily report.
    Накопичені некритичні алерти, скидаються у щоденному звіті."""
    __tablename__ = "pending_alerts"
    __table_args__ = (
        UniqueConstraint("server_id", "alert_key", name="uq_pending_server_key"),
    )

    id        = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(String, ForeignKey("servers.id"), nullable=False)
    alert_key = Column(String, nullable=False)
    title     = Column(String, nullable=False)
    body      = Column(Text, default="")
    severity  = Column(String, default="warning")
    count     = Column(Integer, default=1)   # occurrences since last flush / кількість з останнього скидання
    added_at  = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class Command(Base):
    """Remote command queued via Telegram bot, executed by the agent.
    Команда з Telegram-бота, що виконується агентом на сервері."""
    __tablename__ = "commands"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    server_id     = Column(String, ForeignKey("servers.id"), nullable=False)
    action        = Column(String, nullable=False)  # block_ip | kick_session | restart_service | reboot
    params        = Column(JSONB)                   # {"ip": "1.2.3.4"} | {"session_id": "2"}
    status        = Column(String, default="pending")  # pending | executing | done | failed
    result        = Column(Text)
    tg_chat_id    = Column(String)
    tg_message_id = Column(Integer)
    tg_topic_id   = Column(String)
    created_at    = Column(DateTime, default=datetime.utcnow)
    executed_at   = Column(DateTime)


class MetricsSnapshot(Base):
    """Latest metrics snapshot per server — for fast bot status display.
    Останній знімок метрик кожного сервера — для швидкого відображення статусу в боті."""
    __tablename__ = "metrics_snapshots"

    server_id  = Column(String, ForeignKey("servers.id"), primary_key=True)
    data       = Column(JSONB, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)


class KnownEntity(Base):
    """Known IPs, USB devices, software, tasks, admins — event deduplication.
    Відомі IP, USB, ПЗ, задачі, адміни — дедуплікація подій."""
    __tablename__ = "known_entities"
    __table_args__ = (
        UniqueConstraint("server_id", "entity_type", "value", name="uq_entity"),
    )

    id          = Column(Integer, primary_key=True, autoincrement=True)
    server_id   = Column(String, ForeignKey("servers.id"), nullable=False)
    entity_type = Column(String, nullable=False)   # ip | usb | software | task | admin | file_hash
    value       = Column(String, nullable=False)
    meta        = Column(JSONB)
    first_seen  = Column(DateTime, default=datetime.utcnow)
    last_seen   = Column(DateTime, default=datetime.utcnow)


class RdpLog(Base):
    """RDP login events received from agents.
    Журнал RDP-входів з агентів."""
    __tablename__ = "rdp_log"
    __table_args__ = (
        Index("idx_rdp_log_server_time", "server_id", "event_time"),
        UniqueConstraint("server_id", "username", "ip", "event_time", name="uq_rdp_event"),
    )

    id         = Column(Integer, primary_key=True, autoincrement=True)
    server_id  = Column(String, ForeignKey("servers.id"), nullable=False)
    username   = Column(String, nullable=False)
    ip         = Column(String)
    is_new_ip  = Column(Integer, default=0)   # 0/1 — first login from this IP / перший вхід з цього IP
    event_time = Column(DateTime, nullable=False)  # stored as UTC / зберігається в UTC
    logged_at  = Column(DateTime, default=datetime.utcnow)


class RdpSession(Base):
    """Paired RDP logon/logoff — one row per user session.
    Спарена пара вхід/вихід RDP — один рядок на сесію користувача.

    A logon (4624) opens the row; the matching logoff (4634/4647), tied by
    logon_id, closes it and fills logoff_time + duration_sec. An open row
    (logoff_time is NULL) means the session is still active.
    Вхід (4624) відкриває рядок; відповідний вихід (4634/4647), зв'язаний
    через logon_id, закриває його і заповнює logoff_time + duration_sec.
    Відкритий рядок (logoff_time = NULL) — сесія ще активна.
    """
    __tablename__ = "rdp_sessions"
    __table_args__ = (
        Index("idx_rdp_sessions_server_logon", "server_id", "logon_time"),
        UniqueConstraint("server_id", "logon_id", name="uq_rdp_session"),
    )

    id           = Column(Integer, primary_key=True, autoincrement=True)
    server_id    = Column(String, ForeignKey("servers.id"), nullable=False)
    logon_id     = Column(String, nullable=False)   # Windows TargetLogonId — pairing key
    username     = Column(String, nullable=False)
    ip           = Column(String)
    logon_time   = Column(DateTime, nullable=False)  # stored as UTC / зберігається в UTC
    logoff_time  = Column(DateTime)                  # UTC; NULL = still active / ще активна
    duration_sec = Column(Integer)                   # filled on logoff / заповнюється при виході
    logged_at    = Column(DateTime, default=datetime.utcnow)


class BruteForceIp(Base):
    """Persisted brute-force source IPs per server, for the block-status audit.
    Збережені IP-джерела перебору по серверах — для аудиту статусу блокування.

    Populated from each metrics payload (suspicious_ips + brute_force_alerts).
    `attempts` keeps the peak count seen in a single detection window (the count
    is a rolling 10-min value, so max — not sum — avoids overcounting on replay).
    Blocked/not-blocked status is derived at read time from the agent's current
    blocked_ips, not stored here.
    Заповнюється з кожної порції метрик. `attempts` — пік за одне вікно (count
    ковзний за 10 хв, тому max, не сума). Статус блокування визначається при
    читанні з поточного blocked_ips агента.
    """
    __tablename__ = "brute_force_ips"
    __table_args__ = (
        UniqueConstraint("server_id", "ip", name="uq_bruteforce_ip"),
        Index("idx_bruteforce_server_seen", "server_id", "last_seen"),
    )

    id         = Column(Integer, primary_key=True, autoincrement=True)
    server_id  = Column(String, ForeignKey("servers.id"), nullable=False)
    ip         = Column(String, nullable=False)
    attempts   = Column(Integer, default=0)   # peak count in a window / пік за вікно
    usernames  = Column(JSONB)                # observed target usernames / цільові юзери
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen  = Column(DateTime, default=datetime.utcnow)
    # Rolling 24h accumulator — catches "low-and-slow" (5 tries, pause, 5 more).
    # total_24h grows only by the increase over last_window_count, so rolling
    # 10-min reports are not double-counted; it resets when window_reset_at ages out.
    # Ковзний лічильник за 24 год — ловить «low-and-slow» (5 спроб, пауза, ще 5).
    total_24h         = Column(Integer, default=0)   # cumulative attempts in 24h / сумарно за 24 год
    last_window_count = Column(Integer, default=0)   # last reported window count / останній count вікна
    window_reset_at   = Column(DateTime, default=datetime.utcnow)  # 24h window start / початок вікна 24 год


class LoginLog(Base):
    """Dashboard administrator login/logout audit log.
    Журнал входів і виходів адміністраторів дашборду."""
    __tablename__ = "login_logs"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    admin_id   = Column(Integer, nullable=False)
    action     = Column(String, nullable=False)   # login | logout
    ip         = Column(String)
    user_agent = Column(Text)
    at         = Column(DateTime, default=datetime.utcnow)


class AuthToken(Base):
    """One-time magic-link token for dashboard login via Telegram.
    Одноразовий magic-link токен для входу в дашборд через Telegram."""
    __tablename__ = "auth_tokens"

    token      = Column(String, primary_key=True)  # SHA-256 hash / SHA-256 хеш
    admin_id   = Column(Integer, nullable=False)   # Telegram user_id
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used_at    = Column(DateTime)


class ServerHeartbeat(Base):
    """Current online/offline status per server — for heartbeat alert tracking.
    Поточний статус онлайн/офлайн кожного сервера — для heartbeat-алертів."""
    __tablename__ = "server_heartbeats"

    server_id  = Column(String, ForeignKey("servers.id"), primary_key=True)
    online     = Column(Integer, default=1)   # 1=online, 0=offline
    changed_at = Column(DateTime, default=datetime.utcnow)


class UptimeEvent(Base):
    """Online/offline transition log for SLA calculation.
    Лог переходів онлайн/офлайн для розрахунку SLA."""
    __tablename__ = "uptime_events"
    __table_args__ = (
        Index("idx_uptime_server_at", "server_id", "at"),
    )

    id        = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(String, ForeignKey("servers.id"), nullable=False)
    event     = Column(String, nullable=False)   # "offline" | "online"
    at        = Column(DateTime, default=datetime.utcnow, nullable=False)
