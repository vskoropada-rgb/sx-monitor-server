"""
collectors/memory.py — моніторинг CPU та RAM
"""
import psutil
import time
from storage import save_metric


def collect(config: dict) -> dict:
    # CPU — вимірюємо без блокування: psutil накопичує різницю з попереднього виклику.
    # Перший виклик після старту повертає 0.0, всі наступні — середнє за інтервал опитування.
    cpu_pct = psutil.cpu_percent(interval=None)
    cpu_count = psutil.cpu_count()
    cpu_freq = psutil.cpu_freq()

    # RAM
    ram = psutil.virtual_memory()
    ram_used_pct = ram.percent
    ram_free_gb = round(ram.available / 1e9, 2)
    ram_total_gb = round(ram.total / 1e9, 2)

    # Swap
    swap = psutil.swap_memory()

    # Топ процеси по CPU — обгортаємо в try/except, щоб помилки доступу до системних
    # процесів (AccessDenied, NoSuchProcess) не обривали збір основних метрик.
    top_cpu = []
    try:
        procs = []
        for proc in psutil.process_iter(["name", "cpu_percent", "memory_percent"]):
            try:
                procs.append({
                    "name": proc.info["name"],
                    "cpu_pct": round(proc.info["cpu_percent"] or 0, 1),
                    "ram_pct": round(proc.info["memory_percent"] or 0, 1),
                })
            except Exception:
                pass
        top_cpu = sorted(procs, key=lambda p: p["cpu_pct"], reverse=True)[:5]
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug("top_processes: %s", e)

    # Зберігаємо метрики
    save_metric("cpu_percent", cpu_pct)
    save_metric("ram_percent", ram_used_pct, {"free_gb": ram_free_gb})

    return {
        "cpu": {
            "percent": cpu_pct,
            "count": cpu_count,
            "freq_mhz": round(cpu_freq.current) if cpu_freq else None,
        },
        "ram": {
            "percent": ram_used_pct,
            "free_gb": ram_free_gb,
            "total_gb": ram_total_gb,
        },
        "swap": {
            "percent": swap.percent,
            "used_gb": round(swap.used / 1e9, 2),
        },
        "top_processes": top_cpu,
    }
