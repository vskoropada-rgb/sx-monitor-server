"""
Disk fill forecast using ordinary least-squares linear regression.
Uses existing metric records (metric_name = disk_free_*) — no extra dependencies.

Прогноз заповнення дисків методом лінійної регресії (МНК).
Використовує наявні записи metrics (metric_name = disk_free_*) — без зовнішніх бібліотек.
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from models import Metric


def forecast_disk(db: Session, server_id: str, path_key: str,
                  hours_history: int = 48) -> Optional[dict]:
    """
    Return a forecast dict or None if there is insufficient data / disk is stable.
    Повертає dict з ETA або None якщо даних замало / диск не заповнюється.

    path_key: normalised disk key (e.g. 'C', 'D', 'E_backup')
    path_key: нормалізований ключ диска (напр. 'C', 'D', 'E_backup')

    Result / Результат:
    {
        "path_key": "C",
        "current_pct": 12.3,
        "eta_hours": 96,          # None if disk is stable / None якщо диск стабільний
        "eta_str": "4 дні",
        "rate_per_hour": -0.15    # % free per hour (negative = filling) / від'ємне = заповнюється
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
        return None   # not enough history for a reliable fit / замало даних для надійної регресії

    # Ordinary least squares (OLS) — pure stdlib, no numpy needed.
    # Звичайний МНК — тільки stdlib, numpy не потрібен.
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
        return None   # degenerate — all points at same time / вироджений — всі точки в одному часі

    slope = (n * sxy - sx * sy) / denom     # % free per hour / % вільного на годину
    intercept = (sy - slope * sx) / n
    current_elapsed = (datetime.utcnow() - t0).total_seconds() / 3600
    current_pct = intercept + slope * current_elapsed

    if slope >= 0:
        # Disk is freeing up or stable — no ETA needed.
        # Диск звільняється або стабільний — ETA не потрібен.
        return {
            "path_key": path_key,
            "current_pct": round(current_pct, 1),
            "eta_hours": None,
            "eta_str": None,
            "rate_per_hour": round(slope, 3),
        }

    # Project when free% reaches 0 / Проектуємо коли free% досягне 0%
    eta_hours = -current_pct / slope
    if eta_hours < 0 or eta_hours > 365 * 24:
        return None   # nonsensical result — too far or already past / безглуздий результат

    eta_str = _fmt_eta(eta_hours)
    return {
        "path_key": path_key,
        "current_pct": round(current_pct, 1),
        "eta_hours": round(eta_hours),
        "eta_str": eta_str,
        "rate_per_hour": round(slope, 3),
    }


def get_all_forecasts(db: Session, server_id: str) -> list:
    """Return forecasts for all disks with 48h history, sorted by urgency.
    Повертає прогнози для всіх дисків цього сервера (з даними за 48г), відсортовані за терміновістю."""
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
    # Disks filling fastest (smallest eta_hours) come first; stable last.
    # Диски що заповнюються найшвидше (найменший eta_hours) — першими; стабільні — останніми.
    return sorted(results, key=lambda x: x.get("eta_hours") or 9999)


def _fmt_eta(hours: float) -> str:
    """Human-readable ETA string in Ukrainian.
    Зрозумілий рядок ETA українською мовою."""
    if hours < 24:
        return f"{int(hours)} год"
    days = hours / 24
    if days < 7:
        return f"{days:.1f} дн"
    weeks = days / 7
    return f"{weeks:.1f} тиж"
