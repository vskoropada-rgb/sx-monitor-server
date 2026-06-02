"""
Авторизація дашборду через Telegram magic-link.

Потік:
  1. Адмін пише /login боту  → bot створює AuthToken (одноразовий, 5 хв)
     і надсилає посилання {PUBLIC_URL}/auth?token=...
  2. Адмін переходить за посиланням → consume_login_token() валідує,
     випускає JWT і кладе його в httpOnly cookie на 8 годин.
  3. Усі захищені endpoint'и читають cookie через залежність require_admin().

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


# ─── JWT сесія ───────────────────────────────────────────────────
# Скрізь naive UTC (як datetime.utcnow() у решті коду) — щоб не було
# розбіжностей при записі в TIMESTAMP WITHOUT TIME ZONE.

def _now() -> datetime:
    return datetime.utcnow()


def create_session_jwt(admin_id: int) -> str:
    expire = _now() + timedelta(hours=settings.session_ttl_hours)
    payload = {"sub": str(admin_id), "exp": expire, "typ": "session"}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def set_session_cookie(response: Response, token: str):
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
    response.delete_cookie(COOKIE_NAME, path="/")


def require_admin(sx_session: str | None = Cookie(default=None)) -> int:
    """FastAPI-залежність: повертає admin_id або кидає 401."""
    if not sx_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(sx_session, settings.secret_key, algorithms=[ALGORITHM])
        if payload.get("typ") != "session":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired session")


# ─── Одноразові login-токени (magic link) ────────────────────────
# У БД зберігаємо лише SHA-256 хеш токена: витік таблиці auth_tokens не
# дасть діючих login-посилань (а raw-значення віддаємо тільки ботові).

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_login_token(db: Session, admin_id: int) -> str:
    """Викликається ботом. Створює одноразовий токен і повертає raw-значення."""
    raw = secrets.token_urlsafe(32)
    expires = _now() + timedelta(minutes=settings.login_token_ttl_min)
    db.add(AuthToken(token=_hash_token(raw), admin_id=admin_id, expires_at=expires))
    db.commit()
    return raw


def consume_login_token(db: Session, raw: str) -> int:
    """Перевіряє і одразу «спалює» токен. Повертає admin_id або кидає 401."""
    row = db.query(AuthToken).filter(AuthToken.token == _hash_token(raw)).first()
    if not row:
        raise HTTPException(status_code=401, detail="Невірне посилання")

    # завжди видаляємо — токен одноразовий незалежно від результату
    used = row.used_at is not None
    expired = row.expires_at < _now()
    admin_id = row.admin_id

    if used or expired:
        db.delete(row)
        db.commit()
        raise HTTPException(status_code=401, detail="Посилання прострочене або вже використане")

    row.used_at = _now()
    db.delete(row)  # одноразовий — більше не потрібен
    db.commit()
    return admin_id


def cleanup_expired_tokens(db: Session):
    db.query(AuthToken).filter(AuthToken.expires_at < _now()).delete()
    db.commit()
