"""
collectors/security.py — security monitoring: brute-force detection, new admins,
file integrity checks.
collectors/security.py — безпека: перебір паролів, нові адміни, зміни файлів.
"""
import logging
import re
import win32evtlog
import win32evtlogutil
import win32con
import hashlib
import os
import ipaddress
from datetime import datetime, timedelta
from collections import defaultdict
from storage import (get_known_admins, add_known_admin,
                     get_file_hash, update_file_hash)

logger = logging.getLogger(__name__)

_IP_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
# IPs that should never be treated as attacker addresses.
# IP-адреси, які ніколи не слід вважати адресами атакуючих.
_BAD_IPS = {"-", "", "::1", "127.0.0.1", "0.0.0.0"}


def _get_events(source: str, event_ids: list, minutes: int = 10) -> list:
    """Read events from the Windows Event Log for the last N minutes.
    Читає події з Windows Event Log за останні N хвилин."""
    events = []
    try:
        hand = win32evtlog.OpenEventLog(None, source)
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        cutoff = datetime.now() - timedelta(minutes=minutes)

        while True:
            records = win32evtlog.ReadEventLog(hand, flags, 0)
            if not records:
                break
            for rec in records:
                try:
                    event_time = datetime(*rec.TimeGenerated.timetuple()[:6])
                    if event_time < cutoff:
                        raise StopIteration
                    if rec.EventID & 0xFFFF in event_ids:
                        events.append(rec)
                except StopIteration:
                    win32evtlog.CloseEventLog(hand)
                    return events
        win32evtlog.CloseEventLog(hand)
    except Exception as e:
        logger.warning("_get_events(%s) failed: %s", source, e)
    return events


def _extract_ip_from_strings(strings: list, event_id: int) -> str:
    """Extract an IP address from StringInserts for various event types.
    Вилучає IP з StringInserts різних типів подій.

    Checks known field indices first, then scans all fields as a fallback.
    Спочатку перевіряє відомі індекси, потім сканує всі поля як fallback.
    """
    if not strings:
        return "unknown"

    def _clean(s: str) -> str:
        return s.replace("::ffff:", "").strip()

    candidates = []
    if event_id == 4625:
        # Field 19 = IpAddress, field 13 = WorkstationName (fallback)
        for idx in (19, 13):
            if idx < len(strings) and strings[idx]:
                candidates.append(_clean(strings[idx]))
    elif event_id == 4771:
        # Field 6 = Client Address (may be ::ffff:1.2.3.4)
        if len(strings) > 6 and strings[6]:
            candidates.append(_clean(strings[6]))

    # Prefer the known-index candidates / Перевіряємо відомі індекси першими
    for c in candidates:
        if c and c not in _BAD_IPS and _IP_RE.match(c):
            return c

    # Fallback: scan all StringInserts for any public IP.
    # Fallback: сканує всі StringInserts в пошуку будь-якого публічного IP.
    for s in strings:
        if not s:
            continue
        c = _clean(s)
        if c not in _BAD_IPS and _IP_RE.match(c):
            logger.debug("_extract_ip fallback found IP %r in strings: %s", c,
                         [str(x)[:30] if x else None for x in strings])
            return c

    # Last resort — first candidate without IP format check.
    # Останній шанс — перший кандидат без перевірки формату.
    if candidates:
        c = candidates[0]
        if c and c not in _BAD_IPS:
            return c

    return "unknown"


def _get_rdp_connection_ips(window_min: int) -> dict:
    """Count RDP connection attempts per source IP via Event 1149.
    Рахує RDP-підключення по IP джерела через Event 1149.

    Reads the modern channel
    Microsoft-Windows-TerminalServices-RemoteConnectionManager/Operational
    (needs the EvtQuery API — the legacy ReadEventLog cannot read it). Event
    1149's Param3 is the client source address. Legitimate users connect once
    or twice; an IP with many connections in the window is brute-forcing. This
    recovers the attacker IP even when 4625 logs the failure without one.

    Читає сучасний канал TerminalServices-RemoteConnectionManager/Operational
    (потрібен EvtQuery, legacy ReadEventLog його не бачить). Param3 події 1149 —
    IP джерела. Відновлює IP атакуючого навіть коли 4625 його не містить.
    """
    counts: defaultdict = defaultdict(int)
    try:
        import win32evtlog
    except ImportError:
        return counts

    channel = ("Microsoft-Windows-TerminalServices-"
               "RemoteConnectionManager/Operational")
    ms = int(window_min) * 60 * 1000
    query = (f"*[System[(EventID=1149) and "
             f"TimeCreated[timediff(@SystemTime) <= {ms}]]]")
    try:
        h = win32evtlog.EvtQuery(
            channel,
            win32evtlog.EvtQueryChannelPath | win32evtlog.EvtQueryReverseDirection,
            query,
        )
    except Exception as e:
        logger.debug("1149 EvtQuery failed (%s): %s", channel, e)
        return counts

    processed = 0
    try:
        while processed < 3000:   # safety cap under heavy floods / запобіжник
            try:
                events = win32evtlog.EvtNext(h, 50)
            except Exception:
                break
            if not events:
                break
            for ev in events:
                processed += 1
                try:
                    xml = win32evtlog.EvtRender(ev, win32evtlog.EvtRenderEventXml)
                    m = re.search(r"<Param3>([^<]+)</Param3>", xml)
                    if not m:
                        continue
                    ip = m.group(1).replace("::ffff:", "").strip()
                    if ip and ip not in _BAD_IPS and (_IP_RE.match(ip) or ":" in ip):
                        counts[ip] += 1
                except Exception:
                    continue
    finally:
        try:
            win32evtlog.EvtClose(h)
        except Exception:
            pass

    return counts


