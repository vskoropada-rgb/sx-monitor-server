import hashlib

from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import Server


def hash_api_key(raw: str) -> str:
    """SHA-256 hex-дайджест ключа.

    API-ключі — випадкові токени з високою ентропією (token_urlsafe(32)),
    тож сіль / bcrypt не потрібні. Зберігаємо лише хеш, щоб витік БД не
    розкривав ключі, якими можна керувати агентами.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_server(
    x_api_key: str = Header(..., alias="X-Api-Key"),
    db: Session = Depends(get_db),
) -> Server:
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return server
