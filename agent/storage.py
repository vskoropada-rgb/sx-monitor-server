"""
Local SQLite storage for the agent — state persistence and event deduplication.
Keeps track of known IPs, USB devices, software, scheduled tasks, admins,
file hashes, backup records, and firewall-blocked IPs.

Локальне SQLite-сховище для агента — збереження стану і дедуплікація подій.
Зберігає відомі IP, USB, ПЗ, задачі, адміни, хеші файлів,
записи бекапів і заблоковані IP.
"""
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "monitor.db"


def get_conn():
    """Return a SQLite connection with row_factory set to sqlite3.Row.
    Повертає з'єднання SQLite з row_factory = sqlite3.Row."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables if they do not exist (idempotent).
    Створює всі таблиці якщо вони відсутні (ідемпотентно)."""
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS metrics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT NOT NULL,
            value       REAL NOT NULL,
            extra       TEXT,
            recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(metric_name, recorded_at);

        CREATE TABLE IF NOT EXISTS known_ips (
            ip          TEXT PRIMARY KEY,
            username    TEXT,
            first_seen  DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen   DATETIME DEFAULT CURRENT_TIMESTAMP,
            count       INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS file_hashes (
            file_path   TEXT PRIMARY KEY,
            hash        TEXT NOT NULL,
            updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS service_states (
            service_name TEXT PRIMARY KEY,
            status       TEXT NOT NULL,
            updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS known_admins (
            username    TEXT PRIMARY KEY,
            added_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- Backup history (for size trend chart and schedule tracking)
        -- Історія бекапів (для графіку розміру та відстеження розкладу)
        CREATE TABLE IF NOT EXISTS backup_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            filename    TEXT NOT NULL,
            size_bytes  INTEGER NOT NULL,
            mtime       DATETIME NOT NULL,
            detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            integrity   TEXT DEFAULT 'unknown'
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_backup_fname ON backup_history(filename);
        CREATE INDEX IF NOT EXISTS idx_backup_det ON backup_history(detected_at);

        -- Known USB devices / Відомі USB-пристрої
        CREATE TABLE IF NOT EXISTS known_usb (
            instance_id   TEXT PRIMARY KEY,
            friendly_name TEXT,
            first_seen    DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- Installed software (for new-software detection) / Встановлене ПЗ (для виявлення нового)
        CREATE TABLE IF NOT EXISTS known_software (
            name       TEXT PRIMARY KEY,
            first_seen DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- Known Task Scheduler tasks / Відомі Task Scheduler завдання
        CREATE TABLE IF NOT EXISTS known_tasks (
            task_name  TEXT PRIMARY KEY,
            first_seen DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- IPs blocked via Telegram bot → Windows Firewall
        -- IP заблоковані через Telegram бот → Windows Firewall
        CREATE TABLE IF NOT EXISTS blocked_ips (
            ip         TEXT PRIMARY KEY,
            blocked_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        """)


# ─── Metrics / Метрики ────────────────────────────────────────────────────────

def save_metric(metric_name: str, value: float, extra: dict = None):
    """Persist a scalar metric value with optional JSON extra data.
    Зберігає числову метрику з опціональними JSON-даними."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO metrics (metric_name, value, extra) VALUES (?, ?, ?)",
            (metric_name, value, json.dumps(extra) if extra else None)
        )


def get_metrics_history(metric_name: str, hours: int = 24) -> list:
    """Return metric history for the last N hours.
    Повертає історію метрики за останні N годин."""
    since = datetime.now() - timedelta(hours=hours)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT value, recorded_at FROM metrics "
            "WHERE metric_name = ? AND recorded_at > ? ORDER BY recorded_at",
            (metric_name, since.isoformat())
        ).fetchall()
    return [{"value": r["value"], "time": r["recorded_at"]} for r in rows]


# ─── Known IPs / Відомі IP ────────────────────────────────────────────────────

def is_known_ip(ip: str) -> bool:
    """True if the IP has been seen before (no new-IP alert).
    True якщо IP вже зустрічався (немає алерту нового IP)."""
    with get_conn() as conn:
        return conn.execute("SELECT 1 FROM known_ips WHERE ip = ?", (ip,)).fetchone() is not None


def register_ip(ip: str, username: str):
    """Record or update an IP. On conflict increments the visit count.
    Записує або оновлює IP. При конфлікті збільшує лічильник візитів."""
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO known_ips (ip, username) VALUES (?, ?)
            ON CONFLICT(ip) DO UPDATE SET
                last_seen=CURRENT_TIMESTAMP, count=count+1,
                username=excluded.username
        """, (ip, username))


# ─── File hashes / Хеші файлів ───────────────────────────────────────────────

def get_file_hash(file_path: str) -> Optional[str]:
    """Return the stored SHA-256 hash for a file, or None if unseen.
    Повертає збережений SHA-256 хеш файлу або None якщо файл новий."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT hash FROM file_hashes WHERE file_path = ?", (file_path,)
        ).fetchone()
        return row["hash"] if row else None


def update_file_hash(file_path: str, hash_val: str):
    """Upsert a file's SHA-256 hash.
    Upsert SHA-256 хеш файлу."""
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO file_hashes (file_path, hash) VALUES (?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                hash=excluded.hash, updated_at=CURRENT_TIMESTAMP
        """, (file_path, hash_val))


# ─── Service states / Стани сервісів ─────────────────────────────────────────

def get_service_state(service_name: str) -> Optional[str]:
    """Return the previously recorded service status, or None on first run.
    Повертає раніше записаний статус сервісу або None при першому запуску."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status FROM service_states WHERE service_name = ?", (service_name,)
        ).fetchone()
        return row["status"] if row else None


def update_service_state(service_name: str, status: str):
    """Upsert the current service status.
    Upsert поточного статусу сервісу."""
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO service_states (service_name, status) VALUES (?, ?)
            ON CONFLICT(service_name) DO UPDATE SET
                status=excluded.status, updated_at=CURRENT_TIMESTAMP
        """, (service_name, status))


# ─── Admins / Адміни ─────────────────────────────────────────────────────────

def get_known_admins() -> set:
    """Return the set of all known local administrator usernames.
    Повертає набір всіх відомих локальних адміністраторів."""
    with get_conn() as conn:
        rows = conn.execute("SELECT username FROM known_admins").fetchall()
        return {r["username"] for r in rows}


def add_known_admin(username: str):
    """Record a new known admin (no-op if already present).
    Записує нового відомого адміна (ігнорується якщо вже є)."""
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO known_admins (username) VALUES (?)", (username,))


# ─── Backup history / Історія бекапів ────────────────────────────────────────

def is_known_backup(filename: str) -> bool:
    """True if this backup filename has already been recorded.
    True якщо цей файл бекапу вже зафіксований."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM backup_history WHERE filename = ?", (filename,)
        ).fetchone() is not None


def record_backup(filename: str, size_bytes: int, mtime: str, integrity: str):
    """Record a new backup file (ignored if already present).
    Записує новий файл бекапу (ігнорується якщо вже є)."""
    with get_conn() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO backup_history (filename, size_bytes, mtime, integrity)
            VALUES (?, ?, ?, ?)
        """, (filename, size_bytes, mtime, integrity))


def update_backup_integrity(filename: str, integrity: str):
    """Update the integrity check result for an existing backup record.
    Оновлює результат перевірки цілісності для існуючого запису бекапу."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE backup_history SET integrity = ? WHERE filename = ?",
            (integrity, filename),
        )


def get_backup_integrity(filename: str) -> Optional[str]:
    """Return the stored integrity status for a backup file.
    Повертає збережений статус цілісності файлу бекапу."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT integrity FROM backup_history WHERE filename = ?", (filename,)
        ).fetchone()
        return row["integrity"] if row else None


# ─── USB devices / USB-пристрої ───────────────────────────────────────────────

def is_known_usb(instance_id: str) -> bool:
    """True if this USB device has been seen before.
    True якщо цей USB-пристрій вже зустрічався."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM known_usb WHERE instance_id = ?", (instance_id,)
        ).fetchone() is not None


def register_usb(instance_id: str, friendly_name: str):
    """Record a new USB device (no-op if already known).
    Записує новий USB-пристрій (ігнорується якщо вже відомий)."""
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO known_usb (instance_id, friendly_name) VALUES (?, ?)",
            (instance_id, friendly_name)
        )


# ─── Software / Програмне забезпечення ───────────────────────────────────────

def is_known_software(name: str) -> bool:
    """True if this software title has been seen before.
    True якщо це ПЗ вже зустрічалось."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM known_software WHERE name = ?", (name,)
        ).fetchone() is not None


def register_software(name: str):
    """Record a newly detected software title.
    Записує нове виявлене ПЗ."""
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO known_software (name) VALUES (?)", (name,)
        )


# ─── Scheduled tasks / Задачі планувальника ──────────────────────────────────

def is_known_task(task_name: str) -> bool:
    """True if this scheduled task has been seen before.
    True якщо це завдання планувальника вже зустрічалось."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM known_tasks WHERE task_name = ?", (task_name,)
        ).fetchone() is not None


def register_task(task_name: str):
    """Record a newly detected scheduled task.
    Записує нове виявлене завдання планувальника."""
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO known_tasks (task_name) VALUES (?)", (task_name,)
        )


# ─── Blocked IPs / Заблоковані IP ────────────────────────────────────────────

def record_blocked_ip(ip: str):
    """Record an IP that was blocked via the firewall.
    Записує IP, заблокований через firewall."""
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO blocked_ips (ip) VALUES (?)", (ip,))


def remove_blocked_ip(ip: str):
    """Remove an IP from the blocked list (after unblock).
    Видаляє IP зі списку заблокованих (після розблокування)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM blocked_ips WHERE ip = ?", (ip,))


def get_blocked_ips() -> set:
    """Return the set of all currently blocked IPs.
    Повертає набір всіх поточно заблокованих IP."""
    with get_conn() as conn:
        rows = conn.execute("SELECT ip FROM blocked_ips").fetchall()
        return {r["ip"] for r in rows}
