"""
collectors/winupdate.py — check whether Windows requires a reboot after updates.
collectors/winupdate.py — перевірка очікуваного перезавантаження Windows після оновлень.

Reads two registry keys that Windows sets when a reboot is pending:
- WindowsUpdate\Auto Update\RebootRequired
- Component Based Servicing\RebootPending

Читає два ключі реєстру, які Windows встановлює при очікуваному перезавантаженні.
"""
import winreg
import logging

logger = logging.getLogger(__name__)

# Registry keys whose presence (regardless of value) signals a pending reboot.
# Ключі реєстру, наявність яких (незалежно від значення) сигналізує про перезавантаження.
_REBOOT_KEYS = [
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending",
]


def collect(config: dict) -> dict:
    """Return reboot_required flag and which registry keys triggered it.
    Повертає прапор reboot_required та які ключі реєстру його викликали."""
    reboot_required = False
    reasons = []

    for key_path in _REBOOT_KEYS:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            winreg.CloseKey(key)
            reboot_required = True
            # Use only the last path segment as a human-readable reason label.
            # Використовуємо лише останній сегмент шляху як зрозумілу мітку причини.
            reasons.append(key_path.split("\\")[-1])
        except FileNotFoundError:
            pass   # key absent — no reboot pending / ключ відсутній — перезавантаження не потрібне
        except Exception as e:
            logger.debug("winupdate registry read: %s", e)

    return {
        "reboot_required": reboot_required,
        "reboot_reasons": reasons,
    }
