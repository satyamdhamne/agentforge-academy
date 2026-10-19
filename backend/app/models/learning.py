from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, Timestamps, UUIDPk

STATUS_CHECK = "status IN ('draft', 'review', 'published', 'archived')"
LEVEL_CHECK = "level IN ('beginner', 'intermediate', 'advanced', 'expert')"
TIER_CHECK = "tier IN ('free', 'pro', 'team')"


class LearningTrack(UUIDPk, Timestamps, Base):
    __tablename__ = "learning_tracks"
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(50), default="book")
    color: Mapped[str] = mapped_column(String(20), default="indigo")
    level: Mapped[str] = mapped_column(String(20), default="beginner")
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    tier: Mapped[str] = mapped_column(String(10), default="free")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    tags: Mapped[list[Any]] = mapped_column(default=list)
    outcomes: Mapped[list[Any]] = mapped_column(default=list)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    courses: Mapped[list[Course]] = relationship(back_populates="track", order_by="Course.order_index", cascade="all, delete-orphan")

    __table_args__ = (CheckConstraint(STATUS_CHECK, name="status"), CheckConstraint(LEVEL_CHECK, name="level"),
                      CheckConstraint(TIER_CHECK, name="tier"))


class Course(UUIDPk, Timestamps, Base):
    __tablename__ = "courses"
    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learning_tracks.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(String(500), default="")
    level: Mapped[str] = mapped_column(String(20), default="beginner")
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    estimated_hours: Mapped[float] = mapped_column(Float, default=1.0)
    tier: Mapped[str] = mapped_column(String(10), default="free")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    track: Mapped[LearningTrack] = relationship(back_populates="courses")
    modules: Mapped[list[Module]] = relationship(back_populates="course", order_by="Module.order_index", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("track_id", "slug"), CheckConstraint(STATUS_CHECK, name="status"),
                      CheckConstraint(TIER_CHECK, name="tier"))


class Module(UUIDPk, Timestamps, Base):
    __tablename__ = "modules"
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(String(500), default="")
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    course: Mapped[Course] = relationship(back_populates="modules")
    lessons: Mapped[list[Lesson]] = relationship(back_populates="module", order_by="Lesson.order_index", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("course_id", "slug"),)


class Lesson(UUIDPk, Timestamps, Base):
    __tablename__ = "lessons"
    module_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("modules.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(150), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(String(500), default="")
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=15)
    level: Mapped[str] = mapped_column(String(20), default="beginner")
    tier: Mapped[str] = mapped_column(String(10), default="free")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    prerequisites: Mapped[list[Any]] = mapped_column(default=list)  # lesson slugs
    tags: Mapped[list[Any]] = mapped_column(default=list)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    published_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lesson_versions.id", ondelete="SET NULL", use_alter=True, name="fk_lessons_published_version")
    )
    module: Mapped[Module] = relationship(back_populates="lessons")
    published_version: Mapped[LessonVersion | None] = relationship(foreign_keys=[published_version_id], post_update=True)

    __table_args__ = (CheckConstraint(STATUS_CHECK, name="status"), CheckConstraint(TIER_CHECK, name="tier"),
                      Index("ix_lessons_status", "status"))


class LessonVersion(UUIDPk, Base):
    """Immutable content snapshots. Editing creates a new draft version; publishing points the lesson at it."""

    __tablename__ = "lesson_versions"
    lesson_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    content: Mapped[dict[str, Any]] = mapped_column()
    change_note: Mapped[str] = mapped_column(String(500), default="")
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("lesson_id", "version"), CheckConstraint(STATUS_CHECK, name="status"))


class Enrollment(UUIDPk, Base):
    __tablename__ = "enrollments"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learning_tracks.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("user_id", "track_id"),)


class Progress(UUIDPk, Timestamps, Base):
    __tablename__ = "progress"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    lesson_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    quiz_score: Mapped[float | None] = mapped_column(Float)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "lesson_id"),
                      CheckConstraint("status IN ('in_progress', 'completed')", name="status"),
                      Index("ix_progress_user_completed", "user_id", "completed_at"))


