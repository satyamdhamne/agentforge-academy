"""Authentication: registration, login (server-side sessions), logout, email verification, password reset, profile."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..api.deps import DB, CurrentUser, rate_limit
from ..core.config import get_settings
from ..core.errors import AppError, Conflict, Unauthorized
from ..core.middleware import client_ip
from ..core.ratelimit import limiter
from ..core.security import hash_password, hash_token, needs_rehash, new_token, password_problems, verify_password
from ..models import AuthToken, Profile, Role, Subscription, User, UserRole
from ..models import Session as DbSession
from ..services.common import audit, plan_for, send_email, track

router = APIRouter(prefix="/auth", tags=["auth"])
me_router = APIRouter(prefix="/me", tags=["profile"])

VERIFY_TTL = timedelta(hours=48)
RESET_TTL = timedelta(minutes=30)


# ------------------------------------------------------------------ schemas

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=100)

    @field_validator("email")
    @classmethod
    def lower(cls, v: str) -> str:
        return v.strip().lower()


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=128)

    @field_validator("email")
    @classmethod
    def lower(cls, v: str) -> str:
        return v.strip().lower()


class TokenIn(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)


class ResetRequestIn(BaseModel):
    email: EmailStr


class ResetConfirmIn(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)
    new_password: str = Field(..., max_length=128)


class ProfileOut(BaseModel):
    display_name: str
    bio: str
    avatar_url: str | None
    experience_level: str
    goals: list[str]
    mentor_opt_in: bool
    public_portfolio: bool


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    email_verified: bool
    roles: list[str]
    plan: str
    profile: ProfileOut
    created_at: datetime


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=100)
    bio: str | None = Field(None, max_length=1000)
    experience_level: str | None = Field(None, pattern="^(beginner|intermediate|advanced|expert)$")
    goals: list[str] | None = Field(None, max_length=10)
    mentor_opt_in: bool | None = None
    public_portfolio: bool | None = None


# ------------------------------------------------------------------ helpers

def user_out(db: Session, user: User) -> UserOut:
    p = user.profile
    return UserOut(
        id=user.id, email=user.email, email_verified=user.email_verified_at is not None,
        roles=sorted(user.role_names), plan=plan_for(db, user), created_at=user.created_at,
        profile=ProfileOut(display_name=p.display_name, bio=p.bio, avatar_url=p.avatar_url, experience_level=p.experience_level,
                           goals=list(p.goals or []), mentor_opt_in=p.mentor_opt_in, public_portfolio=p.public_portfolio),
    )


def set_session_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(s.session_cookie, token, max_age=s.session_ttl_hours * 3600, httponly=True, secure=s.cookie_secure,
                        samesite="lax", domain=s.cookie_domain, path="/")


def ensure_csrf_cookie(request: Request, response: Response) -> str:
    s = get_settings()
    token = request.cookies.get(s.csrf_cookie) or new_token(24)
    # Readable by JS on purpose (double-submit pattern); it grants nothing on its own.
    response.set_cookie(s.csrf_cookie, token, max_age=s.session_ttl_hours * 3600, httponly=False, secure=s.cookie_secure,
                        samesite="lax", domain=s.cookie_domain, path="/")
    return token


def create_session(db: Session, user: User, request: Request, response: Response) -> None:
    token = new_token()
    db.add(DbSession(user_id=user.id, token_hash=hash_token(token), ip=client_ip(request),
                     user_agent=(request.headers.get("user-agent") or "")[:300],
                     expires_at=datetime.now(UTC) + timedelta(hours=get_settings().session_ttl_hours)))
    set_session_cookie(response, token)


def issue_token(db: Session, user: User, purpose: str, ttl: timedelta) -> str:
    db.execute(update(AuthToken).where(AuthToken.user_id == user.id, AuthToken.purpose == purpose, AuthToken.used_at.is_(None))
               .values(used_at=datetime.now(UTC)))  # invalidate older tokens of the same purpose
    token = new_token()
    db.add(AuthToken(user_id=user.id, purpose=purpose, token_hash=hash_token(token), expires_at=datetime.now(UTC) + ttl))
    return token


def consume_token(db: Session, token: str, purpose: str) -> User:
    row = db.scalar(select(AuthToken).where(AuthToken.token_hash == hash_token(token), AuthToken.purpose == purpose))
    now = datetime.now(UTC)
    expires = row.expires_at if row and row.expires_at.tzinfo else (row.expires_at.replace(tzinfo=UTC) if row else None)
    if row is None or row.used_at is not None or expires <= now:
        raise AppError("This link is invalid or has expired.", code="invalid_token")
    row.used_at = now
    user = db.get(User, row.user_id)
    assert user is not None
    return user


def send_verification(db: Session, user: User) -> None:
    token = issue_token(db, user, "verify_email", VERIFY_TTL)
    link = f"{get_settings().frontend_url}/verify-email?token={token}"
    send_email(user.email, "Verify your AgentForge Academy email",
               f"Welcome to AgentForge Academy!\n\nConfirm your email address:\n{link}\n\nThis link expires in 48 hours.")


def get_or_create_role(db: Session, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == name))
    if role is None:
        role = Role(name=name, description=name.title())
        db.add(role)
        db.flush()
    return role


def create_user(db: Session, email: str, password: str, display_name: str, roles: tuple[str, ...] = ("learner",),
                plan: str = "free", verified: bool = False) -> User:
    user = User(email=email.lower(), password_hash=hash_password(password),
                email_verified_at=datetime.now(UTC) if verified else None)
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id, display_name=display_name, goals=[]))
    for r in roles:
        db.add(UserRole(user_id=user.id, role_id=get_or_create_role(db, r).id))
    db.add(Subscription(user_id=user.id, plan=plan, status="active"))
    db.flush()
    db.refresh(user)
    return user


# ------------------------------------------------------------------ routes

@router.get("/csrf")
def csrf(request: Request, response: Response) -> dict:
    return {"csrf_token": ensure_csrf_cookie(request, response)}


@router.post("/register", status_code=201, response_model=UserOut,
             dependencies=[Depends(rate_limit("auth", "rate_limit_auth_per_minute"))])
def register(body: RegisterIn, request: Request, response: Response, db: Session = DB) -> UserOut:
    problems = password_problems(body.password, body.email)
    if problems:
        raise AppError("Password " + "; ".join(problems), code="weak_password", status_code=422)
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise Conflict("An account with this email already exists.", code="email_taken")
    user = create_user(db, body.email, body.password, body.display_name.strip())
    send_verification(db, user)
    create_session(db, user, request, response)
    track(db, user.id, "user_registered")
    audit(db, user, "user.register", "user", user.id, request=request)
    db.commit()
    return user_out(db, user)


@router.post("/login", response_model=UserOut, dependencies=[Depends(rate_limit("auth", "rate_limit_auth_per_minute"))])
def login(body: LoginIn, request: Request, response: Response, db: Session = DB) -> UserOut:
    limiter.hit(f"login-email:{body.email}", get_settings().rate_limit_auth_per_minute, 60)  # per-account throttle
    user = db.scalar(select(User).where(User.email == body.email))
    if not verify_password(body.password, user.password_hash if user else None) or user is None or not user.is_active:
        raise Unauthorized("Invalid email or password.", code="invalid_credentials")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    user.last_login_at = datetime.now(UTC)
    create_session(db, user, request, response)  # always a fresh session id (prevents fixation)
    ensure_csrf_cookie(request, response)
    track(db, user.id, "user_logged_in")
    audit(db, user, "user.login", "user", user.id, request=request)
    db.commit()
    return user_out(db, user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = DB) -> Response:
    s = get_settings()
    token = request.cookies.get(s.session_cookie)
    if token:
        db.execute(update(DbSession).where(DbSession.token_hash == hash_token(token)).values(revoked_at=datetime.now(UTC)))
        db.commit()
    response.delete_cookie(s.session_cookie, path="/", domain=s.cookie_domain)
    response.status_code = 204
    return response


@router.post("/logout-all", status_code=204)
def logout_all(response: Response, user: User = CurrentUser, db: Session = DB) -> Response:
    db.execute(update(DbSession).where(DbSession.user_id == user.id, DbSession.revoked_at.is_(None))
               .values(revoked_at=datetime.now(UTC)))
    db.commit()
    s = get_settings()
    response.delete_cookie(s.session_cookie, path="/", domain=s.cookie_domain)
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = CurrentUser, db: Session = DB) -> UserOut:
    return user_out(db, user)


@router.post("/verify-email")
def verify_email(body: TokenIn, request: Request, db: Session = DB) -> dict:
    user = consume_token(db, body.token, "verify_email")
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
        audit(db, user, "user.verify_email", "user", user.id, request=request)
    db.commit()
    return {"verified": True}


@router.post("/resend-verification", status_code=202, dependencies=[Depends(rate_limit("auth", "rate_limit_auth_per_minute"))])
def resend_verification(user: User = CurrentUser, db: Session = DB) -> dict:
    if user.email_verified_at is None:
        send_verification(db, user)
        db.commit()
    return {"sent": user.email_verified_at is None}


@router.post("/password-reset/request", status_code=202,
             dependencies=[Depends(rate_limit("auth", "rate_limit_auth_per_minute"))])
def password_reset_request(body: ResetRequestIn, request: Request, db: Session = DB) -> dict:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user and user.is_active:
        token = issue_token(db, user, "reset_password", RESET_TTL)
        link = f"{get_settings().frontend_url}/reset-password?token={token}"
        send_email(user.email, "Reset your AgentForge Academy password",
                   f"Use this link to choose a new password (valid for 30 minutes):\n{link}\n\n"
                   "If you didn't request this, you can ignore this email.")
        audit(db, user, "user.password_reset_requested", "user", user.id, request=request)
        db.commit()
    # Same response whether or not the account exists (no account enumeration).
    return {"message": "If an account exists for that email, a reset link has been sent."}


@router.post("/password-reset/confirm")
def password_reset_confirm(body: ResetConfirmIn, request: Request, db: Session = DB) -> dict:
    user = consume_token(db, body.token, "reset_password")
    problems = password_problems(body.new_password, user.email)
    if problems:
        db.rollback()
        raise AppError("Password " + "; ".join(problems), code="weak_password", status_code=422)
    user.password_hash = hash_password(body.new_password)
    db.execute(update(DbSession).where(DbSession.user_id == user.id, DbSession.revoked_at.is_(None))
               .values(revoked_at=datetime.now(UTC)))  # sign out everywhere
    audit(db, user, "user.password_reset", "user", user.id, request=request)
    db.commit()
    return {"reset": True}


@me_router.get("/profile", response_model=UserOut)
def get_profile(user: User = CurrentUser, db: Session = DB) -> UserOut:
    return user_out(db, user)


@me_router.patch("/profile", response_model=UserOut)
def update_profile(body: ProfileUpdate, user: User = CurrentUser, db: Session = DB) -> UserOut:
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user.profile, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    return user_out(db, user)
