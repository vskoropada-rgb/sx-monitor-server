"""
Dashboard authentication via Telegram magic-link.
Авторизація дашборду через Telegram magic-link.

Flow / Потік:
  1. Admin sends /login to the bot → bot creates a one-time AuthToken (5 min TTL)
     and sends a link: {PUBLIC_URL}/auth?token=...
     Адмін пише /login боту → bot створює AuthToken (одноразовий, 5 хв)
     і надсилає посилання {PUBLIC_URL}/auth?token=...
  2. Admin follows the link → consume_login_token() validates, issues a JWT,
     sets it as an httpOnly cookie for 8 hours.
     Адмін переходить за посиланням → consume_login_token() валідує,
     випускає JWT і кладе його в httpOnly cookie на 8 годин.
  3. All protected endpoints read the cookie via the require_admin() dependency.
     Всі захищені endpoint'и читають cookie через залежність require_admin().

No VPN, no passwords. The only key is access to the admin's Telegram account.
Без VPN, без паролів. Єдиний ключ — доступ до Telegram-акаунта адміна.
"""
import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import Cookie, HTTPException, Response
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import settings
from models import AuthToken

ALGORITHM = "HS256"
COOKIE_NAME = "sx_session"


# ─── JWT session ─────────────────────────────────────────────────────────────
# All datetimes are naive UTC (matching datetime.utcnow() used elsewhere) to
# avoid skew when writing to TIMESTAMP WITHOUT TIME ZONE columns.
# Всі datetime — naive UTC (як datetime.utcnow() в решті коду) — щоб не було
# розбіжностей при записі в TIMESTAMP WITHOUT TIME ZONE.

def _now() -> datetime:
    return datetime.utcnow()


def create_session_jwt(admin_id: int) -> str:
    """Encode a signed JWT session token for the given admin.
    Створює підписаний JWT-токен сесії для заданого адміна."""
    expire = _now() + timedelta(hours=settings.session_ttl_hours)
    payload = {"sub": str(admin_id), "exp": expire, "typ": "session"}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def set_session_cookie(response: Response, token: str):
    """Attach the JWT as a secure httpOnly cookie.
    Додає JWT як захищений httpOnly cookie до відповіді."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.public_url.startswith("https"),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response):
    """Delete the session cookie on logout.
    Видаляє сесійний cookie при виході."""
    response.delete_cookie(COOKIE_NAME, path="/")


def require_admin(sx_session: str | None = Cookie(default=None)) -> int:
    """FastAPI dependency — returns admin_id or raises 401.
    FastAPI-залежність — повертає admin_id або кидає 401."""
    if not sx_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(sx_session, settings.secret_key, algorithms=[ALGORITHM])
        if payload.get("typ") != "session":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired session")


# ─── One-time login tokens (magic link) ──────────────────────────────────────
# Only the SHA-256 hash is stored in auth_tokens: even if the table leaks,
# no valid login links can be extracted (the raw value is given only to the bot).
# У БД зберігаємо лише SHA-256 хеш токена: витік таблиці auth_tokens не
# дасть діючих login-посилань (а raw-значення віддаємо тільки ботові).

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_login_token(db: Session, admin_id: int) -> str:
    """Called by the bot. Creates a one-time token and returns the raw value.
    Викликається ботом. Створює одноразовий токен і повертає raw-значення."""
    raw = secrets.token_urlsafe(32)
    expires = _now() + timedelta(minutes=settings.login_token_ttl_min)
    db.add(AuthToken(token=_hash_token(raw), admin_id=admin_id, expires_at=expires))
    db.commit()
    return raw


def consume_login_token(db: Session, raw: str) -> int:
    """Validates and immediately burns the token. Returns admin_id or raises 401.
    Перевіряє і одразу «спалює» токен. Повертає admin_id або кидає 401."""
    row = db.query(AuthToken).filter(AuthToken.token == _hash_token(raw)).first()
    if not row:
        raise HTTPException(status_code=401, detail="Невірне посилання")

    # Always delete — token is single-use regardless of validity outcome.
    # Завжди видаляємо — токен одноразовий незалежно від результату.
    used = row.used_at is not None
    expired = row.expires_at < _now()
    admin_id = row.admin_id

    if used or expired:
        db.delete(row)
        db.commit()
        raise HTTPException(status_code=401, detail="Посилання прострочене або вже використане")

    row.used_at = _now()
    db.delete(row)  # single-use — no longer needed / одноразовий — більше не потрібен
    db.commit()
    return admin_id


def cleanup_expired_tokens(db: Session):
    """Purge expired tokens. Call periodically to keep the table clean.
    Видаляє прострочені токени. Викликати періодично для чистоти таблиці."""
    db.query(AuthToken).filter(AuthToken.expires_at < _now()).delete()
    db.commit()
