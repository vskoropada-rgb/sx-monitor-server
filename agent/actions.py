"""
actions.py — server-side actions: session management, services, reboot, firewall.
actions.py — дії на сервері: завершення сесій, сервіси, перезавантаження, firewall.

The qwinsta parser supports both English and Russian Windows locales
(does not rely on column header names).
Парсер qwinsta підтримує англійський і російський Windows
(не залежить від назв колонок заголовка).
"""
from __future__ import annotations

import logging
import subprocess
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Constants / Константи ────────────────────────────────────────────────────

# Firewall rule name prefix used by this tool — allows bulk identification.
# Префікс назви правила firewall — дозволяє масову ідентифікацію наших правил.
_FW_RULE_PREFIX = "1C_Monitor_Block_"

# qwinsta state prefixes (en + ru, case-insensitive)
# Префікси станів qwinsta (en + ru, регістр не важливий)
_STATE_ACTIVE = ("activ", "акт", "conn", "конн")
_STATE_DISCONNECTED = ("disc", "откл")
_STATE_LISTENING = ("listen", "слуш", "lst", "down")

# Pseudo-sessions to ignore when no username is present.
# Псевдо-сесії, які ігноруємо коли немає юзера.
_SYSTEM_SESSION_NAMES = ("services", "rdp-tcp", "console")


# ─── qwinsta parser ───────────────────────────────────────────────────────────


def _parse_qwinsta_line(raw: str) -> Optional[dict]:
    """
    Parse one line of qwinsta output. Returns a dict or None.
    Парсить один рядок виводу qwinsta. Повертає dict або None.

    Strategy: locate the first all-digit token (the session ID) and work
    outward from it. Everything before is session_name + username; everything
    after is state and ancillary fields. Works regardless of the header locale
    (USERNAME / ПОЛЬЗОВАТЕЛЬ etc.).
    Стратегія: знаходимо перший цілочисельний токен (ID сесії) і відштовхуємось
    від нього. Все до ID — session_name + username, всі після — state. Не залежить
    від мови заголовка.
    """
    if not raw or not raw.strip():
        return None

    # Strip the current-session marker '>' and leading whitespace.
    # Прибираємо маркер поточної сесії '>' та провідні пробіли.
    body = raw.lstrip(" >\t")
    tokens = body.split()
    if len(tokens) < 3:
        return None

    # First all-digit token is the session ID / Перший цілочисельний токен — ID сесії
    id_idx = next(
        (i for i, t in enumerate(tokens) if t.isdigit()),
        None,
    )
    if id_idx is None or id_idx == 0:
        return None

    session_name = tokens[0]
    username = " ".join(tokens[1:id_idx]) if id_idx > 1 else ""
    session_id = tokens[id_idx]
    state = tokens[id_idx + 1] if id_idx + 1 < len(tokens) else ""

    return {
        "session_name": session_name,
        "username": username,
        "session_id": session_id,
        "state": state,
    }


def _is_active_state(state: str) -> bool:
    """True for Active or Disconnected states (user-visible sessions).
    True для станів Active або Disconnected (бачимі сесії з юзером)."""
    s = state.lower()
    return any(s.startswith(p) for p in _STATE_ACTIVE + _STATE_DISCONNECTED)


def _is_listening_state(state: str) -> bool:
    """True for Listen / template entries that should be skipped.
    True для Listen / template-записів, які потрібно пропустити."""
    s = state.lower()
    return any(s.startswith(p) for p in _STATE_LISTENING)