class Exercise(UUIDPk, Timestamps, Base):
    """Unified table for lesson exercises and standalone challenges.

    `spec` holds grading data (tests, correct options, rubric) and is NEVER sent to clients as-is.
    """

    __tablename__ = "exercises"
    slug: Mapped[str] = mapped_column(String(150), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lessons.id", ondelete="SET NULL"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # code | multiple_choice | manual_review
    category: Mapped[str] = mapped_column(String(30))  # coding | debugging | architecture | prompt | rag | agent | security | cloud | interview
    difficulty: Mapped[str] = mapped_column(String(20))
    language: Mapped[str | None] = mapped_column(String(20))
    prompt_md: Mapped[str] = mapped_column(Text)
    starter_code: Mapped[str] = mapped_column(Text, default="")
    spec: Mapped[dict[str, Any]] = mapped_column(default=dict)
    hints: Mapped[list[Any]] = mapped_column(default=list)
    explanation_md: Mapped[str] = mapped_column(Text, default="")
    solution: Mapped[str] = mapped_column(Text, default="")
    points: Mapped[int] = mapped_column(Integer, default=10)
    time_limit_minutes: Mapped[int | None] = mapped_column(Integer)
    is_daily_eligible: Mapped[bool] = mapped_column(Boolean, default=True)
    is_weekly_project: Mapped[bool] = mapped_column(Boolean, default=False)
    tier: Mapped[str] = mapped_column(String(10), default="free")
    status: Mapped[str] = mapped_column(String(20), default="published")
    tags: Mapped[list[Any]] = mapped_column(default=list)

    __table_args__ = (
        CheckConstraint("kind IN ('code', 'multiple_choice', 'manual_review')", name="kind"),
        CheckConstraint("difficulty IN ('beginner', 'intermediate', 'advanced', 'expert')", name="difficulty"),
        CheckConstraint("points >= 0", name="points_nonneg"),
        CheckConstraint(STATUS_CHECK, name="status"), CheckConstraint(TIER_CHECK, name="tier"),
        Index("ix_exercises_difficulty_category", "difficulty", "category"),
    )


class ChallengeAttempt(UUIDPk, Base):
    __tablename__ = "challenge_attempts"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    exercise_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"))
    submission: Mapped[dict[str, Any]] = mapped_column()
    submission_hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))
    score: Mapped[float] = mapped_column(Float, default=0.0)
    points_awarded: Mapped[int] = mapped_column(Integer, default=0)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    execution_mode: Mapped[str] = mapped_column(String(20), default="none")  # sandbox | unavailable | none
    result: Mapped[dict[str, Any]] = mapped_column(default=dict)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    review_feedback: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('passed', 'failed', 'error', 'not_graded', 'pending_review', 'reviewed')", name="status"),
        Index("ix_attempts_user_exercise", "user_id", "exercise_id"),
        Index("ix_attempts_status_created", "status", "created_at"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_attempts_idempotency"),
    )


class HintReveal(UUIDPk, Base):
    __tablename__ = "hint_reveals"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    exercise_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"))
    hint_index: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("user_id", "exercise_id", "hint_index"),)


class Assessment(UUIDPk, Timestamps, Base):
    __tablename__ = "assessments"
    slug: Mapped[str] = mapped_column(String(150), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    pass_threshold: Mapped[float] = mapped_column(Float, default=0.7)
    questions: Mapped[list[Question]] = relationship(back_populates="assessment", order_by="Question.order_index")


class Question(UUIDPk, Timestamps, Base):
    """Quiz and interview questions. `answer` is server-side only."""

    __tablename__ = "questions"
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    interview_track: Mapped[str | None] = mapped_column(String(50), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="mcq")
    difficulty: Mapped[str] = mapped_column(String(20), default="beginner")
    prompt_md: Mapped[str] = mapped_column(Text)
    options: Mapped[list[Any]] = mapped_column(default=list)
    answer: Mapped[dict[str, Any]] = mapped_column(default=dict)
    concise_answer: Mapped[str] = mapped_column(Text, default="")
    explanation_md: Mapped[str] = mapped_column(Text, default="")
    follow_ups: Mapped[list[Any]] = mapped_column(default=list)
    common_mistakes: Mapped[list[Any]] = mapped_column(default=list)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    assessment: Mapped[Assessment | None] = relationship(back_populates="questions")
