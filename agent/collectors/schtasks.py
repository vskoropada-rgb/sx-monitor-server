"""
collectors/schtasks.py — detect newly created Task Scheduler tasks via Event ID 4698.
collectors/schtasks.py — виявлення нових завдань Task Scheduler через Event ID 4698.
"""
import logging
import storage

logger = logging.getLogger(__name__)

# System task prefixes — known-safe, always skipped.
# Системні префікси завдань — завжди безпечні, ігноруємо.
_SYSTEM_PREFIXES = ("\\Microsoft\\", "\\MicrosoftEdge", "\\OneDrive")

# Tasks created by this monitoring tool itself — not reported as suspicious.
# Завдання, що створює сам інструмент моніторингу — не повідомляємо як підозрілі.
_OWN_TASKS = {"1C_Monitor", "1C_Monitor_Bot", "1C_Monitor_Watchdog"}


def _is_system_task(name: str) -> bool:
    """True if the task belongs to a known-safe system or tool namespace.
    True якщо завдання належить до відомого безпечного системного простору імен."""
    if name in _OWN_TASKS:
        return True
    return any(name.startswith(p) for p in _SYSTEM_PREFIXES)


def _read_task_events() -> list:
    """Read the last 100 Event ID 4698 (task created) records from the Security log.
    Читає останні 100 Event ID 4698 (задача створена) з журналу Security."""
    try:
        import win32evtlog
        handle = win32evtlog.OpenEventLog(None, "Security")
        flags  = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        events = []

        while True:
            records = win32evtlog.ReadEventLog(handle, flags, 0)
            if not records:
                break
            for rec in records:
                if rec.EventID == 4698:
                    inserts = rec.StringInserts or []
                    # StringInserts[4] = TaskName in most Windows versions.
                    # StringInserts[4] = TaskName у більшості версій Windows.
                    task_name = inserts[4] if len(inserts) > 4 else (inserts[3] if len(inserts) > 3 else "")
                    user = inserts[1] if len(inserts) > 1 else ""
                    events.append({
                        "task_name": task_name.strip(),
                        "user": user,
                        "time": str(rec.TimeGenerated),
                    })
            if len(events) >= 100:
                break

        win32evtlog.CloseEventLog(handle)
        return events
    except Exception as e:
        logger.debug("Task Scheduler event read: %s", e)
        return []


def collect(config: dict) -> dict:
    """Return tasks that appeared in the event log but were not yet known.
    Повертає завдання, що з'явились в журналі подій і ще не були відомі."""
    events = _read_task_events()
    new_tasks = []

    for ev in events:
        name = ev.get("task_name", "")
        if not name or _is_system_task(name):
            continue
        if not storage.is_known_task(name):
            storage.register_task(name)
            new_tasks.append({"name": name, "user": ev.get("user", ""), "time": ev.get("time", "")})

    return {"new_scheduled_tasks": new_tasks}