def get_sessions() -> List[dict]:
    """Return active RDP/console sessions. Works on en/ru Windows.
    Повертає активні RDP/console сесії. Працює на en/ru Windows."""
    try:
        result = subprocess.run(
            ["qwinsta"],
            capture_output=True, text=True,
            encoding="cp866", timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.error("qwinsta failed: %s", e)
        return []

    sessions: List[dict] = []
    lines = result.stdout.splitlines()
    if len(lines) < 2:
        logger.debug("qwinsta returned no data: %r", result.stdout[:200])
        return sessions

    # Skip the header line (lines[0]) / Пропускаємо заголовок (lines[0])
    for raw in lines[1:]:
        parsed = _parse_qwinsta_line(raw)
        if not parsed:
            continue

        # Skip Listen templates (rdp-tcp in Listen state).
        # Ігноруємо listening-templates (rdp-tcp у стані Listen).
        if _is_listening_state(parsed["state"]):
            continue

        # Only active/disconnected sessions / Тільки активні/відключені сесії
        if not _is_active_state(parsed["state"]):
            continue

        # Skip system sessions without a username (services with ID=0).
        # Пропускаємо системні сесії без юзера (services з ID=0).
        if not parsed["username"] and parsed["session_name"].lower() in _SYSTEM_SESSION_NAMES:
            continue

        sessions.append({
            "session_name": parsed["session_name"],
            "username":     parsed["username"] or parsed["session_name"],
            "session_id":   parsed["session_id"],
            "state":        parsed["state"],
        })

    logger.debug("qwinsta parsed %d sessions", len(sessions))
    return sessions


def kick_session(session_id: str) -> Tuple[bool, str]:
    """Terminate a session by ID using logoff.
    Завершує сесію по ID через logoff."""
    if not session_id or not session_id.isdigit():
        return False, f"Невірний session_id: {session_id!r}"
    try:
        result = subprocess.run(
            ["logoff", session_id, "/server:localhost"],
            capture_output=True, text=True, encoding="cp866", timeout=15,
        )
    except subprocess.TimeoutExpired:
        return False, "Таймаут logoff"
    except Exception as e:
        return False, f"Виняток: {e}"

    if result.returncode == 0:
        logger.info("Сесія %s завершена", session_id)
        return True, f"Сесія {session_id} завершена"
    err = (result.stderr or result.stdout or "").strip()
    return False, f"logoff помилка: {err}"


def kick_all_sessions() -> Tuple[bool, str]:
    """Terminate all active sessions except session 0 (services).
    Завершує всі активні сесії крім сесії 0 (services)."""
    sessions = get_sessions()
    if not sessions:
        return True, "Активних сесій немає"

    results = []
    for s in sessions:
        sid = s.get("session_id", "")
        if sid.isdigit() and int(sid) > 0:
            ok, msg = kick_session(sid)
            mark = "✅" if ok else "❌"
            results.append(f"{mark} {s.get('username', sid)}: {msg}")
    return True, "\n".join(results) if results else "Немає сесій для завершення"


# ─── Services / Сервіси ───────────────────────────────────────────────────────


def _net_command(verb: str, service: str, timeout: int = 30) -> Tuple[int, str]:
    """Run 'net stop|start <service>' and return (returncode, message).
    Запускає 'net stop|start <service>' і повертає (returncode, повідомлення)."""
    try:
        r = subprocess.run(
            ["net", verb, service],
            capture_output=True, text=True,
            encoding="cp866", timeout=timeout,
        )
        msg = (r.stderr or r.stdout or "").strip()
        return r.returncode, msg
    except subprocess.TimeoutExpired:
        return 1, f"net {verb} {service}: таймаут"
    except Exception as e:
        return 1, f"net {verb}: {e}"


def restart_service(service_name: str) -> Tuple[bool, str]:
    """Stop then start a Windows service. Treats 'not started' as a non-error.
    Зупиняє і запускає сервіс Windows. 'не запущена' не вважається помилкою."""
    import time
    code, msg = _net_command("stop", service_name)
    if code != 0 and "не запущена" not in msg.lower() and "not started" not in msg.lower():
        return False, f"Помилка зупинки: {msg}"

    time.sleep(3)

    code, msg = _net_command("start", service_name)
    if code == 0:
        return True, f"Сервіс «{service_name}» перезапущений"
    return False, f"Помилка запуску: {msg}"


# ─── Reboot / Перезавантаження ────────────────────────────────────────────────


def reboot_server(delay_sec: int = 30) -> Tuple[bool, str]:
    """Schedule a system reboot with the specified delay.
    Планує перезавантаження системи із вказаною затримкою."""
    try:
        r = subprocess.run(
            ["shutdown", "/r", "/t", str(delay_sec), "/c",
             "Перезавантаження через Telegram бот моніторингу"],
            capture_output=True, text=True, encoding="cp866",
        )
        if r.returncode == 0:
            return True, f"🔄 Сервер перезавантажиться через {delay_sec} сек"
        return False, (r.stderr or r.stdout or "").strip()
    except Exception as e:
        return False, str(e)


# ─── Firewall / Брандмауер ────────────────────────────────────────────────────


def block_ip(ip: str) -> Tuple[bool, str]:
    """Add an inbound block rule for the IP in Windows Advanced Firewall.
    Додає правило блокування вхідних з'єднань для IP у Windows Firewall."""
    rule_name = f"{_FW_RULE_PREFIX}{ip}"
    try:
        r = subprocess.run(
            ["netsh", "advfirewall", "firewall", "add", "rule",
             f"name={rule_name}", "dir=in", "action=block",
             f"remoteip={ip}", "protocol=any", "enable=yes"],
            capture_output=True, text=True, encoding="cp866", timeout=15,
        )
    except Exception as e:
        return False, str(e)

    if r.returncode == 0:
        import storage
        storage.record_blocked_ip(ip)
        logger.info("IP %s заблоковано у Firewall", ip)
        return True, f"IP {ip} заблоковано у Windows Firewall"
    return False, (r.stdout + r.stderr).strip()


def unblock_ip(ip: str) -> Tuple[bool, str]:
    """Remove the firewall block rule for the IP.
    Видаляє правило блокування для IP у Firewall."""
    rule_name = f"{_FW_RULE_PREFIX}{ip}"
    try:
        r = subprocess.run(
            ["netsh", "advfirewall", "firewall", "delete", "rule",
             f"name={rule_name}"],
            capture_output=True, text=True, encoding="cp866", timeout=15,
        )
    except Exception as e:
        return False, str(e)

    if r.returncode == 0:
        import storage
        storage.remove_blocked_ip(ip)
        logger.info("Блокування IP %s знято", ip)
        return True, f"IP {ip} розблоковано"
    return False, (r.stdout + r.stderr).strip()


def list_blocked_ips() -> List[str]:
    """Return the sorted list of currently blocked IPs from local storage.
    Повертає відсортований список заблокованих IP з локального сховища."""
    try:
        import storage
        return sorted(storage.get_blocked_ips())
    except Exception:
        return []


# ─── Disk details / Деталі дисків ────────────────────────────────────────────


def get_disk_details(paths: List[str]) -> str:
    """Return a formatted text disk detail block (used by the bot).
    Повертає текстовий блок деталей дисків (для бота)."""
    import psutil
    lines = ["💾 <b>Деталі дисків:</b>"]
    for path in paths:
        try:
            u = psutil.disk_usage(path)
            free_gb  = round(u.free  / 1e9, 2)
            total_gb = round(u.total / 1e9, 2)
            used_gb  = round(u.used  / 1e9, 2)
            pct = round((u.used / u.total) * 100, 1)
            lines.append(f"\n<b>Диск {path}</b>")
            lines.append(f"{_progress_bar(pct)} {pct}%")
            lines.append(f"Використано: {used_gb}GB / {total_gb}GB")
            lines.append(f"Вільно: {free_gb}GB")
        except Exception as e:
            lines.append(f"Диск {path}: помилка — {e}")
    return "\n".join(lines)


def _progress_bar(percent: float, length: int = 10) -> str:
    """Render an emoji progress bar coloured by fill level.
    Рендерить emoji прогрес-бар з кольором залежно від заповнення."""
    filled = max(0, min(length, int(percent / 100 * length)))
    empty = length - filled
    if percent > 80:
        char = "🟥"
    elif percent > 60:
        char = "🟧"
    else:
        char = "🟩"
    return char * filled + "⬜" * empty


# ─── Agent self-update / Самооновлення агента ─────────────────────────────────

# All files that make up the agent installation.
# Всі файли, що складають інсталяцію агента.
_AGENT_FILES = [
    "agent.py", "register_agent.py", "config.py", "storage.py", "actions.py",
    "manage.ps1", "watchdog.ps1", "requirements.txt",
    "collectors/__init__.py", "collectors/disk.py", "collectors/memory.py",
    "collectors/services.py", "collectors/backup.py", "collectors/winupdate.py",
    "collectors/security.py", "collectors/rdp.py", "collectors/usb.py",
    "collectors/software.py", "collectors/schtasks.py",
]


def update_agent(branch: str = "main") -> Tuple[bool, str]:
    """Download updated agent files from GitHub then exit — watchdog will restart.
    Завантажує нові файли агента з GitHub і виходить — watchdog перезапустить."""
    import re as _re
    if not _re.match(r'^[a-zA-Z0-9._/-]{1,100}$', branch):
        return False, f"Недозволена назва гілки: {branch!r}"
    import os
    import sys
    import urllib.request

    base_url = f"https://raw.githubusercontent.com/vskoropada-rgb/sx-monitor-server/{branch}/agent"
    install_dir = os.path.dirname(os.path.abspath(__file__))
    updated, failed = [], []

    for f in _AGENT_FILES:
        url  = f"{base_url}/{f}"
        dest = os.path.join(install_dir, f.replace("/", os.sep))
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            urllib.request.urlretrieve(url, dest)
            updated.append(f)
        except Exception as e:
            failed.append(f"{f}: {e}")
            logger.error("update_agent: не вдалось завантажити %s: %s", f, e)

    if failed:
        return False, f"Оновлено {len(updated)}, помилки: {'; '.join(failed[:3])}"

    logger.info("update_agent: оновлено %d файлів, перезапуск…", len(updated))
    agent_path = os.path.abspath(__file__.replace("actions.py", "agent.py"))
    import subprocess as _sp
    _sp.Popen(
        [sys.executable, agent_path],
        creationflags=getattr(_sp, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    # Return the result before exiting so report_result can deliver it.
    # Повертаємо результат до того як вмерти — report_result встигне відправити статус.
    import threading as _th
    _th.Thread(target=lambda: (__import__("time").sleep(5), os._exit(0)),
               daemon=True).start()
    return True, f"Оновлено {len(updated)} файлів. Перезапуск через 5с…"