def collect_brute_force(config: dict) -> dict:
    """Detect password brute-force via 4625 (NTLM) + 4771 (Kerberos) + RDP 1149.
    Виявляє перебір паролів через 4625 (NTLM) + 4771 (Kerberos) + RDP 1149."""
    window_min = int(config.get("BRUTE_FORCE_WINDOW_MIN", 10))
    threshold = int(config.get("BRUTE_FORCE_THRESHOLD", 5))
    local_threshold = int(config.get("BRUTE_FORCE_LOCAL_THRESHOLD", 20))
    known_networks_str = config.get("KNOWN_IPS", "192.168.1.0/24")

    known_networks = []
    for net in known_networks_str.split(","):
        try:
            known_networks.append(ipaddress.ip_network(net.strip(), strict=False))
        except Exception:
            pass

    events = _get_events("Security", [4625, 4771], minutes=window_min)
    ip_attempts    = defaultdict(list)
    ip_workstations = defaultdict(set)  # ip → workstation names / ip → назви пристроїв

    for rec in events:
        try:
            strings = rec.StringInserts or []
            event_id = rec.EventID & 0xFFFF
            ip = _extract_ip_from_strings(strings, event_id)
            if event_id == 4625:
                username    = strings[5].strip() if len(strings) > 5  and strings[5]  else "unknown"
                workstation = strings[13].strip() if len(strings) > 13 and strings[13] else ""
                if workstation and workstation not in ("-", "", "–"):
                    ip_workstations[ip].add(workstation)
            else:  # 4771 Kerberos
                username = strings[0].strip() if strings and strings[0] else "unknown"
            ip_attempts[ip].append(username)
            logger.debug("brute_force event %d: ip=%r user=%r strings_len=%d",
                         event_id, ip, username, len(strings))
        except Exception as e:
            logger.warning("brute_force parse error: %s", e)

    logger.info("brute_force: зібрано %d подій (4625+4771) за %d хв, унікальних IP: %d, розподіл: %s",
                len(events), window_min, len(ip_attempts),
                {ip: len(u) for ip, u in ip_attempts.items()})

    # Aggregate failed logins per source IP; keep local (no-IP) failures apart.
    # Then fold in RDP connection floods (Event 1149), which recover the source
    # IP when 4625 logs the failure without one (the FASADE case).
    # Агрегуємо невдалі входи по IP; локальні (без IP) — окремо. Далі додаємо
    # RDP-підключення з Event 1149 — вони відновлюють IP, коли 4625 його не має.
    combined: dict = {}   # ip -> {"count", "users": set, "wks": set, "is_known"}
    local_failed = 0
    local_users: list = []

    def _note(ip: str, cnt: int, users, wks) -> None:
        if not ip or ip in _BAD_IPS:
            return
        try:
            is_known = any(ipaddress.ip_address(ip) in n for n in known_networks)
        except ValueError:
            return
        e = combined.get(ip)
        if e is None:
            combined[ip] = {"count": cnt, "users": set(users),
                            "wks": set(wks), "is_known": is_known}
        else:
            e["count"] = max(e["count"], cnt)   # strongest signal across sources
            e["users"].update(users)
            e["wks"].update(wks)

    for ip, users in ip_attempts.items():
        if ip in ("unknown", "", "-"):
            local_failed += len(users)
            local_users.extend(users)
            continue
        _note(ip, len(users), users, ip_workstations.get(ip, set()))

    # Event 1149 — RDP connection attempts per source IP (recovers no-IP 4625).
    # Event 1149 — RDP-підключення по IP (відновлює IP, якого нема в 4625).
    for ip, cnt in _get_rdp_connection_ips(window_min).items():
        _note(ip, cnt, [], [])

    alerts = []
    suspicious_ips = []  # real external IPs only / лише реальні зовнішні IP
    for ip, e in combined.items():
        entry = {
            "ip": ip,
            "count": e["count"],
            "usernames": list(e["users"])[:5],
            "workstations": list(e["wks"])[:3],
            "is_known_network": e["is_known"],
        }
        if e["count"] >= threshold:
            alerts.append(entry)
        if not e["is_known"]:            # external → eligible for auto-block
            suspicious_ips.append(entry)

    # Local (no-IP) failures still alert when very high — nothing to block.
    # Локальні (без IP) — алерт при дуже великій кількості, блокувати нема кого.
    if local_failed >= local_threshold:
        alerts.append({
            "ip": "",
            "count": local_failed,
            "usernames": list(dict.fromkeys(local_users))[:5],
            "workstations": [],
            "is_known_network": True,
        })

    alerts.sort(key=lambda x: x["count"], reverse=True)
    suspicious_ips.sort(key=lambda x: x["count"], reverse=True)

    return {
        "brute_force_alerts": alerts,
        "suspicious_ips": suspicious_ips[:5],
        "total_failed_logins": len(events),
        "local_failed_logins": local_failed,
        "window_min": window_min,
    }


