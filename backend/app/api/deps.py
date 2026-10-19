from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import get_db
from ..core.errors import Forbidden, Unauthorized
from ..core.middleware import client_ip
from ..core.ratelimit import limiter
from ..core.security import hash_token
from ..models import Session as DbSession
from ..models import User

DB = Depends(get_db)


def _as_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def get_optional_user(request: Request, db: Session = DB) -> User | None:
    s = get_settings()
    token = request.cookies.get(s.session_cookie)
    if not token:
        return None
    sess = db.scalar(select(DbSession).where(DbSession.token_hash == hash_token(token)))
    now = datetime.now(UTC)
    if sess is None or sess.revoked_at is not None or _as_aware(sess.expires_at) <= now:
        return None
    user = db.get(User, sess.user_id)
    if user is None or not user.is_active:
        return None
    if now - _as_aware(sess.last_seen_at) > timedelta(minutes=5):  # throttle writes
        sess.last_seen_at = now
        db.commit()
    request.state.user_id = str(user.id)
    request.state.session_id = sess.id
    return user


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise Unauthorized("Sign in required")
    return user


def require_roles(*roles: str) -> Callable[[User], User]:
    def checker(user: User = Depends(get_current_user)) -> User:
        if not (user.role_names & set(roles)) and "admin" not in user.role_names:
            raise Forbidden(f"Requires role: {', '.join(roles)}")
        return user

    return checker


def rate_limit(scope: str, limit_attr: str) -> Callable[[Request], None]:
    """Per-IP (and per-user when signed in) limiter using a limit from settings."""

    def dep(request: Request) -> None:
        limit = getattr(get_settings(), limit_attr)
        who = getattr(request.state, "user_id", None) or client_ip(request)
        limiter.hit(f"{scope}:{who}", limit, 60)

    return dep


CurrentUser = Depends(get_current_user)
OptionalUser = Depends(get_optional_user)
