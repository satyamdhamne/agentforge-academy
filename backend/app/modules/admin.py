"""Admin CMS (versioned lessons with draft → review → published), manual review queue, plans, analytics, audit."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from ..api.deps import DB, require_roles
from ..core.errors import AppError, Conflict, NotFound
from ..models import (
    AgentRun,
    Announcement,
    AuditLog,
    ChallengeAttempt,
    Exercise,
    Lesson,
    LessonVersion,
    PortfolioEntry,
    Progress,
    Subscription,
    UsageEvent,
    User,
)
from ..services import achievements as ach
from ..services.common import audit, paginate, track

router = APIRouter(prefix="/admin", tags=["admin"])
public_router = APIRouter(tags=["announcements"])

Author = Depends(require_roles("author", "reviewer"))
Reviewer = Depends(require_roles("reviewer"))
Admin = Depends(require_roles("admin"))

REQUIRED_SECTIONS = ["explanation", "why_it_matters", "prerequisites", "mental_model", "code_examples", "real_world",
                     "common_mistakes", "debugging", "performance_security", "interview_questions", "mini_challenge",
                     "advanced_challenge", "further_reading"]


# ------------------------------------------------------------------ lessons (CMS)

def _version_out(v: LessonVersion) -> dict:
    return {"id": str(v.id), "version": v.version, "status": v.status, "change_note": v.change_note,
            "author_id": str(v.author_id) if v.author_id else None, "created_at": v.created_at, "published_at": v.published_at}


@router.get("/lessons")
def list_lessons(status: str | None = Query(None, pattern="^(draft|review|published|archived)$"),
                 q: str | None = Query(None, max_length=100), page: int = Query(1, ge=1),
                 page_size: int = Query(50, ge=1, le=200), _: User = Author, db: Session = DB) -> dict:
    stmt = select(Lesson).order_by(Lesson.slug)
    if status:
        stmt = stmt.where(Lesson.status == status)
    if q:
        stmt = stmt.where(func.lower(Lesson.title).like(f"%{q.lower()}%"))
    items, total = paginate(db, stmt, page, page_size)
    pending = dict(db.execute(select(LessonVersion.lesson_id, func.count()).where(LessonVersion.status == "review")
                              .group_by(LessonVersion.lesson_id)).all())
    return {"items": [{"id": str(lesson.id), "slug": lesson.slug, "title": lesson.title, "status": lesson.status, "tier": lesson.tier,
                       "track": lesson.module.course.track.title, "published_version": lesson.published_version.version if lesson.published_version else None,
                       "pending_review": pending.get(lesson.id, 0), "updated_at": lesson.updated_at} for lesson in items],
            "total": total, "page": page, "page_size": page_size}


@router.get("/lessons/{lesson_id}")
def get_lesson_admin(lesson_id: uuid.UUID, _: User = Author, db: Session = DB) -> dict:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise NotFound("Lesson not found")
    versions = db.scalars(select(LessonVersion).where(LessonVersion.lesson_id == lesson.id).order_by(LessonVersion.version.desc())).all()
    latest = versions[0] if versions else None
    return {"id": str(lesson.id), "slug": lesson.slug, "title": lesson.title, "status": lesson.status, "tier": lesson.tier,
            "versions": [_version_out(v) for v in versions], "latest_content": latest.content if latest else None,
            "required_sections": REQUIRED_SECTIONS}


class VersionIn(BaseModel):
    content: dict[str, Any]
    change_note: str = Field(..., min_length=3, max_length=500)


@router.post("/lessons/{lesson_id}/versions", status_code=201)
def create_version(lesson_id: uuid.UUID, body: VersionIn, request: Request, user: User = Author, db: Session = DB) -> dict:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise NotFound("Lesson not found")
    sections = (body.content or {}).get("sections") or {}
    missing = [s for s in REQUIRED_SECTIONS if not sections.get(s)]
    if missing:
        raise AppError("Lesson content is missing required sections.", code="incomplete_lesson", status_code=422, details=missing)
    latest = db.scalar(select(func.max(LessonVersion.version)).where(LessonVersion.lesson_id == lesson.id)) or 0
    v = LessonVersion(lesson_id=lesson.id, version=latest + 1, status="draft", content=body.content,
                      change_note=body.change_note, author_id=user.id)
    db.add(v)
    db.flush()
    audit(db, user, "lesson_version.create", "lesson", lesson.id, after={"version": v.version}, request=request)
    db.commit()
    return _version_out(v)


def _transition(db: Session, version_id: uuid.UUID, allowed_from: tuple[str, ...]) -> LessonVersion:
    v = db.get(LessonVersion, version_id)
    if v is None:
        raise NotFound("Version not found")
    if v.status not in allowed_from:
        raise Conflict(f"Version is {v.status}; expected one of {', '.join(allowed_from)}.")
    return v


@router.post("/lesson-versions/{version_id}/submit")
def submit_for_review(version_id: uuid.UUID, request: Request, user: User = Author, db: Session = DB) -> dict:
    v = _transition(db, version_id, ("draft",))
    v.status = "review"
    audit(db, user, "lesson_version.submit", "lesson_version", v.id, before={"status": "draft"}, after={"status": "review"}, request=request)
    db.commit()
    return _version_out(v)


@router.post("/lesson-versions/{version_id}/publish")
def publish(version_id: uuid.UUID, request: Request, user: User = Reviewer, db: Session = DB) -> dict:
    v = _transition(db, version_id, ("review",))
    if v.author_id == user.id and "admin" not in user.role_names:
        raise AppError("Authors cannot publish their own changes; another reviewer must approve.", code="four_eyes", status_code=403)
    lesson = db.get(Lesson, v.lesson_id)
    previous = lesson.published_version
    if previous:
        previous.status = "archived"
    v.status, v.published_at, v.reviewer_id = "published", datetime.now(UTC), user.id
    lesson.published_version_id, lesson.status = v.id, "published"
    audit(db, user, "lesson_version.publish", "lesson", lesson.id,
          before={"version": previous.version if previous else None}, after={"version": v.version}, request=request)
    db.commit()
    return _version_out(v)


@router.post("/lesson-versions/{version_id}/reject")
def reject(version_id: uuid.UUID, request: Request, user: User = Reviewer, db: Session = DB) -> dict:
    v = _transition(db, version_id, ("review",))
    v.status = "draft"
    audit(db, user, "lesson_version.reject", "lesson_version", v.id, before={"status": "review"}, after={"status": "draft"}, request=request)
    db.commit()
    return _version_out(v)


# ------------------------------------------------------------------ manual review queue

@router.get("/reviews")
def review_queue(_: User = Reviewer, db: Session = DB) -> dict:
    rows = db.execute(select(ChallengeAttempt, Exercise).join(Exercise, Exercise.id == ChallengeAttempt.exercise_id)
                      .where(ChallengeAttempt.status == "pending_review").order_by(ChallengeAttempt.created_at)).all()
    return {"items": [{"id": str(a.id), "exercise": {"slug": e.slug, "title": e.title, "points": e.points,
                                                     "rubric": (e.spec or {}).get("rubric", []), "prompt_md": e.prompt_md},
                       "answer_text": a.submission.get("answer_text"), "submitted_at": a.created_at} for a, e in rows]}


class ReviewIn(BaseModel):
    scores: dict[str, float] = Field(..., description="criterion -> score between 0 and 1")
    feedback: str = Field(..., min_length=10, max_length=5000)


@router.post("/attempts/{attempt_id}/review")
def review_attempt(attempt_id: uuid.UUID, body: ReviewIn, request: Request, user: User = Reviewer, db: Session = DB) -> dict:
    a = db.get(ChallengeAttempt, attempt_id)
    if a is None or a.status != "pending_review":
        raise NotFound("No pending review with that id")
    if a.user_id == user.id:
        raise AppError("You cannot review your own submission.", code="self_review", status_code=403)
    e = db.get(Exercise, a.exercise_id)
    rubric = (e.spec or {}).get("rubric", [])
    names = {r["criterion"] for r in rubric}
    if set(body.scores) != names or any(not 0 <= s <= 1 for s in body.scores.values()):
        raise AppError("Score every rubric criterion between 0 and 1.", code="bad_scores", status_code=422, details=sorted(names))
    total_w = sum(r.get("weight", 1) for r in rubric) or 1
    score = round(sum(body.scores[r["criterion"]] * r.get("weight", 1) for r in rubric) / total_w, 3)
    from .challenges import points_for  # local import avoids a module cycle

    prior = db.scalars(select(ChallengeAttempt).where(ChallengeAttempt.user_id == a.user_id, ChallengeAttempt.exercise_id == e.id,
                                                      ChallengeAttempt.id != a.id)).all()
    a.status, a.score, a.reviewer_id, a.reviewed_at = "reviewed", score, user.id, datetime.now(UTC)
    a.points_awarded = points_for(e, "reviewed", score, a.hints_used, list(prior))
    a.review_feedback = body.feedback
    a.result = {**(a.result or {}), "rubric_scores": body.scores}
    audit(db, user, "attempt.review", "challenge_attempt", a.id, after={"score": score, "points": a.points_awarded}, request=request)
    learner = db.get(User, a.user_id)
    db.flush()
    ach.evaluate(db, learner)
    track(db, a.user_id, "challenge_reviewed", exercise=e.slug, score=score, points=a.points_awarded)
    db.commit()
    return {"id": str(a.id), "status": a.status, "score": score, "points_awarded": a.points_awarded}


# ------------------------------------------------------------------ users & plans

@router.get("/users")
def list_users(q: str | None = Query(None, max_length=100), page: int = Query(1, ge=1), _: User = Admin, db: Session = DB) -> dict:
    stmt = select(User).order_by(User.created_at.desc())
    if q:
        stmt = stmt.where(User.email.like(f"%{q.lower()}%"))
    items, total = paginate(db, stmt, page, 50)
    plans = dict(db.execute(select(Subscription.user_id, Subscription.plan).where(Subscription.status == "active")).all())
    return {"items": [{"id": str(u.id), "email": u.email, "display_name": u.profile.display_name if u.profile else "",
                       "roles": sorted(u.role_names), "plan": plans.get(u.id, "free"), "verified": u.email_verified_at is not None,
                       "created_at": u.created_at, "last_login_at": u.last_login_at} for u in items], "total": total}


class PlanIn(BaseModel):
    plan: str = Field(..., pattern="^(free|pro|team)$")


@router.patch("/users/{user_id}/plan")
def set_plan(user_id: uuid.UUID, body: PlanIn, request: Request, admin: User = Admin, db: Session = DB) -> dict:
    """Manual plan assignment. Payment providers integrate later by writing the same Subscription rows."""
    target = db.get(User, user_id)
    if target is None:
        raise NotFound("User not found")
    sub = db.scalar(select(Subscription).where(Subscription.user_id == target.id, Subscription.status == "active"))
    before = sub.plan if sub else None
    if sub is None:
        sub = Subscription(user_id=target.id, plan=body.plan, status="active")
        db.add(sub)
    sub.plan = body.plan
    audit(db, admin, "subscription.set_plan", "user", target.id, before={"plan": before}, after={"plan": body.plan}, request=request)
    track(db, target.id, "plan_changed", plan=body.plan)
    db.commit()
    return {"user_id": str(target.id), "plan": body.plan}


@router.get("/audit-logs")
def audit_logs(entity_type: str | None = Query(None, max_length=50), page: int = Query(1, ge=1), _: User = Admin, db: Session = DB) -> dict:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    items, total = paginate(db, stmt, page, 50)
    return {"items": [{"id": str(x.id), "actor_id": str(x.actor_id) if x.actor_id else None, "action": x.action,
                       "entity_type": x.entity_type, "entity_id": x.entity_id, "before": x.before, "after": x.after,
                       "trace_id": x.trace_id, "created_at": x.created_at} for x in items], "total": total, "page": page}


# ------------------------------------------------------------------ analytics

@router.get("/analytics")
def analytics(_: User = Admin, db: Session = DB) -> dict:
    now = datetime.now(UTC)
    d7, d14, d30 = now - timedelta(days=7), now - timedelta(days=14), now - timedelta(days=30)
    users_total = db.scalar(select(func.count()).select_from(User)) or 0
    activated = db.scalar(select(func.count(distinct(Progress.user_id))).where(Progress.status == "completed")) or 0
    wal = db.scalar(select(func.count(distinct(UsageEvent.user_id))).where(UsageEvent.created_at >= d7)) or 0
    cohort = db.scalars(select(User.id).where(User.created_at >= d14, User.created_at < d7)).all()
    retained = 0
    if cohort:
        retained = db.scalar(select(func.count(distinct(UsageEvent.user_id))).where(
            UsageEvent.user_id.in_(cohort), UsageEvent.created_at >= d7)) or 0
    paid = db.scalar(select(func.count(distinct(Subscription.user_id))).where(Subscription.plan != "free", Subscription.status == "active")) or 0

    def count_event(name: str, since: datetime) -> int:
        return db.scalar(select(func.count()).select_from(UsageEvent).where(UsageEvent.event_type == name, UsageEvent.created_at >= since)) or 0

    series: dict[str, dict[str, int]] = {}
    for ev_type, ts in db.execute(select(UsageEvent.event_type, UsageEvent.created_at).where(
            UsageEvent.created_at >= d14, UsageEvent.event_type.in_(("lesson_completed", "challenge_attempted", "agent_run", "user_registered")))):
        day = ts.date().isoformat()
        series.setdefault(day, {}).setdefault(ev_type, 0)
        series[day][ev_type] += 1
    days = [(now - timedelta(days=i)).date().isoformat() for i in range(13, -1, -1)]
    cost = db.scalar(select(func.coalesce(func.sum(AgentRun.cost_usd), 0)).where(AgentRun.created_at >= d30)) or 0
    unknown_cost = db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.created_at >= d30, AgentRun.cost_usd.is_(None))) or 0
    by_provider = dict(db.execute(select(AgentRun.provider, func.count()).where(AgentRun.created_at >= d30).group_by(AgentRun.provider)).all())
    return {
        "kpis": {
            "users_total": users_total,
            "activation_rate": round(activated / users_total, 3) if users_total else 0,
            "weekly_active_learners": wal,
            "week1_retention": round(retained / len(cohort), 3) if cohort else None,
            "lesson_completions_7d": count_event("lesson_completed", d7),
            "challenge_completions_7d": db.scalar(select(func.count()).select_from(ChallengeAttempt).where(
                ChallengeAttempt.points_awarded > 0, ChallengeAttempt.created_at >= d7)) or 0,
            "agent_runs_7d": count_event("agent_run", d7),
            "agent_demo_users_7d": db.scalar(select(func.count(distinct(UsageEvent.user_id))).where(
                UsageEvent.event_type == "agent_run", UsageEvent.created_at >= d7)) or 0,
            "projects_verified": db.scalar(select(func.count()).select_from(PortfolioEntry).where(PortfolioEntry.verified.is_(True))) or 0,
            "paid_conversion": round(paid / users_total, 3) if users_total else 0,
            "inference_cost_usd_30d": float(cost),
            "runs_without_price_30d": unknown_cost,
        },
        "series": [{"date": d, **series.get(d, {})} for d in days],
        "runs_by_provider_30d": by_provider,
        "pending_reviews": db.scalar(select(func.count()).select_from(ChallengeAttempt).where(ChallengeAttempt.status == "pending_review")) or 0,
        "privacy_note": "Analytics use pseudonymous user ids and allowlisted event properties only.",
    }


# ------------------------------------------------------------------ announcements

class AnnouncementIn(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    body_md: str = Field(..., min_length=3, max_length=10_000)
    publish: bool = False


@router.post("/announcements", status_code=201)
def create_announcement(body: AnnouncementIn, request: Request, user: User = Author, db: Session = DB) -> dict:
    a = Announcement(title=body.title, body_md=body.body_md, status="published" if body.publish else "draft",
                     published_at=datetime.now(UTC) if body.publish else None)
    db.add(a)
    db.flush()
    audit(db, user, "announcement.create", "announcement", a.id, after={"status": a.status}, request=request)
    db.commit()
    return {"id": str(a.id), "status": a.status}


@public_router.get("/announcements")
def list_announcements(db: Session = DB) -> dict:
    rows = db.scalars(select(Announcement).where(Announcement.status == "published").order_by(Announcement.published_at.desc()).limit(5)).all()
    return {"items": [{"id": str(a.id), "title": a.title, "body_md": a.body_md, "published_at": a.published_at} for a in rows]}
