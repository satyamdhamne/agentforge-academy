from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, Timestamps, UUIDPk


class Agent(UUIDPk, Timestamps, Base):
    __tablename__ = "agents"
    number: Mapped[int] = mapped_column(Integer, unique=True)
    slug: Mapped[str] = mapped_column(String(150), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100), index=True)
    level: Mapped[str] = mapped_column(String(20))
    build_hours: Mapped[int] = mapped_column(Integer, default=4)
    summary: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(20))
    has_reference_impl: Mapped[bool] = mapped_column(Boolean, default=False)
    tier: Mapped[str] = mapped_column(String(10), default="free")
    status: Mapped[str] = mapped_column(String(20), default="published")
    tags: Mapped[list[Any]] = mapped_column(default=list)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_versions.id", ondelete="SET NULL", use_alter=True, name="fk_agents_current_version")
    )
    current_version: Mapped[AgentVersion | None] = relationship(foreign_keys=[current_version_id], post_update=True)

    __table_args__ = (CheckConstraint("verdict IN ('agent', 'workflow', 'rag', 'deterministic')", name="verdict"),)


class AgentVersion(UUIDPk, Base):
    __tablename__ = "agent_versions"
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    blueprint: Mapped[dict[str, Any]] = mapped_column()
    example_runs: Mapped[list[Any]] = mapped_column(default=list)
    eval_report: Mapped[dict[str, Any] | None] = mapped_column()
    status: Mapped[str] = mapped_column(String(20), default="published")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    files: Mapped[list[AgentFile]] = relationship(back_populates="version", cascade="all, delete-orphan", order_by="AgentFile.path")

    __table_args__ = (UniqueConstraint("agent_id", "version"),)


class AgentFile(UUIDPk, Base):
    __tablename__ = "agent_files"
    agent_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_versions.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(300))
    language: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    version: Mapped[AgentVersion] = relationship(back_populates="files")

    __table_args__ = (UniqueConstraint("agent_version_id", "path"),)


class AgentRun(UUIDPk, Base):
    __tablename__ = "agent_runs"
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(30))
    input: Mapped[dict[str, Any]] = mapped_column()
    output: Mapped[dict[str, Any] | None] = mapped_column()
    pending_actions: Mapped[list[Any]] = mapped_column(default=list)
    approval_result: Mapped[dict[str, Any] | None] = mapped_column()
    trace_id: Mapped[str] = mapped_column(String(64))
    trace: Mapped[list[Any]] = mapped_column(default=list)
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(100))
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed', 'awaiting_approval', 'approved', 'rejected', 'cancelled')",
                        name="status"),
        Index("ix_agent_runs_user_created", "user_id", "created_at"),
        Index("ix_agent_runs_agent", "agent_id"),
    )
