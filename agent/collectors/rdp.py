"""
collectors/rdp.py — RDP session monitoring and new-IP detection via Windows Event Log.
collectors/rdp.py — моніторинг RDP-сесій та виявлення нових IP через Windows Event Log.

Active sessions are read via qwinsta (delegated to actions.py).
Active IPs are mapped via netstat (port 3389 ESTABLISHED connections).
Recent RDP logins come from Event Log ID 4624 (LogonType=10).

Активні сесії зчитуються через qwinsta (делеговано до actions.py).
Активні IP маппуються через netstat (ESTABLISHED з'єднання на порт 3389).
Нещодавні RDP-входи — з Event Log ID 4624 (LogonType=10).
"""
from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timedelta
from typing import List

import actions
from storage import is_known_ip, register_ip

logger = logging.getLogger(__name__)


def get_active_sessions() -> List[dict]:
    """Active RDP sessions via qwinsta (uses the parser from actions.py).
    Активні RDP-сесії через qwinsta (використовує parser з actions.py)."""
    return actions.get_sessions()


def get_session_ips() -> dict:
    """Map IP → True for established connections on port 3389 (via netstat).
    Мапа IP→True для встановлених підключень на порт 3389 (netstat)."""
    ips: dict = {}
    try:
        result = subprocess.run(
            ["netstat", "-n"],
            capture_output=True, text=True,
            encoding="cp866", timeout=10,
        )
    except Exception as e:
        logger.error("netstat failed: %s", e)
        return ips

    for line in result.stdout.splitlines():
        if ":3389" not in line or "ESTABLISHED" not in line:
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        remote = parts[2]
        ip = remote.rsplit(":", 1)[0].strip("[]")
        if ip:
            ips[ip] = True
    return ips


def get_recent_rdp_logins(minutes: int = 60) -> List[dict]:
    """Read Event ID 4624 LogonType=10 (successful RDP logins) for the last N minutes.
    Читає Event ID 4624 LogonType=10 — успішні RDP-входи за останні N хвилин.

    Note: TimeGenerated returns local Windows time, not UTC.
    Примітка: TimeGenerated повертає локальний час Windows, не UTC.
    """
    try:
        import win32evtlog
    except ImportError:
        logger.warning("pywin32 недоступний — RDP логіни пропущено")
        return []

    logins: List[dict] = []
    try:
        hand = win32evtlog.OpenEventLog(None, "Security")
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        cutoff = datetime.now() - timedelta(minutes=minutes)
    except Exception as e:
        logger.error("OpenEventLog failed: %s", e)
        return logins

    try:
        while True:
            records = win32evtlog.ReadEventLog(hand, flags, 0)
            if not records:
                break
            for rec in records:
                try:
                    event_time = datetime(*rec.TimeGenerated.timetuple()[:6])
                    if event_time < cutoff:
                        return logins  # reading backwards — older records follow
                                       # читаємо з кінця — далі тільки старіші
                    if (rec.EventID & 0xFFFF) != 4624:
                        continue

                    strings = rec.StringInserts or []
                    # LogonType is at index 8 in the standard 4624 event layout.
                    # LogonType — індекс 8 у стандартному layout події 4624.
                    if len(strings) <= 8:
                        continue
                    logon_type = (strings[8] or "").strip()
                    if logon_type != "10":  # 10 = RemoteInteractive (RDP)
                        continue

                    username = (strings[5] or "").strip() if len(strings) > 5 else ""
                    ip = (strings[18] or "").strip() if len(strings) > 18 else "unknown"
                    # TargetLogonId (index 7) uniquely ties this logon to its
                    # matching logoff (4634/4647) so the server can pair sessions.
                    # TargetLogonId (індекс 7) унікально зв'язує цей вхід із
                    # відповідним виходом (4634/4647) — сервер парує сесії.
                    logon_id = (strings[7] or "").strip() if len(strings) > 7 else ""

                    if not username or not ip:
                        continue

                    logins.append({
                        "username":  username,
                        "ip":        ip,
                        "logon_id":  logon_id,
                        "time":      event_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "is_new_ip": not is_known_ip(ip),
                    })
                    if ip not in ("", "-", "unknown"):
                        register_ip(ip, username)
                except Exception as e:
                    logger.debug("Skip event: %s", e)
    finally:
        try:
            win32evtlog.CloseEventLog(hand)
        except Exception:
            pass

    return logins


