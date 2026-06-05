"""
collectors/disk.py — disk space monitoring with 1h and 24h delta tracking.
collectors/disk.py — моніторинг дискового простору з відстеженням δ за 1г та 24г.
"""
import psutil
import os
from storage import save_metric, get_metrics_history


def collect(config: dict) -> dict:
    """Return disk usage stats for each configured path.
    Повертає статистику використання диску для кожного налаштованого шляху."""
    paths = [p.strip() for p in config.get("DISK_PATHS", "C:\\").split(",")]
    results = []

    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            usage = psutil.disk_usage(path)
            free_pct = (usage.free / usage.total) * 100
            used_pct = usage.percent

            # Save metric for trend and forecast calculations.
            # Зберігаємо метрику для розрахунку тренду та прогнозу.
            # Backslash cannot appear in f-strings on Python 3.8 — use a variable.
            # Backslash не можна в f-string на Python 3.8 — використовуємо змінну.
            path_key = path.replace(':', '').replace('\\', '')
            metric_key = f"disk_{path_key}_free_pct"
            save_metric(metric_key, free_pct, {"path": path, "free_gb": round(usage.free / 1e9, 2)})

            # 1-hour delta / Динаміка за годину
            history = get_metrics_history(metric_key, hours=1)
            delta_1h = None
            if len(history) >= 2:
                delta_1h = round(history[-1]["value"] - history[0]["value"], 2)

            # 24-hour delta / Динаміка за 24 години
            history_24h = get_metrics_history(metric_key, hours=24)
            delta_24h = None
            if len(history_24h) >= 2:
                delta_24h = round(history_24h[-1]["value"] - history_24h[0]["value"], 2)

            results.append({
                "path": path,
                "free_pct": round(free_pct, 1),
                "used_pct": round(used_pct, 1),
                "free_gb": round(usage.free / 1e9, 2),
                "total_gb": round(usage.total / 1e9, 2),
                "delta_1h": delta_1h,
                "delta_24h": delta_24h,
            })
        except Exception as e:
            results.append({"path": path, "error": str(e)})

    return {"disks": results}
