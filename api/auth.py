"""
Agent authentication via X-Api-Key header.
Автентифікація агентів через заголовок X-Api-Key.

Agents register once with REGISTER_SECRET and receive a random API key.
Only the SHA-256 hash is stored in the database — even if the DB leaks,
no valid keys can be extracted from the digests.

Агенти реєструються один раз з REGISTER_SECRET і отримують випадковий API-ключ.
У БД зберігається лише SHA-256 хеш — витік таблиці servers не розкриє ключів.

See also / Дивись також:
  security.py — dashboard JWT session auth (magic-link flow)
               — JWT-сесії дашборду (magic-link потік)
"""
import hashlib

from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Server


def hash_api_key(raw: str) -> str:
    """SHA-256 hex digest of an agent API key.
    SHA-256 hex-дайджест ключа агента.

    Keys are high-entropy random tokens (token_urlsafe(32)), so salting /
    bcrypt is unnecessary. Storing only the hash means a DB leak does not
    expose keys that can be used to control agents.

    Ключі — випадкові токени з високою ентропією (token_urlsafe(32)),
    тож сіль / bcrypt не потрібні. Зберігаємо лише хеш, щоб витік БД не
    розкривав ключі, якими можна керувати агентами.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_server(
    x_api_key: str = Header(..., alias="X-Api-Key"),
    db: Session = Depends(get_db),
) -> Server:
    """FastAPI dependency — looks up the server by its hashed API key or raises 401.
    FastAPI-залежність — знаходить сервер за хешованим API-ключем або кидає 401."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return server
