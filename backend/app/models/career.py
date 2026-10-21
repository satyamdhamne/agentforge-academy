"""Phase 5 workflow runs and Phase 6 interview sessions, mentor conversations and skill assessments."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UUIDPk

# ---------------------------------------------------------------------------- Agent Builder runs


class WorkflowRun(UUIDPk, Base):
    __tablename__ = "workflow_runs"
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(30))
    mode: Mapped[str] = mapped_column(String(10), default="mock")  # mock | live
    definition: Mapped[dict[str, Any]] = mapped_column()  # snapshot of the validated graph that ran
    input: Mapped[dict[str, Any]] = mapped_column(default=dict)
    state: Mapped[dict[str, Any]] = mapped_column(default=dict)
    output: Mapped[dict[str, Any] | None] = mapped_column()
    trace: Mapped[list[Any]] = mapped_column(default=list)
    node_status: Mapped[dict[str, Any]] = mapped_column(default=dict)
    pending: Mapped[dict[str, Any] | None] = mapped_column()  # approval request while paused
    steps: Mapped[int] = mapped_column(Integer, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed', 'awaiting_approval', 'rejected', 'cancelled')", name="status"),
        Index("ix_workflow_runs_user_created", "user_id", "created_at"),
    )


# ---------------------------------------------------------------------------- Interview Arena


class InterviewSession(UUIDPk, Base):
    __tablename__ = "interview_sessions"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    track: Mapped[str] = mapped_column(String(50))
    difficulty: Mapped[str | None] = mapped_column(String(20))
    question_ids: Mapped[list[Any]] = mapped_column(default=list)
    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    scorer: Mapped[str] = mapped_column(String(20), default="rubric")  # rubric | model
    summary: Mapped[dict[str, Any] | None] = mapped_column()
    overall: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("status IN ('in_progress', 'completed')", name="status"),)


class InterviewAnswer(UUIDPk, Base):
    __tablename__ = "interview_answers"
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    answer_text: Mapped[str] = mapped_column(Text)
    scores: Mapped[dict[str, Any]] = mapped_column(default=dict)
    feedback: Mapped[dict[str, Any]] = mapped_column(default=dict)
    overall: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------- AI mentor


class MentorMessage(UUIDPk, Base):
    """Stored only for learners who opted in to the mentor; deletable at any time."""

    __tablename__ = "mentor_messages"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20))  # user | mentor
    content: Mapped[str] = mapped_column(Text)
    context: Mapped[dict[str, Any]] = mapped_column(default=dict)
    citations: Mapped[list[Any]] = mapped_column(default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_mentor_messages_user_created", "user_id", "created_at"),
                      CheckConstraint("role IN ('user', 'mentor')", name="role"))


class SkillAssessment(UUIDPk, Base):
    __tablename__ = "skill_assessments"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    answers: Mapped[dict[str, Any]] = mapped_column(default=dict)
    scores: Mapped[dict[str, Any]] = mapped_column(default=dict)
    recommendations: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
