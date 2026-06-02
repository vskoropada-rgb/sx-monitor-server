"""
disk_forecast.py — прогноз заповнення дисків методом лінійної регресії.
Використовує наявні записи metrics (metric_name = disk_free_*).
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from models import Metric


def forecast_disk(db: Session, server_id: str, path_key: str,
                  hours_history: int = 48) -> Optional[dict]:
    """
    Повертає dict з ETA або None якщо даних замало / диск не заповнюється.

    path_key: нормалізований ключ диска (напр. 'C', 'D', 'E_backup')
    Результат: {
        "path_key": "C",
        "current_pct": 12.3,
        "eta_hours": 96,          # None якщо диск не заповнюється
        "eta_str": "4 дні",
        "rate_per_hour": -0.15    # % вільного на годину (від'ємне = заповнюється)
    }
    """
    metric_name = f"disk_free_{path_key}"
    cutoff = datetime.utcnow() - timedelta(hours=hours_history)

    rows = (
        db.query(Metric.recorded_at, Metric.value)
        .filter(
            Metric.server_id == server_id,
            Metric.metric_name == metric_name,
            Metric.recorded_at >= cutoff,
        )
        .order_by(Metric.recorded_at)
        .all()
    )
    if len(rows) < 6:
        return None

    # Лінійна регресія (МНК) без зовнішніх бібліотек
    t0 = rows[0].recorded_at
    xs = [(r.recorded_at - t0).total_seconds() / 3600 for r in rows]
    ys = [r.value for r in rows]
    n = len(xs)
    sx = sum(xs)
    sy = sum(ys)
    sxy = sum(x * y for x, y in zip(xs, ys))
    sxx = sum(x * x for x in xs)
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-9:
        return None

    slope = (n * sxy - sx * sy) / denom     # % вільного на годину
    intercept = (sy - slope * sx) / n
    current_elapsed = (datetime.utcnow() - t0).total_seconds() / 3600
    current_pct = intercept + slope * current_elapsed

    if slope >= 0:
        # диск звільняється або стабільний — не треба ETA
        return {
            "path_key": path_key,
            "current_pct": round(current_pct, 1),
            "eta_hours": None,
            "eta_str": None,
            "rate_per_hour": round(slope, 3),
        }

    # ETA коли вільно стане 0%
    eta_hours = -current_pct / slope
    if eta_hours < 0 or eta_hours > 365 * 24:
        return None

    eta_str = _fmt_eta(eta_hours)
    return {
        "path_key": path_key,
        "current_pct": round(current_pct, 1),
        "eta_hours": round(eta_hours),
        "eta_str": eta_str,
        "rate_per_hour": round(slope, 3),
    }


def get_all_forecasts(db: Session, server_id: str) -> list:
    """Повертає прогнози для всіх дисків цього сервера (з даними за 48г)."""
    names = db.execute(
        text(
            "SELECT DISTINCT metric_name FROM metrics "
            "WHERE server_id=:s AND metric_name LIKE 'disk_free_%'"
        ),
        {"s": server_id},
    ).fetchall()
    results = []
    for (name,) in names:
        path_key = name[len("disk_free_"):]
        fc = forecast_disk(db, server_id, path_key)
        if fc:
            results.append(fc)
    return sorted(results, key=lambda x: x.get("eta_hours") or 9999)


def _fmt_eta(hours: float) -> str:
    if hours < 24:
        return f"{int(hours)} год"
    days = hours / 24
    if days < 7:
        return f"{days:.1f} дн"
    weeks = days / 7
    return f"{weeks:.1f} тиж"
