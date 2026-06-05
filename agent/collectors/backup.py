"""
collectors/backup.py — backup monitoring: archive integrity, schedule adherence, size trend.
collectors/backup.py — перевірка бекапів: цілісність, розклад, тренд розміру.

Searches for zip/rar/7z archives by default. RAR requires the 'rarfile' package
+ unrar/bsdtar in PATH. Extend formats via BACKUP_EXTENSIONS=zip,rar,7z,bak,dt,1cd in .env.

За замовчуванням шукає zip/rar/7z. Для RAR потрібен `rarfile` + unrar/bsdtar у PATH.
Розширити формати можна через BACKUP_EXTENSIONS=zip,rar,7z,bak,dt,1cd у .env.
"""
from __future__ import annotations

import glob
import logging
import os
import zipfile
from datetime import datetime, timedelta
from typing import Optional

import storage

logger = logging.getLogger(__name__)

_DEFAULT_EXTS = ("zip", "rar", "7z")
_MIN_VALID_SIZE = 1024  # bytes — smaller files are treated as "too_small" / байтів


# ─── Integrity checks / Перевірка цілісності ─────────────────────────────────


def _check_zip(filepath: str, password: Optional[str]) -> str:
    """Return 'ok' | 'encrypted' | 'corrupted' | 'too_small' for a ZIP archive.
    Повертає 'ok' | 'encrypted' | 'corrupted' | 'too_small' для ZIP-архіву."""
    if os.path.getsize(filepath) <= _MIN_VALID_SIZE:
        return "too_small"
    try:
        with zipfile.ZipFile(filepath) as zf:
            is_encrypted = any(info.flag_bits & 0x1 for info in zf.infolist())
            if is_encrypted:
                if not password:
                    return "encrypted"
                zf.setpassword(password.encode())
            try:
                bad = zf.testzip()
                return "ok" if bad is None else "corrupted"
            except RuntimeError as e:
                msg = str(e).lower()
                if "password" in msg or "encrypted" in msg:
                    return "encrypted"
                return "corrupted"
    except zipfile.BadZipFile:
        return "corrupted"
    except Exception as e:
        logger.debug("check_zip(%s): %s", filepath, e)
        return "error"


def _size_ok(filepath: str, min_size_mb: float = 1.0) -> bool:
    return os.path.getsize(filepath) >= min_size_mb * 1_000_000


def _check_rar(filepath: str, password: Optional[str]) -> str:
    """Check RAR integrity via header parsing (Python-only, no external tools).
    Перевіряє цілісність RAR через парсинг заголовків (Python-only, без зовнішніх утиліт).

    testrar() is NOT called to avoid false-positive 'corrupted' results when
    unrar/bsdtar is absent.
    testrar() НЕ викликається щоб уникнути false-positive 'corrupted' при відсутності unrar.
    """
    if os.path.getsize(filepath) <= _MIN_VALID_SIZE:
        return "too_small"

    try:
        import rarfile
        # Read headers only — pure Python, no external tool needed.
        # Читаємо тільки заголовки — чистий Python, unrar не потрібен.
        with rarfile.RarFile(filepath) as rf:
            if rf.needs_password():
                if not password:
                    return "encrypted"
                rf.setpassword(password)
        return "ok"
    except ImportError:
        pass  # library absent — fall through to size check / бібліотека відсутня
    except Exception as e:
        msg = str(e).lower()
        if "password" in msg or "encrypted" in msg:
            return "encrypted"
        # Cannot read headers but file is large — don't call it corrupted.
        # Не можемо прочитати заголовки, але файл великий → не вважаємо пошкодженим.
        logger.debug("check_rar header(%s): %s", filepath, e)

    return "ok" if _size_ok(filepath) else "too_small"


