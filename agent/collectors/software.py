"""
collectors/software.py — detect newly installed software via Windows registry.
collectors/software.py — виявлення нового встановленого ПЗ через реєстр Windows.

Reads both 64-bit and 32-bit (WOW64) Uninstall keys.
Читає як 64-bit, так і 32-bit (WOW64) ключі Uninstall.
"""
import winreg
import logging
import storage

logger = logging.getLogger(__name__)

# Registry paths that enumerate installed programs.
# Шляхи реєстру що перераховують встановлені програми.
_UNINSTALL_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
]


def _get_installed_software() -> set:
    """Read all DisplayName values from both Uninstall registry hives.
    Зчитує всі значення DisplayName з обох кущів реєстру Uninstall."""
    names = set()
    for hive, key_path in _UNINSTALL_KEYS:
        try:
            key = winreg.OpenKey(hive, key_path)
            count = winreg.QueryInfoKey(key)[0]
            for i in range(count):
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, subkey_name)
                    try:
                        name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                        if name and name.strip():
                            names.add(name.strip())
                    except (FileNotFoundError, OSError):
                        pass
                    winreg.CloseKey(subkey)
                except (FileNotFoundError, OSError):
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            logger.debug("Software registry read: %s", e)
    return names


def collect(config: dict) -> dict:
    """Return software titles installed since the last check.
    Повертає назви ПЗ, встановленого з останньої перевірки."""
    current = _get_installed_software()
    new_software = []

    for name in current:
        if not storage.is_known_software(name):
            storage.register_software(name)
            new_software.append(name)

    return {
        "new_software": new_software,
        "software_count": len(current),
    }
