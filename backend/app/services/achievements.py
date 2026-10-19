"""Server-side achievement rules. Badges are only granted from verifiable database records."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from ..models import (
    Achievement,
    AgentRun,
    ChallengeAttempt,
    Course,
    LearningTrack,
    Lesson,
    Module,
    Progress,
    User,
    UserAchievement,
)


def _lessons_completed(db: Session, user: User) -> int:
    return db.scalar(select(func.count()).select_from(Progress).where(Progress.user_id == user.id, Progress.status == "completed")) or 0


def _challenges_passed(db: Session, user: User) -> int:
    return db.scalar(select(func.count(distinct(ChallengeAttempt.exercise_id))).where(
        ChallengeAttempt.user_id == user.id, ChallengeAttempt.status.in_(("passed", "reviewed")),
        ChallengeAttempt.points_awarded > 0)) or 0


def _agent_runs(db: Session, user: User) -> int:
    return db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.user_id == user.id,
                                                                     AgentRun.status != "failed")) or 0


def activity_days(db: Session, user: User) -> list[date]:
    """Distinct UTC days with a completed lesson or a challenge attempt."""
    days: set[date] = set()
    for (ts,) in db.execute(select(Progress.completed_at).where(Progress.user_id == user.id, Progress.completed_at.is_not(None))):
        days.add(ts.date())
    for (ts,) in db.execute(select(ChallengeAttempt.created_at).where(ChallengeAttempt.user_id == user.id)):
        days.add(ts.date())
    return sorted(days)


def current_streak(db: Session, user: User, today: date | None = None) -> int:
    days = set(activity_days(db, user))
    day = today or datetime.now(UTC).date()
    if day not in days:
        day -= timedelta(days=1)  # streak survives until the end of today
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def _track_completed(db: Session, user: User, track_slug: str) -> bool:
    lesson_ids = db.scalars(select(Lesson.id).join(Module).join(Course).join(LearningTrack).where(
        LearningTrack.slug == track_slug, Lesson.status == "published")).all()
    if not lesson_ids:
        return False
    done = db.scalar(select(func.count()).select_from(Progress).where(
        Progress.user_id == user.id, Progress.status == "completed", Progress.lesson_id.in_(lesson_ids))) or 0
    return done == len(lesson_ids)


def evaluate(db: Session, user: User) -> list[Achievement]:
    """Grant any newly satisfied achievements. Returns the newly granted ones."""
    owned = set(db.scalars(select(UserAchievement.achievement_id).where(UserAchievement.user_id == user.id)).all())
    stats = {"lessons_completed": _lessons_completed(db, user), "challenges_passed": _challenges_passed(db, user),
             "agent_runs": _agent_runs(db, user), "streak_days": current_streak(db, user)}
    new = []
    for ach in db.scalars(select(Achievement)).all():
        if ach.id in owned:
            continue
        c = ach.criteria
        kind = c.get("type")
        ok = False
        if kind in stats:
            ok = stats[kind] >= int(c.get("min", 1))
        elif kind == "track_completed":
            ok = _track_completed(db, user, c["track"])
        if ok:
            db.add(UserAchievement(user_id=user.id, achievement_id=ach.id,
                                   evidence={"rule": c, "observed": stats.get(kind, True)}))
            new.append(ach)
    return new
