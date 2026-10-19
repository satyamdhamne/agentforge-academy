"""Learning catalog, lessons, quizzes, progress, enrollments, dashboard and achievements."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..api.deps import DB, CurrentUser, OptionalUser
from ..core.errors import AppError, NotFound
from ..models import (
    Achievement,
    AgentRun,
    Assessment,
    ChallengeAttempt,
    Course,
    Enrollment,
    Exercise,
    LearningTrack,
    Lesson,
    Module,
    Progress,
    User,
    UserAchievement,
)
from ..services import achievements as ach
from ..services.common import can_access_tier, plan_for, track
from .challenges import daily_challenge, exercise_card

router = APIRouter(tags=["learning"])


# ------------------------------------------------------------------ helpers

def _completed_ids(db: Session, user: User | None) -> set[uuid.UUID]:
    if user is None:
        return set()
    return set(db.scalars(select(Progress.lesson_id).where(Progress.user_id == user.id, Progress.status == "completed")).all())


def _track_lessons(track: LearningTrack) -> list[Lesson]:
    return [lesson for c in track.courses for m in c.modules for lesson in m.lessons]


def _track_summary(t: LearningTrack, done: set[uuid.UUID], enrolled: set[uuid.UUID]) -> dict:
    lessons = _track_lessons(t)
    published = [lesson for lesson in lessons if lesson.status == "published"]
    completed = sum(1 for lesson in published if lesson.id in done)
    return {
        "slug": t.slug, "title": t.title, "summary": t.summary, "icon": t.icon, "color": t.color, "level": t.level,
        "tier": t.tier, "order": t.order_index, "tags": t.tags, "courses": len(t.courses), "lessons_total": len(lessons),
        "lessons_available": len(published), "lessons_completed": completed,
        "progress": round(completed / len(published), 3) if published else 0.0, "enrolled": t.id in enrolled,
        "estimated_hours": round(sum(c.estimated_hours for c in t.courses), 1),
    }


def _load_tracks(db: Session):
    return db.scalars(select(LearningTrack).where(LearningTrack.status == "published").order_by(LearningTrack.order_index)
                      .options(selectinload(LearningTrack.courses).selectinload(Course.modules).selectinload(Module.lessons))).all()


def _lesson_or_404(db: Session, slug: str) -> Lesson:
    lesson = db.scalar(select(Lesson).where(Lesson.slug == slug))
    if lesson is None or lesson.status != "published" or lesson.published_version is None:
        raise NotFound("Lesson not found")
    return lesson


def _quiz(db: Session, lesson: Lesson) -> Assessment | None:
    return db.scalar(select(Assessment).where(Assessment.lesson_id == lesson.id).options(selectinload(Assessment.questions)))


# ------------------------------------------------------------------ catalog

@router.get("/tracks")
def list_tracks(user: User | None = OptionalUser, db: Session = DB) -> dict:
    done = _completed_ids(db, user)
    enrolled = set(db.scalars(select(Enrollment.track_id).where(Enrollment.user_id == user.id)).all()) if user else set()
    return {"items": [_track_summary(t, done, enrolled) for t in _load_tracks(db)]}


@router.get("/tracks/{slug}")
def get_track(slug: str, user: User | None = OptionalUser, db: Session = DB) -> dict:
    t = db.scalar(select(LearningTrack).where(LearningTrack.slug == slug, LearningTrack.status == "published")
                  .options(selectinload(LearningTrack.courses).selectinload(Course.modules).selectinload(Module.lessons)))
    if t is None:
        raise NotFound("Track not found")
    done = _completed_ids(db, user)
    enrolled = set(db.scalars(select(Enrollment.track_id).where(Enrollment.user_id == user.id)).all()) if user else set()
    plan = plan_for(db, user)
    summary = _track_summary(t, done, enrolled)
    summary["description"] = t.description
    summary["outcomes"] = t.outcomes
    summary["courses_detail"] = [{
        "slug": c.slug, "title": c.title, "summary": c.summary, "level": c.level, "tier": c.tier,
        "estimated_hours": c.estimated_hours,
        "modules": [{
            "slug": m.slug, "title": m.title, "summary": m.summary,
            "lessons": [{
                "slug": lesson.slug, "title": lesson.title, "summary": lesson.summary, "minutes": lesson.estimated_minutes,
                "level": lesson.level, "tier": lesson.tier, "available": lesson.status == "published",
                "locked": not can_access_tier(plan, lesson.tier), "completed": lesson.id in done,
            } for lesson in m.lessons],
        } for m in c.modules],
    } for c in t.courses]
    return summary


@router.post("/tracks/{slug}/enroll", status_code=201)
def enroll(slug: str, user: User = CurrentUser, db: Session = DB) -> dict:
    t = db.scalar(select(LearningTrack).where(LearningTrack.slug == slug, LearningTrack.status == "published"))
    if t is None:
        raise NotFound("Track not found")
    if not db.scalar(select(Enrollment.id).where(Enrollment.user_id == user.id, Enrollment.track_id == t.id)):
        db.add(Enrollment(user_id=user.id, track_id=t.id))
        track(db, user.id, "track_enrolled", track=slug)
        db.commit()
    return {"enrolled": True}


@router.get("/lessons/{slug}")
def get_lesson(slug: str, user: User | None = OptionalUser, db: Session = DB) -> dict:
    lesson = _lesson_or_404(db, slug)
    module = lesson.module
    course = module.course
    trk = course.track
    meta = {"slug": lesson.slug, "title": lesson.title, "summary": lesson.summary, "minutes": lesson.estimated_minutes,
            "level": lesson.level, "tier": lesson.tier, "tags": lesson.tags, "prerequisites": lesson.prerequisites,
            "breadcrumb": {"track": {"slug": trk.slug, "title": trk.title}, "course": course.title, "module": module.title},
            "version": lesson.published_version.version,
            "updated_at": lesson.published_version.published_at or lesson.published_version.created_at}
    plan = plan_for(db, user)
    if not can_access_tier(plan, lesson.tier):
        return {**meta, "locked": True, "required_tier": lesson.tier, "content": None, "quiz": [], "exercises": []}

    ordered = [x for c in trk.courses for m in c.modules for x in m.lessons if x.status == "published"]
    idx = next(i for i, x in enumerate(ordered) if x.id == lesson.id)
    nav = {"prev": {"slug": ordered[idx - 1].slug, "title": ordered[idx - 1].title} if idx > 0 else None,
           "next": {"slug": ordered[idx + 1].slug, "title": ordered[idx + 1].title} if idx + 1 < len(ordered) else None}
    quiz = _quiz(db, lesson)
    progress = None
    if user:
        p = db.scalar(select(Progress).where(Progress.user_id == user.id, Progress.lesson_id == lesson.id))
        if p is None:
            p = Progress(user_id=user.id, lesson_id=lesson.id, status="in_progress")
            db.add(p)
            track(db, user.id, "lesson_started", lesson=lesson.slug)
        p.last_viewed_at = datetime.now(UTC)
        db.commit()
        progress = {"status": p.status, "quiz_score": p.quiz_score, "completed_at": p.completed_at}
    exercises = db.scalars(select(Exercise).where(Exercise.lesson_id == lesson.id, Exercise.status == "published")).all()
    return {
        **meta, "locked": False, "content": lesson.published_version.content, "navigation": nav, "progress": progress,
        "quiz": [{"id": str(q.id), "prompt": q.prompt_md, "options": q.options} for q in (quiz.questions if quiz else [])],
        "quiz_pass_threshold": quiz.pass_threshold if quiz else None,
        "exercises": [exercise_card(e) for e in exercises],
    }


class QuizIn(BaseModel):
    answers: dict[str, int] = Field(..., description="question id -> selected option index")


@router.post("/lessons/{slug}/quiz")
def submit_quiz(slug: str, body: QuizIn, user: User = CurrentUser, db: Session = DB) -> dict:
    lesson = _lesson_or_404(db, slug)
    quiz = _quiz(db, lesson)
    if quiz is None or not quiz.questions:
        raise AppError("This lesson has no quiz.", code="no_quiz")
    results = []
    for q in quiz.questions:
        chosen = body.answers.get(str(q.id))
        correct = q.answer.get("index")
        results.append({"id": str(q.id), "correct": chosen == correct, "correct_index": correct, "explanation": q.explanation_md})
    score = round(sum(r["correct"] for r in results) / len(results), 3)
    p = db.scalar(select(Progress).where(Progress.user_id == user.id, Progress.lesson_id == lesson.id))
    if p is None:
        p = Progress(user_id=user.id, lesson_id=lesson.id, status="in_progress")
        db.add(p)
    p.quiz_score = max(p.quiz_score or 0.0, score)
    track(db, user.id, "quiz_submitted", lesson=lesson.slug, score=score)
    db.commit()
    return {"score": score, "passed": score >= quiz.pass_threshold, "threshold": quiz.pass_threshold, "results": results}


class ProgressIn(BaseModel):
    status: str = Field(..., pattern="^(in_progress|completed)$")


@router.post("/lessons/{slug}/progress")
def update_progress(slug: str, body: ProgressIn, request: Request, user: User = CurrentUser, db: Session = DB) -> dict:
    lesson = _lesson_or_404(db, slug)
    if not can_access_tier(plan_for(db, user), lesson.tier):
        raise AppError("Upgrade required for this lesson.", code="upgrade_required", status_code=402)
    p = db.scalar(select(Progress).where(Progress.user_id == user.id, Progress.lesson_id == lesson.id))
    if p is None:
        p = Progress(user_id=user.id, lesson_id=lesson.id, status="in_progress")
        db.add(p)
    new_badges: list[Achievement] = []
    if body.status == "completed" and p.status != "completed":
        quiz = _quiz(db, lesson)
        if quiz and quiz.questions and (p.quiz_score or 0) < quiz.pass_threshold:
            raise AppError(f"Pass the lesson quiz (≥{int(quiz.pass_threshold * 100)}%) to complete this lesson.",
                           code="quiz_required", status_code=409)
        p.status = "completed"
        p.completed_at = datetime.now(UTC)
        track(db, user.id, "lesson_completed", lesson=lesson.slug)
        db.flush()
        new_badges = ach.evaluate(db, user)
    elif body.status == "in_progress" and p.status != "completed":
        p.status = "in_progress"
    db.commit()
    return {"status": p.status, "completed_at": p.completed_at,
            "new_achievements": [{"slug": a.slug, "name": a.name, "icon": a.icon} for a in new_badges]}


# ------------------------------------------------------------------ dashboard & achievements

@router.get("/me/dashboard")
def dashboard(user: User = CurrentUser, db: Session = DB) -> dict:
    done = _completed_ids(db, user)
    enrolled_ids = set(db.scalars(select(Enrollment.track_id).where(Enrollment.user_id == user.id)).all())
    tracks = _load_tracks(db)
    enrolled = [_track_summary(t, done, enrolled_ids) for t in tracks if t.id in enrolled_ids]
    points = db.scalar(select(func.coalesce(func.sum(ChallengeAttempt.points_awarded), 0)).where(ChallengeAttempt.user_id == user.id)) or 0
    solved = db.scalar(select(func.count(func.distinct(ChallengeAttempt.exercise_id))).where(
        ChallengeAttempt.user_id == user.id, ChallengeAttempt.points_awarded > 0)) or 0
    runs = db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.user_id == user.id)) or 0

    last = db.scalar(select(Progress).where(Progress.user_id == user.id, Progress.status == "in_progress")
                     .order_by(Progress.last_viewed_at.desc()).limit(1))
    continue_lesson = None
    if last:
        lesson = db.get(Lesson, last.lesson_id)
        if lesson and lesson.status == "published":
            continue_lesson = {"slug": lesson.slug, "title": lesson.title, "track": lesson.module.course.track.title}
    if continue_lesson is None:
        for t in tracks:
            if enrolled_ids and t.id not in enrolled_ids:
                continue
            nxt = next((x for x in _track_lessons(t) if x.status == "published" and x.id not in done), None)
            if nxt:
                continue_lesson = {"slug": nxt.slug, "title": nxt.title, "track": t.title}
                break

    today = datetime.now(UTC).date()
    activity = {(today - timedelta(days=i)).isoformat(): 0 for i in range(6, -1, -1)}
    since = datetime.now(UTC) - timedelta(days=7)
    for (ts,) in db.execute(select(Progress.completed_at).where(Progress.user_id == user.id, Progress.completed_at >= since)):
        activity[ts.date().isoformat()] = activity.get(ts.date().isoformat(), 0) + 1
    for (ts,) in db.execute(select(ChallengeAttempt.created_at).where(ChallengeAttempt.user_id == user.id, ChallengeAttempt.created_at >= since)):
        activity[ts.date().isoformat()] = activity.get(ts.date().isoformat(), 0) + 1

    recent = db.execute(select(Achievement, UserAchievement.awarded_at).join(UserAchievement)
                        .where(UserAchievement.user_id == user.id).order_by(UserAchievement.awarded_at.desc()).limit(4)).all()
    daily = daily_challenge(db)
    recommended = [_track_summary(t, done, enrolled_ids) for t in tracks if t.id not in enrolled_ids][:3]
    return {
        "stats": {"lessons_completed": len(done), "challenges_solved": solved, "points": int(points),
                  "streak_days": ach.current_streak(db, user), "agent_runs": runs},
        "continue_lesson": continue_lesson,
        "enrolled_tracks": enrolled,
        "recommended_tracks": recommended,
        "daily_challenge": exercise_card(daily) if daily else None,
        "activity": [{"date": d, "count": c} for d, c in sorted(activity.items())[-7:]],
        "recent_achievements": [{"slug": a.slug, "name": a.name, "icon": a.icon, "awarded_at": at} for a, at in recent],
        "plan": plan_for(db, user),
    }


@router.get("/achievements")
def list_achievements(user: User | None = OptionalUser, db: Session = DB) -> dict:
    earned: dict[uuid.UUID, Any] = {}
    if user:
        earned = dict(db.execute(select(UserAchievement.achievement_id, UserAchievement.awarded_at)
                                 .where(UserAchievement.user_id == user.id)).all())
    return {"items": [{"slug": a.slug, "name": a.name, "description": a.description, "icon": a.icon,
                       "earned": a.id in earned, "awarded_at": earned.get(a.id)}
                      for a in db.scalars(select(Achievement).order_by(Achievement.name)).all()]}


@router.get("/me/progress")
def my_progress(user: User = CurrentUser, db: Session = DB) -> dict:
    done = _completed_ids(db, user)
    enrolled = set(db.scalars(select(Enrollment.track_id).where(Enrollment.user_id == user.id)).all())
    items = [_track_summary(t, done, enrolled) for t in _load_tracks(db)]
    attempts = db.execute(select(Exercise.category, func.count(func.distinct(ChallengeAttempt.exercise_id)))
                          .join(Exercise, Exercise.id == ChallengeAttempt.exercise_id)
                          .where(ChallengeAttempt.user_id == user.id, ChallengeAttempt.points_awarded > 0)
                          .group_by(Exercise.category)).all()
    return {"tracks": [i for i in items if i["lessons_completed"] or i["enrolled"]],
            "challenges_by_category": {c: n for c, n in attempts},
            "activity_days": [d.isoformat() for d in ach.activity_days(db, user)][-90:],
            "streak_days": ach.current_streak(db, user)}

