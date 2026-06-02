"""
sla.py — розрахунок SLA / uptime по серверу за будь-який проміжок.
"""
import calendar
from datetime import datetime

from sqlalchemy.orm import Session

from models import UptimeEvent


def compute_sla(db: Session, server_id: str,
                start: datetime, end: datetime) -> dict:
    """
    Повертає {
        "server_id": ...,
        "start": ..., "end": ...,
        "uptime_pct": 99.8,
        "downtime_min": 45,
        "incidents": [{"from": ..., "to": ..., "duration_min": 20}, ...]
    }
    """
    total_sec = (end - start).total_seconds()
    if total_sec <= 0:
        return {
            "server_id": server_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "uptime_pct": 100.0,
            "downtime_min": 0,
            "incidents": [],
        }

    events = (
        db.query(UptimeEvent)
        .filter(
            UptimeEvent.server_id == server_id,
            UptimeEvent.at >= start,
            UptimeEvent.at <= end,
        )
        .order_by(UptimeEvent.at)
        .all()
    )

    # Стан до початку вікна: дивимось на останню подію перед start
    last_before = (
        db.query(UptimeEvent)
        .filter(UptimeEvent.server_id == server_id, UptimeEvent.at < start)
        .order_by(UptimeEvent.at.desc())
        .first()
    )
    initial_state = "online"
    offline_since = None
    if last_before and last_before.event == "offline":
        initial_state = "offline"
        offline_since = start   # відраховуємо простій від початку вікна

    incidents = []
    downtime_sec = 0

    for ev in events:
        if ev.event == "offline" and initial_state == "online":
            offline_since = ev.at
            initial_state = "offline"
        elif ev.event == "online" and initial_state == "offline" and offline_since:
            duration = (ev.at - offline_since).total_seconds()
            downtime_sec += duration
            incidents.append({
                "from": offline_since.isoformat(),
                "to":   ev.at.isoformat(),
                "duration_min": round(duration / 60),
            })
            offline_since = None
            initial_state = "online"

    # якщо досі offline — вважаємо простій до end
    if initial_state == "offline" and offline_since:
        duration = (end - offline_since).total_seconds()
        downtime_sec += duration
        incidents.append({
            "from": offline_since.isoformat(),
            "to":   end.isoformat(),
            "duration_min": round(duration / 60),
        })

    uptime_pct = round((1 - downtime_sec / total_sec) * 100, 3)
    return {
        "server_id":    server_id,
        "start":        start.isoformat(),
        "end":          end.isoformat(),
        "uptime_pct":   uptime_pct,
        "downtime_min": round(downtime_sec / 60),
        "incidents":    incidents,
    }


def compute_monthly_sla(db: Session, server_id: str, year: int, month: int) -> dict:
    """Зручний хелпер для місячного SLA."""
    _, last_day = calendar.monthrange(year, month)
    start = datetime(year, month, 1)
    end   = datetime(year, month, last_day, 23, 59, 59)
    now   = datetime.utcnow()
    if end > now:
        end = now
    return compute_sla(db, server_id, start, end)


def compute_weekly_sla(db: Session, server_id: str,
                       week_start: datetime, week_end: datetime) -> dict:
    """SLA за довільний тижневий проміжок."""
    now = datetime.utcnow()
    if week_end > now:
        week_end = now
    return compute_sla(db, server_id, week_start, week_end)
