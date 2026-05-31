from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    tg_bot_token: str
    tg_group_id: str
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    secret_key: str = "dev-secret"
    alert_cooldown_min: int = 30
    daily_report_hour: int = 10

    # Секрет для реєстрації нових агентів (POST /api/servers/register).
    # Окремий від secret_key, щоб не світити майстер-ключ JWT на агентах.
    register_secret: str = ""

    # ─── Dashboard / Auth ────────────────────────────────────────
    # Публічний URL сервера — для magic-link у Telegram (https://monitor.domain.com)
    public_url: str = "http://localhost"
    # Telegram user_id кому дозволено логінитись у дашборд (через кому)
    dashboard_admins: str = ""
    # Час життя сесії дашборду (годин)
    session_ttl_hours: int = 8
    # Час життя одноразового login-токена (хвилин)
    login_token_ttl_min: int = 5

    @property
    def admin_ids(self) -> set[int]:
        return {int(x) for x in self.dashboard_admins.split(",") if x.strip()}

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
