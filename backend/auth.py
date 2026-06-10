from __future__ import annotations

import re
import secrets
import hashlib
import hmac
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, Response

from backend.deps import settings
from backend.models import User, new_uid, store
from backend.user_persistence import save_registered_users_unlocked


ADMIN_SESSION_COOKIE = "admin_session"
USER_SESSION_COOKIE = "user_session"
UID_COOKIE = "uid"
_admin_sessions: set[str] = set()
_user_sessions: dict[str, str] = {}
_UID_RE = re.compile(r"^u_[0-9a-f]{8}$")
_USERNAME_RE = re.compile(r"^[a-z0-9_]{3,32}$")
_PASSWORD_ITERATIONS = 240_000


def normalize_username(username: str) -> str:
    normalized = username.strip().lower()
    if not _USERNAME_RE.fullmatch(normalized):
        raise HTTPException(status_code=400, detail="用户名需为 3-32 位字母、数字或下划线")
    return normalized


def validate_password(password: str) -> None:
    if not 8 <= len(password) <= 128:
        raise HTTPException(status_code=400, detail="密码长度需为 8-128 位")


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        _PASSWORD_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${_PASSWORD_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    try:
        method, iterations_text, salt, expected = stored_hash.split("$", 3)
        if method != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("ascii"),
            iterations,
        ).hex()
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def user_public_dto(user: User) -> dict[str, object]:
    return {
        "uid": user.uid,
        "username": user.username,
        "balance_mb": user.balance_mb,
        "total_recharged_mb": user.total_recharged_mb,
        "created_at": user.created_at.isoformat(),
    }


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


async def require_user(
    response: Response,
    session_id: Annotated[str | None, Cookie(alias=USER_SESSION_COOKIE)] = None,
) -> User:
    uid = _user_sessions.get(session_id or "")
    if not uid:
        raise HTTPException(status_code=401, detail="user login required")
    async with store.lock:
        user = store.users.get(uid)
        if user is None or not user.username:
            if session_id:
                _user_sessions.pop(session_id, None)
            raise HTTPException(status_code=401, detail="user login required")
    response.set_cookie(
        UID_COOKIE,
        user.uid,
        httponly=False,
        samesite="lax",
        max_age=60 * 60 * 24 * 365,
    )
    return user


def create_user_session(response: Response, user: User) -> None:
    session_id = secrets.token_urlsafe(32)
    _user_sessions[session_id] = user.uid
    response.set_cookie(
        USER_SESSION_COOKIE,
        session_id,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 365,
    )
    response.set_cookie(
        UID_COOKIE,
        user.uid,
        httponly=False,
        samesite="lax",
        max_age=60 * 60 * 24 * 365,
    )


def clear_user_session(response: Response, session_id: str | None) -> None:
    if session_id:
        _user_sessions.pop(session_id, None)
    response.delete_cookie(USER_SESSION_COOKIE)
    response.delete_cookie(UID_COOKIE)


def clear_all_user_sessions() -> None:
    _user_sessions.clear()


def register_user_unlocked(username: str, password: str, legacy_uid: str | None = None) -> User:
    normalized = normalize_username(username)
    validate_password(password)
    if store.find_user_by_username_unlocked(normalized):
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = None
    if legacy_uid and _UID_RE.fullmatch(legacy_uid):
        candidate = store.users.get(legacy_uid)
        if candidate is not None and not candidate.username:
            user = candidate
    if user is None:
        uid = new_uid()
        while uid in store.users:
            uid = new_uid()
        user = User(uid=uid)
        store.users[user.uid] = user

    user.username = normalized
    user.password_hash = hash_password(password)
    save_registered_users_unlocked(store)
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
) -> None:
    session_id = request.cookies.get(ADMIN_SESSION_COOKIE)
    if not session_id or session_id not in _admin_sessions:
        raise HTTPException(status_code=401, detail="admin login required")


def check_admin_credentials(username: str, password: str) -> bool:
    return secrets.compare_digest(username, settings.admin_username) and secrets.compare_digest(
        password, settings.admin_password
    )
