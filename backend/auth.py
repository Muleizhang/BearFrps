from __future__ import annotations

import re
import secrets
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, Response

from backend.config import Settings
from backend.deps import settings
from backend.models import User, store


ADMIN_SESSION_COOKIE = "admin_session"
UID_COOKIE = "uid"
_admin_sessions: set[str] = set()
_UID_RE = re.compile(r"^u_[0-9a-f]{8}$")


async def get_or_create_user(
    response: Response,
    uid: Annotated[str | None, Cookie(alias=UID_COOKIE)] = None,
) -> User:
    if uid and not _UID_RE.fullmatch(uid):
        uid = None
    async with store.lock:
        user = store.ensure_user_unlocked(uid)
    response.set_cookie(
        UID_COOKIE,
        user.uid,
        httponly=False,
        samesite="lax",
        max_age=60 * 60 * 24 * 365,
    )
    return user


def create_admin_session(response: Response) -> None:
    session_id = secrets.token_urlsafe(32)
    _admin_sessions.add(session_id)
    response.set_cookie(
        ADMIN_SESSION_COOKIE,
        session_id,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 8,
    )


def clear_admin_session(response: Response, session_id: str | None) -> None:
    if session_id:
        _admin_sessions.discard(session_id)
    response.delete_cookie(ADMIN_SESSION_COOKIE)


async def require_admin(
    request: Request,
    cfg: Settings = settings,
) -> None:
    session_id = request.cookies.get(ADMIN_SESSION_COOKIE)
    if not session_id or session_id not in _admin_sessions:
        raise HTTPException(status_code=401, detail="admin login required")


def check_admin_credentials(username: str, password: str, cfg: Settings = settings) -> bool:
    return secrets.compare_digest(username, cfg.admin_username) and secrets.compare_digest(
        password, cfg.admin_password
    )
