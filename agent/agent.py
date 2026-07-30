"""
agent.py — lightweight client for the client-server monitoring architecture.
агент.py — легкий клієнт для client-server архітектури моніторингу.

Replaces the local main.py/monitor.py (which did analysis and Telegram) with:
  • metric collection via existing collectors/;
  • sending metrics to the central server (POST /api/metrics);
  • polling the command queue (GET /api/commands/pending) and executing
    commands locally via actions.py (block_ip / kick_session / restart_service
    / reboot / update_agent);
  • reporting results (POST /api/commands/{id}/result).

Замінює локальний main.py/monitor.py (з аналізом і Telegram) на:
  • збір метрик наявними collectors/;
  • відправку метрик на центральний сервер (POST /api/metrics);
  • опитування черги команд (GET /api/commands/pending) і їх локальне
    виконання через actions.py (block_ip / kick_session / restart_service
    / reboot / update_agent);
  • звіт про результат (POST /api/commands/{id}/result).

Metric analysis, alert deduplication, and Telegram — all on the server side.
storage.py stays on the agent: collectors use SQLite to remember known IPs /
admins / USB devices / file hashes.

Аналіз метрик, дедуплікація алертів і Telegram — тепер на сервері.
storage.py лишається на агенті: collectors використовують SQLite для
запам'ятовування «відомих» IP / адмінів / USB / хешів файлів.

Config (.env): SERVER_ID, API_URL, API_KEY + standard collector settings.
Конфіг (.env): SERVER_ID, API_URL, API_KEY + звичайні налаштування collectors.
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config as _config_module
import actions

# ─── Logging setup / Налаштування логування ──────────────────────────────────

LOG_PATH = Path(__file__).parent / "agent.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[
        RotatingFileHandler(LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3,
                            encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("agent")

AGENT_VERSION = "1.6.0"

try:
    import requests
except ImportError:
    logger.critical("Бібліотека requests не встановлена (pip install requests)")
    raise


# ─── Metric collection / Збір метрик ─────────────────────────────────────────

def collect_metrics(config: dict) -> dict:
    """Run all collectors sequentially. A failure in one does not abort the rest.
    Послідовно опитує всі collectors. Помилка одного не валить решту."""
    from collectors import disk, memory, services, backup

    metrics: dict = {}

    def _run(name: str, fn):
        try:
            metrics.update(fn())
        except Exception as e:
            logger.error("collector %s: %s", name, e)

    _run("disk",     lambda: disk.collect(config))
    _run("memory",   lambda: memory.collect(config))
    _run("services", lambda: services.collect(config))
    _run("backup",   lambda: backup.collect(config))

    # Windows Update reboot flag / Прапор очікуваного перезавантаження Windows
    try:
        from collectors import winupdate
        metrics.update(winupdate.collect(config))
    except Exception as e:
        logger.error("collector winupdate: %s", e)

    # Security + RDP collectors require pywin32 — gracefully skip if unavailable.
    # Збірники security + rdp потребують pywin32 — пропускаємо, якщо відсутній.
    try:
        from collectors import security, rdp
        metrics.update(security.collect(config))
        metrics.update(rdp.collect(config))
    except ImportError:
        logger.warning("pywin32 недоступний — security/rdp пропущено")
    except Exception as e:
        logger.error("collector security/rdp: %s", e)

    # USB / software / scheduled tasks collectors
    for mod_name in ("usb", "software", "schtasks"):
        try:
            mod = __import__(f"collectors.{mod_name}", fromlist=[mod_name])
            metrics.update(mod.collect(config))
        except Exception as e:
            logger.error("collector %s: %s", mod_name, e)

    # Include the current firewall block list in the metrics payload.
    # Додаємо список заблокованих IP до метрик.
    try:
        blocked = actions.list_blocked_ips()
        metrics["blocked_ips"] = blocked
    except Exception:
        metrics["blocked_ips"] = []

    # Filter out already-blocked IPs from brute-force alerts to avoid duplicate actions.
    # Прибираємо вже заблоковані IP з brute-force алертів, щоб уникнути дублювання дій.
    if metrics.get("brute_force_alerts"):
        try:
            blocked = set(actions.list_blocked_ips())
            if blocked:
                metrics["brute_force_alerts"] = [
                    a for a in metrics["brute_force_alerts"]
                    if a.get("ip") not in blocked
                ]
        except Exception as e:
            logger.error("filter blocked ips: %s", e)

    metrics["agent_version"] = AGENT_VERSION
    return metrics


# ─── HTTP to the server / HTTP до сервера ────────────────────────────────────

def _headers(config: dict) -> dict:
    """Build auth headers for API requests.
    Формує заголовки автентифікації для API-запитів."""
    return {"X-Api-Key": config.get("API_KEY", ""), "Content-Type": "application/json"}


def send_metrics(config: dict, metrics: dict) -> bool:
    """POST metrics payload to the central server.
    Надсилає payload метрик на центральний сервер."""
    url = config["API_URL"].rstrip("/") + "/api/metrics"
    try:
        r = requests.post(url, json=metrics, headers=_headers(config), timeout=15)
        if r.status_code == 200:
            return True
        logger.error("POST /api/metrics → %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        logger.error("send_metrics: %s", e)
    return False


def fetch_commands(config: dict) -> list:
    """Poll the pending command queue from the server.
    Опитує чергу команд на сервері."""
    url = config["API_URL"].rstrip("/") + "/api/commands/pending"
    try:
        r = requests.get(url, headers=_headers(config), timeout=10)
        if r.status_code == 200:
            return r.json()
        logger.error("GET /api/commands/pending → %s", r.status_code)
    except Exception as e:
        logger.error("fetch_commands: %s", e)
    return []


def report_result(config: dict, command_id: int, status: str, result: str):
    """Report a command execution result back to the server.
    Звітує про результат виконання команди на сервер."""
    url = config["API_URL"].rstrip("/") + f"/api/commands/{command_id}/result"
    try:
        requests.post(url, json={"status": status, "result": result[:1000]},
                      headers=_headers(config), timeout=10)
    except Exception as e:
        logger.error("report_result(%s): %s", command_id, e)


# ─── Command execution / Виконання команд ────────────────────────────────────

def execute_command(config: dict, cmd: dict) -> tuple[str, str]:
    """Dispatch and execute a command from the queue.
    Returns (status, result_text) where status ∈ {done, failed}.
    Виконує команду з черги. Повертає (status, result_text), status ∈ {done, failed}."""
    action = cmd.get("action")
    params = cmd.get("params") or {}
    logger.info("Виконую команду #%s: %s %s", cmd.get("id"), action, params)

    try:
        if action == "block_ip":
            ip = params.get("ip")
            if not ip:
                return "failed", "не вказано ip"
            ok, msg = actions.block_ip(ip)

        elif action == "kick_session":
            sid = str(params.get("session_id", ""))
            if sid == "all":
                ok, msg = actions.kick_all_sessions()
            elif sid:
                ok, msg = actions.kick_session(sid)
            else:
                return "failed", "не вказано session_id"

        elif action == "restart_service":
            svc = params.get("service")
            if not svc:
                # Default to the first configured service if none specified.
                # За замовчуванням — перший із MONITOR_SERVICES якщо не вказано.
                svcs = [s.strip() for s in config.get("MONITOR_SERVICES", "").split(",") if s.strip()]
                svc = svcs[0] if svcs else None
            if not svc:
                return "failed", "не вказано сервіс"
            ok, msg = actions.restart_service(svc)

        elif action == "reboot":
            delay = int(params.get("delay_sec", 30))
            ok, msg = actions.reboot_server(delay)

        elif action == "unblock_ip":
            ip = params.get("ip")
            if not ip:
                return "failed", "не вказано ip"
            ok, msg = actions.unblock_ip(ip)

        elif action == "update_agent":
            branch = params.get("branch", "main")
            ok, msg = actions.update_agent(branch)

        else:
            return "failed", f"невідома команда: {action}"

        return ("done" if ok else "failed"), msg

    except Exception as e:
        logger.exception("execute_command")
        return "failed", str(e)


# ─── Background loops / Фонові цикли ─────────────────────────────────────────

def metrics_loop(stop: threading.Event):
    """Collect and send metrics every CHECK_INTERVAL_SEC seconds.
    Збирає і надсилає метрики кожні CHECK_INTERVAL_SEC секунд."""
    while not stop.is_set():
        config = _config_module.load()
        interval = int(config.get("CHECK_INTERVAL_SEC", 60) or 60)
        try:
            metrics = collect_metrics(config)
            ok = send_metrics(config, metrics)
            logger.info("Метрики надіслано: %s (CPU %s%%, RAM %s%%)",
                        ok,
                        metrics.get("cpu", {}).get("percent"),
                        metrics.get("ram", {}).get("percent"))
        except Exception as e:
            logger.error("metrics_loop: %s", e)
        stop.wait(interval)


def command_loop(stop: threading.Event):
    """Poll and execute queued commands every COMMAND_POLL_SEC seconds.
    Опитує і виконує команди з черги кожні COMMAND_POLL_SEC секунд."""
    while not stop.is_set():
        config = _config_module.load()
        poll = int(config.get("COMMAND_POLL_SEC", 5) or 5)
        try:
            for cmd in fetch_commands(config):
                status, result = execute_command(config, cmd)
                report_result(config, cmd["id"], status, result)
                logger.info("Команда #%s → %s: %s", cmd["id"], status, result)
        except Exception as e:
            logger.error("command_loop: %s", e)
        stop.wait(poll)


def main():
    config = _config_module.load()
    if not config.get("API_URL") or not config.get("API_KEY"):
        logger.critical("API_URL / API_KEY не задані в .env — агент не може стартувати")
        sys.exit(1)

    import storage as _storage
    try:
        _storage.init_db()
    except Exception as e:
        logger.error("init_db failed: %s", e)

    logger.info("=== SX Monitor Agent старт ===")
    logger.info("SERVER_ID=%s  API_URL=%s", config.get("SERVER_ID"), config.get("API_URL"))

    stop = threading.Event()
    threads = [
        threading.Thread(target=metrics_loop, args=(stop,), daemon=True, name="metrics"),
        threading.Thread(target=command_loop, args=(stop,), daemon=True, name="commands"),
    ]
    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Зупинка агента…")
        stop.set()


if __name__ == "__main__":
    main()
