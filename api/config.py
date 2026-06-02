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
    # UTC offset для щоденного звіту. Україна: влітку +3, взимку +2
    report_utc_offset: int = 3

    # Секрет для реєстрації нових агентів (POST /api/servers/register).
    # Окремий від secret_key, щоб не світити майстер-ключ JWT на агентах.
    register_secret: str = ""

    # Секрет для внутрішнього виклику бот→API (/api/auth/login-token).
    # Окремий від secret_key: якщо цей заголовок колись витече, ним не можна
    # буде підписувати/форджити JWT-сесії. Якщо не заданий — для сумісності
    # зі старими деплоями використовуємо secret_key (див. effective_internal_secret).
    internal_secret: str = ""

    # ─── Dashboard / Auth ────────────────────────────────────────
    # Публічний URL сервера — для magic-link у Telegram (https://monitor.domain.com)
    public_url: str = "http://localhost"
    # Telegram user_id кому дозволено логінитись у дашборд (через кому)
    dashboard_admins: str = ""
    # Час життя сесії дашборду (годин)
    session_ttl_hours: int = 8
    # Час життя одноразового login-токена (хвилин)
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
        """internal_secret, або secret_key як fallback для старих деплоїв."""
        return self.internal_secret or self.secret_key

    @property
    def admin_ids(self) -> set[int]:
        return {int(x) for x in self.dashboard_admins.split(",") if x.strip()}

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