def get_recent_rdp_logoffs(minutes: int = 60) -> List[dict]:
    """Read Event ID 4634/4647 (logoff) for the last N minutes.
    Читає Event ID 4634/4647 (вихід) за останні N хвилин.

    Each logoff carries a TargetLogonId that matches the logon's; the server
    pairs them to compute session duration. LogonType is not always present on
    4634, so we do not filter by it here — the server keeps only logoffs whose
    logon_id matches a tracked RDP logon.
    Кожен вихід містить TargetLogonId, що збігається з входом; сервер парує їх
    для обчислення тривалості. LogonType на 4634 присутній не завжди, тож тут не
    фільтруємо — сервер лишає лише виходи, чий logon_id збігається з RDP-входом.

    Note: TimeGenerated returns local Windows time, not UTC.
    Примітка: TimeGenerated повертає локальний час Windows, не UTC.
    """
    try:
        import win32evtlog
    except ImportError:
        return []

    logoffs: List[dict] = []
    try:
        hand = win32evtlog.OpenEventLog(None, "Security")
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        cutoff = datetime.now() - timedelta(minutes=minutes)
    except Exception as e:
        logger.error("OpenEventLog (logoff) failed: %s", e)
        return logoffs

    try:
        while True:
            records = win32evtlog.ReadEventLog(hand, flags, 0)
            if not records:
                break
            for rec in records:
                try:
                    event_time = datetime(*rec.TimeGenerated.timetuple()[:6])
                    if event_time < cutoff:
                        return logoffs  # reading backwards — older records follow
                                        # читаємо з кінця — далі тільки старіші
                    if (rec.EventID & 0xFFFF) not in (4634, 4647):
                        continue

                    strings = rec.StringInserts or []
                    # 4634/4647 layout: [1]=TargetUserName, [3]=TargetLogonId.
                    # Layout 4634/4647: [1]=TargetUserName, [3]=TargetLogonId.
                    if len(strings) <= 3:
                        continue
                    username = (strings[1] or "").strip()
                    logon_id = (strings[3] or "").strip()
                    if not logon_id:
                        continue

                    logoffs.append({
                        "username": username,
                        "logon_id": logon_id,
                        "time":     event_time.strftime("%Y-%m-%d %H:%M:%S"),
                    })
                except Exception as e:
                    logger.debug("Skip logoff event: %s", e)
    finally:
        try:
            win32evtlog.CloseEventLog(hand)
        except Exception:
            pass

    return logoffs


def collect(config: dict) -> dict:
    """Collect all RDP metrics: active sessions, recent logins/logoffs, new-IP alerts.
    Збирає всі RDP-метрики: активні сесії, нещодавні входи/виходи, алерти нових IP."""
    active = get_active_sessions()
    ips = get_session_ips()
    # Extend the lookback window slightly beyond the poll interval to avoid gaps.
    # Розширюємо вікно перегляду трохи більше за інтервал опитування щоб не пропустити події.
    minutes = max(2, int(config.get("CHECK_INTERVAL_SEC", 60)) // 60 + 2)
    recent = get_recent_rdp_logins(minutes=minutes)
    logoffs = get_recent_rdp_logoffs(minutes=minutes)

    new_ip_alerts = [
        l for l in recent
        if l["is_new_ip"] and l["ip"] not in ("", "-", "unknown")
    ]

    return {
        "active_sessions": active,
        "active_ips":      list(ips.keys()),
        "recent_logins":   recent,
        "recent_logoffs":  logoffs,
        "new_ip_alerts":   new_ip_alerts,
        "session_count":   len(active),
    }
