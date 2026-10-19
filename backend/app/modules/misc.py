"""Plans (pricing), real-world projects and health endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..api.deps import DB, OptionalUser
from ..core.config import get_settings
from ..models import Entitlement, Project, User
from ..services.common import can_access_tier, plan_for

router = APIRouter(tags=["catalog"])
health_router = APIRouter(tags=["health"])

PLAN_COPY = {
    "free": {"name": "Free", "price_hint": "$0", "tagline": "Start learning today",
             "highlights": ["Introductory tracks", "Selected challenges", "Mock agent runs", "Limited code lab runs"]},
    "pro": {"name": "Pro", "price_hint": "Configurable", "tagline": "Everything for individual engineers",
            "highlights": ["All learning paths", "Advanced projects", "Real model agent runs", "Higher lab allowances"]},
    "team": {"name": "Team", "price_hint": "Contact us", "tagline": "Upskill your engineering org",
             "highlights": ["Shared learning paths", "Team dashboards", "Enterprise scenarios", "Admin controls"]},
}


@router.get("/plans")
def plans(db: Session = DB) -> dict:
    ents = db.scalars(select(Entitlement).order_by(Entitlement.feature_key)).all()
    out = []
    for key in ("free", "pro", "team"):
        features = {e.feature_key: (e.limit_value if e.limit_value is not None else e.enabled) for e in ents if e.plan == key}
        out.append({"key": key, **PLAN_COPY[key], "features": features})
    return {"items": out, "payments_enabled": False}


@router.get("/projects")
def projects(user: User | None = OptionalUser, db: Session = DB) -> dict:
    plan = plan_for(db, user)
    rows = db.scalars(select(Project).where(Project.status == "published").order_by(Project.estimated_hours)).all()
    return {"items": [{"slug": p.slug, "title": p.title, "summary": p.summary, "difficulty": p.difficulty, "track": p.track_slug,
                       "skills": p.skills, "requirements": p.requirements, "estimated_hours": p.estimated_hours, "tier": p.tier,
                       "locked": not can_access_tier(plan, p.tier)} for p in rows]}


@health_router.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@health_router.get("/readyz")
def readyz(db: Session = DB) -> dict:
    db.execute(text("SELECT 1"))
    s = get_settings()
    return {"status": "ready", "llm_provider": s.llm_provider, "sandbox_configured": bool(s.sandbox_url), "env": s.env}
