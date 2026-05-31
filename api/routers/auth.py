"""
Авторизація дашборду.

  GET  /auth?token=...        — magic-link landing: валідує токен, ставить cookie, редірект на /
  GET  /api/auth/me           — хто я (для фронтенду)
  POST /api/auth/logout       — вихід
  POST /api/auth/login-token  — внутрішній: бот просить одноразовий токен (захищено shared-secret)
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import LoginLog
import security

router = APIRouter(tags=["auth"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/auth")
def magic_link(token: str, request: Request, db: Session = Depends(get_db)):
    """Перехід за посиланням з Telegram. Спалює токен, видає сесію."""
    admin_id = security.consume_login_token(db, token)
    db.add(LoginLog(
        admin_id=admin_id,
        action="login",
        ip=_client_ip(request),
        user_agent=request.headers.get("User-Agent", ""),
    ))
    db.commit()

    jwt_token = security.create_session_jwt(admin_id)
    resp = RedirectResponse(url="/", status_code=303)
    security.set_session_cookie(resp, jwt_token)
    return resp


@router.get("/api/auth/me")
def me(admin_id: int = Depends(security.require_admin)):
    return {"admin_id": admin_id, "authenticated": True}


@router.post("/api/auth/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    admin_id: int = Depends(security.require_admin),
):
    db.add(LoginLog(
        admin_id=admin_id,
        action="logout",
        ip=_client_ip(request),
        user_agent=request.headers.get("User-Agent", ""),
    ))
    db.commit()
    security.clear_session_cookie(response)
    return {"ok": True}


# ─── Внутрішній endpoint для бота ────────────────────────────────
# Бот і API в одній docker-мережі. Захищаємо shared-secret'ом,
# щоб ззовні (через nginx цей шлях не пробрасуємо) ніхто не смикнув.

class LoginTokenRequest(BaseModel):
    admin_id: int


@router.post("/api/auth/login-token")
def create_login_token(
    body: LoginTokenRequest,
    x_internal_secret: str = Header(default=""),
    db: Session = Depends(get_db),
):
    if x_internal_secret != settings.secret_key:
        raise HTTPException(status_code=403, detail="Forbidden")
    if body.admin_id not in settings.admin_ids:
        raise HTTPException(status_code=403, detail="Not an admin")

    raw = security.issue_login_token(db, body.admin_id)
    return {"url": f"{settings.public_url}/auth?token={raw}"}
