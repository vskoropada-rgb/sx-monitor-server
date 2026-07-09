"""
Application settings loaded from .env via pydantic-settings.
Налаштування застосунку, що завантажуються з .env через pydantic-settings.
"""
from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    tg_bot_token: str
    tg_group_id: str
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    secret_key: str = ""
    alert_cooldown_min: int = 30
    daily_report_hour: int = 10
    disk_warning_percent: int = 10
    disk_critical_percent: int = 5
    cpu_warning_percent: int = 85
    ram_warning_percent: int = 90

    # UTC offset for daily reports. Ukraine: UTC+3 summer, UTC+2 winter.
    # Зсув UTC для щоденного звіту. Україна: влітку +3, взимку +2.
    report_utc_offset: int = 3

    # ─── Auto-block on password brute-force ──────────────────────
    # Master switch. If False — only a Telegram alert with a manual "block"
    # button is sent, no firewall rule is created automatically.
    # Головний вимикач. Якщо False — лише сповіщення в Telegram з кнопкою
    # ручного блокування, автоматичне правило firewall не створюється.
    auto_block_enabled: bool = True
    # Auto-block triggers when failed logins from one external IP exceed this
    # number within the brute-force window (default 10 min). "More than N".
    # Автоблок спрацьовує, коли невдалих спроб з одного зовнішнього IP БІЛЬШЕ
    # за це число за вікно перебору (типово 10 хв). «Більше за N».
    auto_block_threshold: int = 10
    # Never-block IPs/CIDRs (office, VPN), comma-separated. Private RFC1918
    # ranges are never blocked regardless of this list.
    # IP/CIDR, які ніколи не блокуємо (офіс, VPN), через кому. Приватні мережі
    # RFC1918 не блокуються в будь-якому разі.
    auto_block_allowlist: str = ""

    # Shared secret for new agent registration (POST /api/servers/register).
    # Separate from secret_key so agents never see the master JWT key.
    # Секрет для реєстрації нових агентів (POST /api/servers/register).
    # Окремий від secret_key, щоб не світити майстер-ключ JWT на агентах.
    register_secret: str = ""

    # Secret for the internal bot→API call (/api/auth/login-token).
    # Separate from secret_key: leaking this header cannot forge JWT sessions.
    # Falls back to secret_key for compatibility with older deployments.
    # Секрет для внутрішнього виклику бот→API (/api/auth/login-token).
    # Окремий від secret_key: якщо цей заголовок колись витече, ним не можна
    # буде підписувати JWT-сесії. Якщо не заданий — fallback на secret_key.
    internal_secret: str = ""

    # ─── Dashboard / Auth ────────────────────────────────────────
    # Public server URL — used in Telegram magic-link (https://monitor.domain.com)
    # Публічний URL сервера — для magic-link у Telegram (https://monitor.domain.com)
    public_url: str = "http://localhost"
    # Telegram user_ids allowed to log in to the dashboard (comma-separated)
    # Telegram user_id кому дозволено логінитись у дашборд (через кому)
    dashboard_admins: str = ""
    # Dashboard session lifetime (hours) / Час життя сесії дашборду (годин)
    session_ttl_hours: int = 8
    # One-time login token lifetime (minutes) / Час життя одноразового login-токена (хвилин)
    login_token_ttl_min: int = 5

    @field_validator("secret_key")
    @classmethod
    def secret_key_must_be_set(cls, v: str) -> str:
        if not v or v == "dev-secret":
            raise ValueError(
                "SECRET_KEY must be set to a strong random value in .env "
                "(generate with: python -c \"import secrets; print(secrets.token_hex(32))\")"
            )
        return v

    @property
    def effective_internal_secret(self) -> str:
        """internal_secret, or secret_key as fallback for older deployments.
        internal_secret, або secret_key як fallback для старих деплоїв."""
        return self.internal_secret or self.secret_key

    @property
    def admin_ids(self) -> set[int]:
        """Parsed set of allowed admin Telegram IDs.
        Розбитий набір дозволених Telegram ID адміністраторів."""
        return {int(x) for x in self.dashboard_admins.split(",") if x.strip()}

    @property
    def auto_block_networks(self):
        """Parsed allowlist as ip_network objects (invalid entries skipped).
        Розпарсений allowlist як об'єкти ip_network (невалідні — пропускаються)."""
        import ipaddress
        nets = []
        for item in self.auto_block_allowlist.split(","):
            item = item.strip()
            if not item:
                continue
            try:
                nets.append(ipaddress.ip_network(item, strict=False))
            except ValueError:
                pass
        return nets

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
