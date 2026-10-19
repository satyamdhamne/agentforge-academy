"""Workflows (Agent Builder, Phase 5), prompts & evaluations (Phase 4), achievements, portfolio,
billing and operational tables. Tables for later phases are created now so the schema is stable."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Timestamps, UUIDPk

# ---------------------------------------------------------------------------- workflows


class Workflow(UUIDPk, Timestamps, Base):
    """Agent Builder graph. Node configs reference credentials by CredentialRef id only - never raw secrets."""

    __tablename__ = "workflows"
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    definition_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")


class WorkflowNode(UUIDPk, Base):
    __tablename__ = "workflow_nodes"
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    node_key: Mapped[str] = mapped_column(String(64))
    node_type: Mapped[str] = mapped_column(String(30))
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    position: Mapped[dict[str, Any]] = mapped_column(default=dict)
    __table_args__ = (
        UniqueConstraint("workflow_id", "node_key"),
        CheckConstraint("node_type IN ('input', 'llm', 'prompt', 'tool', 'retrieval', 'condition', 'memory', "
                        "'human_approval', 'evaluation', 'output')", name="node_type"),
    )


class WorkflowEdge(UUIDPk, Base):
    __tablename__ = "workflow_edges"
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    source_key: Mapped[str] = mapped_column(String(64))
    target_key: Mapped[str] = mapped_column(String(64))
    condition: Mapped[dict[str, Any] | None] = mapped_column()


# ---------------------------------------------------------------------------- prompts & evaluation


class PromptTemplate(UUIDPk, Timestamps, Base):
    __tablename__ = "prompt_templates"
    slug: Mapped[str] = mapped_column(String(150), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="published")
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="SET NULL", use_alter=True, name="fk_prompt_templates_current_version")
    )


class PromptVersion(UUIDPk, Base):
    __tablename__ = "prompt_versions"
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompt_templates.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    system: Mapped[str] = mapped_column(Text, default="")
    user_template: Mapped[str] = mapped_column(Text)
    variables: Mapped[list[Any]] = mapped_column(default=list)
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    change_note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("template_id", "version"),)


class Evaluation(UUIDPk, Base):
    __tablename__ = "evaluations"
    name: Mapped[str] = mapped_column(String(200))
    target_type: Mapped[str] = mapped_column(String(20))  # agent | prompt | rag
    target_id: Mapped[uuid.UUID | None] = mapped_column()
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    summary: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvaluationCase(UUIDPk, Base):
    __tablename__ = "evaluation_cases"
    evaluation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"), index=True)
    case_key: Mapped[str] = mapped_column(String(100))
    input: Mapped[dict[str, Any]] = mapped_column()
    expected: Mapped[dict[str, Any]] = mapped_column(default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column()
    passed: Mapped[bool | None] = mapped_column(Boolean)


# ---------------------------------------------------------------------------- achievements & portfolio


class Achievement(UUIDPk, Base):
    """Badges are awarded only by server-side rules over verifiable records (criteria.type)."""

    __tablename__ = "achievements"
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(300))
    icon: Mapped[str] = mapped_column(String(50), default="award")
    criteria: Mapped[dict[str, Any]] = mapped_column()


class UserAchievement(UUIDPk, Base):
    __tablename__ = "user_achievements"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    achievement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("achievements.id", ondelete="CASCADE"))
    evidence: Mapped[dict[str, Any]] = mapped_column(default=dict)
    awarded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("user_id", "achievement_id"),)


class Project(UUIDPk, Timestamps, Base):
    """Real-world portfolio projects learners can build."""

    __tablename__ = "projects"
    slug: Mapped[str] = mapped_column(String(150), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(20))
    track_slug: Mapped[str | None] = mapped_column(String(100))
    skills: Mapped[list[Any]] = mapped_column(default=list)
    requirements: Mapped[list[Any]] = mapped_column(default=list)
    estimated_hours: Mapped[int] = mapped_column(Integer, default=10)
    tier: Mapped[str] = mapped_column(String(10), default="free")
    status: Mapped[str] = mapped_column(String(20), default="published")


class Portfolio(UUIDPk, Timestamps, Base):
    __tablename__ = "portfolios"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    headline: Mapped[str] = mapped_column(String(200), default="")
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)


class PortfolioEntry(UUIDPk, Timestamps, Base):
    __tablename__ = "portfolio_entries"
    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    repo_url: Mapped[str | None] = mapped_column(String(500))
    deployment_url: Mapped[str | None] = mapped_column(String(500))
    notes_md: Mapped[str] = mapped_column(Text, default="")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------------------------------------------------------------------- billing


class Subscription(UUIDPk, Timestamps, Base):
    """Plan assignment. `provider`/`provider_ref` stay null until a payment provider is integrated."""

    __tablename__ = "subscriptions"
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    plan: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="active")
    provider: Mapped[str | None] = mapped_column(String(30))
    provider_ref: Mapped[str | None] = mapped_column(String(200))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("plan IN ('free', 'pro', 'team')", name="plan"),
        CheckConstraint("(user_id IS NOT NULL) OR (organization_id IS NOT NULL)", name="has_owner"),
    )


class Entitlement(UUIDPk, Base):
    __tablename__ = "entitlements"
    plan: Mapped[str] = mapped_column(String(20))
    feature_key: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    limit_value: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("plan", "feature_key"),)


# ---------------------------------------------------------------------------- operations


class UsageEvent(UUIDPk, Base):
    """Product analytics events. Properties must not contain free text or personal data."""

    __tablename__ = "usage_events"
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(60))
    properties: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("ix_usage_events_type_created", "event_type", "created_at"),
                      Index("ix_usage_events_user_created", "user_id", "created_at"))


class AuditLog(UUIDPk, Base):
    __tablename__ = "audit_logs"
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(100))
    before: Mapped[dict[str, Any] | None] = mapped_column()
    after: Mapped[dict[str, Any] | None] = mapped_column()
    ip: Mapped[str | None] = mapped_column(String(64))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)


class Announcement(UUIDPk, Timestamps, Base):
    __tablename__ = "announcements"
    title: Mapped[str] = mapped_column(String(200))
    body_md: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
