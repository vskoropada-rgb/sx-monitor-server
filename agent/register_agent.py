"""
register_agent.py — одноразова реєстрація агента на центральному сервері.

Генерує API_KEY, реєструє сервер у БД центрального сервера і записує ключ
у .env (зашифрованим DPAPI, якщо доступно).

Запуск (на Windows-сервері, від адміністратора):
    python register_agent.py

Потрібно щоб у .env уже були: SERVER_ID, COMPANY_NAME, API_URL, TG_TOPIC_ID (опц.)
"""
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

import config as _config_module

try:
    import requests
except ImportError:
    print("Встановіть requests: pip install requests")
    sys.exit(1)

ENV_PATH = Path(__file__).parent / ".env"


def _encrypt_dpapi(value: str) -> str:
    """Шифрує значення DPAPI (LocalMachine). Якщо не Windows — повертає як є."""
    try:
        import base64, ctypes, ctypes.wintypes

        CRYPTPROTECT_LOCAL_MACHINE = 0x4

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", ctypes.wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char)),
            ]

        data = value.encode("utf-8")
        buf = ctypes.create_string_buffer(data, len(data))
        inp = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        out = DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(inp), None, None, None, None,
            CRYPTPROTECT_LOCAL_MACHINE, ctypes.byref(out),
        )
        if not ok:
            raise OSError("CryptProtectData failed")
        enc = ctypes.string_at(out.pbData, out.cbData)
        ctypes.windll.kernel32.LocalFree(out.pbData)
        return "ENCRYPTED:" + base64.b64encode(enc).decode("ascii")
    except Exception:
        return value  # не-Windows або помилка — кладемо як є


def _update_env_key(key: str, value: str):
    """Записує/оновлює рядок KEY=value у .env."""
    lines = []
    found = False
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    config = _config_module.load()
    server_id = config.get("SERVER_ID")
    name      = config.get("COMPANY_NAME") or server_id
    api_url   = config.get("API_URL")
    topic_id  = config.get("TG_TOPIC_ID") or None

    if not server_id or not api_url:
        print("Помилка: у .env мають бути SERVER_ID та API_URL")
        sys.exit(1)

    # Якщо ключ уже є — не перезаписуємо без потреби
    existing = os.getenv("API_KEY", "")
    api_key = config.get("API_KEY") or secrets.token_urlsafe(32)

    # Секрет реєстрації (REGISTER_SECRET сервера). Не зберігається — лише разовий ввід.
    register_secret = os.getenv("REGISTER_SECRET", "").strip()
    if not register_secret:
        register_secret = input("REGISTER_SECRET (з .env сервера): ").strip()
    if not register_secret:
        print("Помилка: потрібен REGISTER_SECRET")
        sys.exit(1)

    payload = {
        "server_id": server_id,
        "name": name,
        "api_key": api_key,
        "tg_topic_id": topic_id,
    }

    url = api_url.rstrip("/") + "/api/servers/register"
    print(f"Реєструю '{name}' ({server_id}) на {url} …")
    r = requests.post(url, json=payload,
                      headers={"X-Register-Secret": register_secret}, timeout=15)
    if r.status_code != 200:
        print(f"Помилка реєстрації: {r.status_code} {r.text}")
        sys.exit(1)

    print(f"OK: {r.json()}")

    if not existing:
        _update_env_key("API_KEY", _encrypt_dpapi(api_key))
        print("API_KEY збережено в .env (зашифровано).")
    else:
        print("API_KEY уже був у .env — лишаю без змін.")

    print("\nГотово. Запускайте агента:  python agent.py")


if __name__ == "__main__":
    main()