def _check_archive(filepath: str, password: Optional[str]) -> str:
    """Dispatch to the appropriate integrity checker based on file extension.
    Делегує перевірку цілісності залежно від розширення файлу."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".zip":
        return _check_zip(filepath, password)
    if ext == ".rar":
        return _check_rar(filepath, password)
    # 7z/bak/dt/1cd — without a library only size can be verified.
    # 7z/bak/dt/1cd — без бібліотеки можемо перевірити тільки розмір.
    return "too_small" if os.path.getsize(filepath) <= _MIN_VALID_SIZE else "ok"


# ─── Main collector / Основна функція ────────────────────────────────────────


def collect(config: dict) -> dict:
    """Collect backup status: latest file, integrity, schedule compliance, file list.
    Збирає статус бекапів: останній файл, цілісність, відповідність розкладу, список файлів."""
    backup_path   = config.get("BACKUP_PATH", "")
    max_age_hours = int(config.get("BACKUP_MAX_AGE_HOURS", 25))
    min_size_mb   = float(config.get("BACKUP_MIN_SIZE_MB", 10))
    zip_password  = config.get("BACKUP_ZIP_PASSWORD", "") or None

    # Backup window: WINDOW_START–WINDOW_END hours; deadline = WINDOW_END + GRACE_HOURS.
    # Вікно бекапів: WINDOW_START–WINDOW_END; дедлайн = WINDOW_END + GRACE_HOURS.
    win_start     = int(config.get("BACKUP_WINDOW_START", 0))
    win_end       = int(config.get("BACKUP_WINDOW_END", 5))
    grace_hours   = int(config.get("BACKUP_GRACE_HOURS", 3))
    deadline_hour = win_end + grace_hours
    schedule_info = f"вікно {win_start:02d}:00–{win_end:02d}:00, дедлайн {deadline_hour:02d}:00"

    if not backup_path or not os.path.exists(backup_path):
        return {
            "status": "error",
            "error":  f"Папка бекапів не знайдена: {backup_path}",
            "backup_path": backup_path,
        }

    raw_exts = config.get("BACKUP_EXTENSIONS", "")
    exts = [e.strip().lstrip("*.") for e in raw_exts.split(",") if e.strip()] or list(_DEFAULT_EXTS)

    all_files = []
    for ext in exts:
        all_files.extend(glob.glob(os.path.join(backup_path, f"*.{ext}")))

    now          = datetime.now()
    today_window = now.replace(hour=win_start, minute=0, second=0, microsecond=0)

    if not all_files:
        schedule_missed = now.hour >= deadline_hour
        if schedule_missed:
            return {
                "status":         "warning",
                "issues":         [f"Бекапів не знайдено ({schedule_info})"],
                "backup_path":    backup_path,
                "schedule_missed": True,
                "schedule_info":  schedule_info,
            }
        return {
            "status":     "no_files",
            "backup_path": backup_path,
            "error":      "Файли бекапів не знайдені (zip/rar/7z/bak/dt/1cd)",
        }

    # Use mtime (actual write time) not detection time.
    # Ignore files ≤ 1 KB (script markers/metadata) if larger archives exist.
    # Використовуємо mtime (реальний час запису), не час виявлення.
    # Ігноруємо файли ≤ 1KB (маркери від скриптів) якщо є більші архіви.
    real_files = [f for f in all_files if os.path.getsize(f) > _MIN_VALID_SIZE]
    latest_file       = max(real_files if real_files else all_files, key=os.path.getmtime)
    latest_mtime      = datetime.fromtimestamp(os.path.getmtime(latest_file))
    latest_size_bytes = os.path.getsize(latest_file)
    latest_size_mb    = round(latest_size_bytes / 1e6, 2)
    age_hours         = round((now - latest_mtime).total_seconds() / 3600, 1)

    # Register new files + re-check files with uncertain integrity status.
    # Реєструємо нові файли + повторно перевіряємо ті у яких статус "невпевнений".
    latest_integrity = "unknown"
    for f in all_files:
        fname = os.path.basename(f)
        if not storage.is_known_backup(fname):
            size  = os.path.getsize(f)
            mtime = datetime.fromtimestamp(os.path.getmtime(f))
            integ = _check_archive(f, zip_password)
            storage.record_backup(fname, size, mtime.isoformat(), integ)
            logger.info("Новий бекап: %s (%sMB) — %s", fname, round(size/1e6, 1), integ)
            if f == latest_file:
                latest_integrity = integ
        elif f == latest_file:
            stored = storage.get_backup_integrity(fname)
            if stored in ("corrupted", "error", "unknown", "too_small"):
                # too_small may be recorded while the file is still being written — re-check.
                # too_small може бути записаний поки файл ще писався — перевіряємо знову.
                integ = _check_archive(f, zip_password)
                if integ != stored:
                    storage.update_backup_integrity(fname, integ)
                    logger.info("Оновлено цілісність %s: %s → %s", fname, stored, integ)
                latest_integrity = integ
            else:
                latest_integrity = stored or "ok"

    # Build the file list for the UI (sorted newest-first, capped at 30).
    # Список файлів для UI (сортування від нового до старого, ліміт 30).
    recent_files = []
    for f in all_files:
        mtime = datetime.fromtimestamp(os.path.getmtime(f))
        recent_files.append({
            "name":      os.path.basename(f),
            "size_mb":   round(os.path.getsize(f) / 1e6, 2),
            "age_hours": round((now - mtime).total_seconds() / 3600, 1),
            "time":      mtime.strftime("%Y-%m-%d %H:%M"),
        })
    recent_files.sort(key=lambda x: x["age_hours"])

    # Determine whether we expect a backup from today's or yesterday's window.
    # Before the deadline: yesterday's backup is still acceptable.
    # Визначаємо чи очікуємо бекап з сьогоднішнього або вчорашнього вікна.
    # До дедлайну: вчорашній бекап ще прийнятний (вікно могло не закритись).
    if now.hour >= deadline_hour:
        expected_after = today_window
    else:
        expected_after = today_window - timedelta(days=1)

    is_fresh        = latest_mtime >= expected_after
    schedule_missed = now.hour >= deadline_hour and not is_fresh

    issues = []
    status = "ok"

    if latest_integrity == "corrupted":
        status = "critical"
        issues.append("Архів пошкоджений!")
    elif latest_integrity == "too_small":
        status = "warning"
        issues.append("Архів менше 1 KB — можливо порожній")
    elif latest_integrity == "encrypted":
        issues.append("Архів зашифрований (цілісність без пароля не перевірена)")

    if latest_size_mb < min_size_mb and latest_integrity not in ("corrupted", "too_small"):
        if status == "ok":
            status = "warning"
        issues.append(f"Розмір {latest_size_mb}MB менше мінімуму {min_size_mb}MB")

    if age_hours > max_age_hours:
        if status == "ok":
            status = "warning"
        issues.append(f"Останній бекап {age_hours}г тому (ліміт {max_age_hours}г)")

    if schedule_missed:
        if status == "ok":
            status = "warning"
        issues.append(f"Відсутній свіжий бекап ({schedule_info})")

    return {
        "status":            status,
        "issues":            issues,
        "latest_file":       os.path.basename(latest_file),
        "latest_size_mb":    latest_size_mb,
        "latest_size_bytes": latest_size_bytes,
        "latest_age_hours":  age_hours,
        "latest_time":       latest_mtime.strftime("%Y-%m-%d %H:%M"),
        "latest_integrity":  latest_integrity,
        "recent_files":      recent_files[:30],
        "total_files":       len(all_files),
        "backup_path":       backup_path,
        "schedule_info":     schedule_info,
        "schedule_missed":   schedule_missed,
        "is_fresh":          is_fresh,
    }