def collect_new_admins(config: dict) -> dict:
    """Detect additions to the Administrators group via Event ID 4732.
    Виявляє додавання до групи Administrators через Event ID 4732."""
    events = _get_events("Security", [4732], minutes=int(config.get("CHECK_INTERVAL_SEC", 60)) // 60 + 1)
    known = get_known_admins()
    new_admins = []

    for rec in events:
        try:
            strings = rec.StringInserts
            if strings and len(strings) > 2:
                added_user = strings[0].strip()
                added_by = strings[4].strip() if len(strings) > 4 else "unknown"
                group = strings[2].strip() if len(strings) > 2 else ""

                if "Administrator" in group or "Администрат" in group:
                    if added_user not in known:
                        new_admins.append({
                            "username": added_user,
                            "added_by": added_by,
                            "group": group,
                            "time": str(rec.TimeGenerated),
                        })
                        add_known_admin(added_user)
        except Exception:
            pass

    # Bootstrap known admins on the very first run to avoid false-positive alerts.
    # Ініціалізуємо відомих адмінів при першому запуску щоб уникнути хибних алертів.
    if not known:
        _bootstrap_known_admins()

    return {"new_admins": new_admins}


def _bootstrap_known_admins() -> None:
    """
    On first run, seed the known-admins table from 'net localgroup Administrators'
    to prevent false-positive new-admin alerts. Parses en/ru Windows output
    carefully — skips headers, separators, and system lines.

    При першому запуску наповнює таблицю відомих адмінів з
    'net localgroup Administrators' щоб уникнути false-positive алертів.
    Обережно парсить en/ru вивід — пропускає заголовки, рамки, службові рядки.
    """
    import subprocess
    try:
        result = subprocess.run(
            ["net", "localgroup", "Administrators"],
            capture_output=True, text=True, encoding="cp866", timeout=15,
        )
    except Exception as e:
        # Russian locale may use a different group name.
        # Російська локаль може мати іншу назву групи.
        try:
            result = subprocess.run(
                ["net", "localgroup", "Администраторы"],
                capture_output=True, text=True, encoding="cp866", timeout=15,
            )
        except Exception as e2:
            return

    _SKIP_PREFIXES = (
        "alias name", "comment", "members",     # en
        "псевдоним", "комментарий", "члены",    # ru
    )
    _SKIP_KEYWORDS = (
        "completed successfully",   # en
        "выполнена успешно",        # ru
    )

    for raw in result.stdout.splitlines():
        line = raw.strip()
        if not line or line.startswith("-"):
            continue
        low = line.lower()
        if any(low.startswith(p) for p in _SKIP_PREFIXES):
            continue
        if any(kw in low for kw in _SKIP_KEYWORDS):
            continue

        # Domain entries: "BUILTIN\Administrators" — take only the part after the last backslash.
        # Доменні записи: "BUILTIN\Administrators" — беремо лише після останнього '\'.
        if "\\" in line:
            line = line.rsplit("\\", 1)[-1]

        if line:
            add_known_admin(line)


def collect_file_changes(config: dict) -> dict:
    """Compare SHA-256 hashes of watched files to detect modifications.
    Порівнює SHA-256 хеші відслідковуваних файлів для виявлення змін."""
    watch_files = [f.strip() for f in config.get(
        "WATCH_FILES",
        r"C:\Windows\System32\drivers\etc\hosts"
    ).split(",")]

    changed_files = []

    for file_path in watch_files:
        if not os.path.exists(file_path):
            continue
        try:
            with open(file_path, "rb") as f:
                current_hash = hashlib.sha256(f.read()).hexdigest()

            stored_hash = get_file_hash(file_path)

            if stored_hash is None:
                # First run — record baseline hash. No alert.
                # Перший запуск — записуємо еталонний хеш. Без алерту.
                update_file_hash(file_path, current_hash)
            elif stored_hash != current_hash:
                changed_files.append({
                    "path": file_path,
                    "old_hash": stored_hash[:16] + "...",
                    "new_hash": current_hash[:16] + "...",
                    "size_bytes": os.path.getsize(file_path),
                    "modified": datetime.fromtimestamp(
                        os.path.getmtime(file_path)
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                })
                update_file_hash(file_path, current_hash)
        except Exception:
            pass

    return {"changed_files": changed_files}


def collect(config: dict) -> dict:
    """Run all security sub-collectors and merge results.
    Запускає всі підзбирачі безпеки і об'єднує результати."""
    result = {}
    result.update(collect_brute_force(config))
    result.update(collect_new_admins(config))
    result.update(collect_file_changes(config))
    return result
