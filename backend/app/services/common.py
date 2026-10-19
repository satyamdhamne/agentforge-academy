"""Cross-cutting services: email, audit logging, analytics events, entitlements, pagination."""

from __future__ import annotations

import logging
import smtplib
import uuid
from email.message import EmailMessage
from typing import Any

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.errors import PaymentRequired
from ..core.middleware import client_ip
from ..models import AuditLog, Entitlement, Subscription, UsageEvent, User

log = logging.getLogger("agentforge")
PLAN_RANK = {"free": 0, "pro": 1, "team": 2}

# ---------------------------------------------------------------- email


def send_email(to: str, subject: str, body: str) -> None:
    s = get_settings()
    if s.mail_backend == "console":
        # Development only (production config refuses the console backend).
        log.info("email (console backend)", extra={"path": f"to={to} subject={subject}\n{body}"})
        print(f"\n=== EMAIL to {to} ===\nSubject: {subject}\n\n{body}\n=====================\n", flush=True)
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.mail_from, to, subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
        smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)


# ---------------------------------------------------------------- audit & analytics


def audit(db: Session, actor: User | None, action: str, entity_type: str, entity_id: Any = None,
          before: dict | None = None, after: dict | None = None, request: Request | None = None) -> None:
    db.add(AuditLog(
        actor_id=actor.id if actor else None, action=action, entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None, before=before, after=after,
        ip=client_ip(request) if request else None, trace_id=getattr(request.state, "trace_id", None) if request else None,
    ))


ALLOWED_EVENT_PROPS = {"lesson", "track", "exercise", "status", "agent", "provider", "points", "difficulty", "plan",
                       "category", "language", "mode", "score", "cost_usd", "tokens"}


def track(db: Session, user_id: uuid.UUID | None, event_type: str, **props: Any) -> None:
    """Record a product analytics event. Only allowlisted, non-personal properties are kept."""
    clean = {k: v for k, v in props.items() if k in ALLOWED_EVENT_PROPS and isinstance(v, (str, int, float, bool, type(None)))}
    db.add(UsageEvent(user_id=user_id, event_type=event_type, properties=clean))


# ---------------------------------------------------------------- entitlements


def plan_for(db: Session, user: User | None) -> str:
    if user is None:
        return "free"
    owner = Subscription.user_id == user.id
    if user.organization_id:
        owner = or_(owner, Subscription.organization_id == user.organization_id)
    plans = db.scalars(select(Subscription.plan).where(Subscription.status == "active", owner)).all()
    return max(plans, key=lambda p: PLAN_RANK[p], default="free")


def can_access_tier(plan: str, tier: str) -> bool:
    return PLAN_RANK[plan] >= PLAN_RANK.get(tier, 0)


def require_tier(db: Session, user: User | None, tier: str, what: str) -> None:
    plan = plan_for(db, user)
    if not can_access_tier(plan, tier):
        raise PaymentRequired(f"{what} is included in the {tier.title()} plan.", details={"required_tier": tier, "current_plan": plan})


def entitlement_limit(db: Session, plan: str, feature_key: str) -> int | None:
    ent = db.scalar(select(Entitlement).where(Entitlement.plan == plan, Entitlement.feature_key == feature_key))
    if ent is None or not ent.enabled:
        return 0
    return ent.limit_value


# ---------------------------------------------------------------- pagination


def paginate(db: Session, stmt, page: int, page_size: int) -> tuple[list, int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = db.scalars(stmt.limit(page_size).offset((page - 1) * page_size)).all()
    return list(items), int(total)
