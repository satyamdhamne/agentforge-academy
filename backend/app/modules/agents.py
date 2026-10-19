"""Agent Library: catalog, detail pages, source files, runs (with budgets) and human approval of actions."""

from __future__ import annotations

import concurrent.futures
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from agentforge_agents.core import AnthropicProvider, LLMProvider, MockProvider, OpenAICompatibleProvider, run_agent
from agentforge_agents.registry import get_spec

from ..api.deps import DB, CurrentUser, OptionalUser, rate_limit
from ..core.config import get_settings
from ..core.errors import AppError, NotFound
from ..models import Agent, AgentFile, AgentRun, UsageEvent, User
from ..services import achievements as ach
from ..services.common import audit, can_access_tier, entitlement_limit, plan_for, track
from ..services.sandbox import get_sandbox

router = APIRouter(prefix="/agents", tags=["agents"])
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent-run")


def agent_card(a: Agent) -> dict:
    return {"number": a.number, "slug": a.slug, "name": a.name, "category": a.category, "level": a.level,
            "build_hours": a.build_hours, "summary": a.summary, "verdict": a.verdict,
            "has_reference_impl": a.has_reference_impl, "tier": a.tier, "tags": a.tags}


def _agent(db: Session, slug: str) -> Agent:
    a = db.scalar(select(Agent).where(Agent.slug == slug, Agent.status == "published"))
    if a is None:
        raise NotFound("Agent not found")
    return a


def _provider_for(plan: str) -> LLMProvider:
    """Free plan: mock runs only. Paid plans: the server-configured provider. Keys never leave the server."""
    s = get_settings()
    if plan == "free" or s.llm_provider == "mock":
        return MockProvider()
    if s.llm_provider == "openai":
        return OpenAICompatibleProvider(s.openai_api_key, s.openai_model, s.openai_base_url)
    return AnthropicProvider(s.anthropic_api_key, s.anthropic_model)


def _groups_for(user: User) -> list[str]:
    # Document permissions for the RAG demo come from the user's roles, never from request input.
    groups = ["everyone"]
    if user.role_names & {"admin", "author", "reviewer"}:
        groups += ["engineering"]
    if "admin" in user.role_names:
        groups += ["hr", "people-managers"]
    return groups


def _cost(model: str, tin: int, tout: int) -> Decimal | None:
    price = get_settings().model_prices.get(model)
    if not price:
        return Decimal(0) if model.startswith("mock") else None
    return Decimal(str(round(tin / 1e6 * price.get("input_per_mtok", 0) + tout / 1e6 * price.get("output_per_mtok", 0), 6)))


def run_out(r: AgentRun, slug: str | None = None) -> dict:
    return {"id": str(r.id), "agent": slug, "status": r.status, "input": r.input, "output": r.output,
            "pending_actions": r.pending_actions, "approval_result": r.approval_result, "trace_id": r.trace_id,
            "trace": r.trace, "provider": r.provider, "model": r.model, "llm_calls": r.llm_calls, "tool_calls": r.tool_calls,
            "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
            "cost_usd": float(r.cost_usd) if r.cost_usd is not None else None, "latency_ms": r.latency_ms,
            "error": r.error, "created_at": r.created_at, "finished_at": r.finished_at,
            "is_mock": r.provider == "mock"}


# ------------------------------------------------------------------ catalog

@router.get("")
def list_agents(category: str | None = Query(None, max_length=100), verdict: str | None = Query(None, pattern="^(agent|workflow|rag|deterministic)$"),
                level: str | None = Query(None, max_length=20), implemented: bool | None = None,
                q: str | None = Query(None, max_length=100), db: Session = DB) -> dict:
    stmt = select(Agent).where(Agent.status == "published")
    if category:
        stmt = stmt.where(Agent.category == category)
    if verdict:
        stmt = stmt.where(Agent.verdict == verdict)
    if level:
        stmt = stmt.where(Agent.level == level)
    if implemented is not None:
        stmt = stmt.where(Agent.has_reference_impl.is_(implemented))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Agent.name).like(like), func.lower(Agent.summary).like(like), func.lower(Agent.category).like(like)))
    items = db.scalars(stmt.order_by(Agent.has_reference_impl.desc(), Agent.number)).all()
    cats = db.execute(select(Agent.category, func.count()).where(Agent.status == "published").group_by(Agent.category)).all()
    verdicts = db.execute(select(Agent.verdict, func.count()).where(Agent.status == "published").group_by(Agent.verdict)).all()
    return {"items": [agent_card(a) for a in items], "total": len(items),
            "facets": {"categories": dict(sorted(cats)), "verdicts": dict(verdicts)}}


@router.get("/runs/mine")
def my_runs(limit: int = Query(20, ge=1, le=100), user: User = CurrentUser, db: Session = DB) -> dict:
    rows = db.execute(select(AgentRun, Agent.slug).join(Agent, Agent.id == AgentRun.agent_id)
                      .where(AgentRun.user_id == user.id).order_by(AgentRun.created_at.desc()).limit(limit)).all()
    return {"items": [{k: v for k, v in run_out(r, slug).items() if k not in ("trace", "input", "output")} for r, slug in rows]}


@router.get("/runs/{run_id}")
def get_run(run_id: uuid.UUID, user: User = CurrentUser, db: Session = DB) -> dict:
    r = db.get(AgentRun, run_id)
    if r is None or (r.user_id != user.id and "admin" not in user.role_names):
        raise NotFound("Run not found")
    return run_out(r, db.get(Agent, r.agent_id).slug)


@router.get("/{slug}")
def get_agent(slug: str, user: User | None = OptionalUser, db: Session = DB) -> dict:
    a = _agent(db, slug)
    v = a.current_version
    files = db.scalars(select(AgentFile.path).where(AgentFile.agent_version_id == v.id).order_by(AgentFile.path)).all() if v else []
    spec = get_spec(a.slug) if a.has_reference_impl else None
    return {**agent_card(a), "version": v.version if v else None, "blueprint": v.blueprint if v else {},
            "example_runs": v.example_runs if v else [], "eval_report": v.eval_report if v else None,
            "files": list(files), "runnable": spec is not None,
            "examples": spec.examples if spec else [],
            "locked": not can_access_tier(plan_for(db, user), a.tier)}


@router.get("/{slug}/files/{path:path}")
def get_agent_file(slug: str, path: str, db: Session = DB) -> dict:
    a = _agent(db, slug)
    f = db.scalar(select(AgentFile).where(AgentFile.agent_version_id == a.current_version_id, AgentFile.path == path))
    if f is None:
        raise NotFound("File not found")
    return {"path": f.path, "language": f.language, "content": f.content}


# ------------------------------------------------------------------ runs

class RunIn(BaseModel):
    input: dict[str, Any] | None = None
    example_index: int | None = Field(None, ge=0, le=20)


@router.post("/{slug}/runs", status_code=201, dependencies=[Depends(rate_limit("agent_runs", "rate_limit_agent_runs_per_minute"))])
def create_run(slug: str, body: RunIn, request: Request, user: User = CurrentUser, db: Session = DB) -> dict:
    a = _agent(db, slug)
    spec = get_spec(a.slug)
    if spec is None or not a.has_reference_impl:
        raise AppError("This agent is a blueprint without a runnable reference implementation yet.", code="not_runnable")
    plan = plan_for(db, user)
    if not can_access_tier(plan, a.tier):
        raise AppError("Upgrade required for this agent.", code="upgrade_required", status_code=402)
    limit = entitlement_limit(db, plan, "agent_runs_per_day")
    if limit is not None:
        used = db.scalar(select(func.count()).select_from(UsageEvent).where(
            UsageEvent.user_id == user.id, UsageEvent.event_type == "agent_run",
            UsageEvent.created_at >= datetime.now(UTC) - timedelta(days=1))) or 0
        if used >= limit:
            raise AppError(f"Daily agent-run limit reached for the {plan} plan ({limit}/day).", code="quota_exceeded", status_code=429)
    if body.input is None:
        idx = body.example_index or 0
        if idx >= len(spec.examples):
            raise AppError("Unknown example.", code="bad_example", status_code=422)
        raw = spec.examples[idx]
    else:
        raw = body.input

    provider = _provider_for(plan)
    sandbox = get_sandbox()
    future = _pool.submit(run_agent, spec, raw, provider, sandbox.run if sandbox else None, None, _groups_for(user),
                          getattr(request.state, "trace_id", None))
    try:
        result = future.result(timeout=get_settings().agent_run_timeout_s)
    except concurrent.futures.TimeoutError:
        raise AppError("The agent run exceeded the time limit.", code="run_timeout", status_code=504) from None

    r = AgentRun(agent_id=a.id, user_id=user.id, status=result.status, input=raw, output=result.output,
                 pending_actions=(result.output or {}).get("pending_actions", []), trace_id=result.trace_id,
                 trace=result.trace, provider=result.provider, model=result.model, llm_calls=result.llm_calls,
                 tool_calls=result.tool_calls, input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                 cost_usd=_cost(result.model, result.input_tokens, result.output_tokens), latency_ms=result.latency_ms,
                 error=result.error, finished_at=datetime.now(UTC))
    db.add(r)
    track(db, user.id, "agent_run", agent=a.slug, provider=result.provider, status=result.status,
          tokens=result.input_tokens + result.output_tokens, cost_usd=float(r.cost_usd or 0))
    db.flush()
    ach.evaluate(db, user)
    db.commit()
    return run_out(r, a.slug)


class DecisionIn(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject)$")
    note: str = Field("", max_length=1000)


@router.post("/runs/{run_id}/decision")
def decide(run_id: uuid.UUID, body: DecisionIn, request: Request, user: User = CurrentUser, db: Session = DB) -> dict:
    r = db.get(AgentRun, run_id)
    if r is None or (r.user_id != user.id and "admin" not in user.role_names):
        raise NotFound("Run not found")  # 404, not 403: don't reveal that someone else's run exists
    if r.status != "awaiting_approval":
        raise AppError(f"Run is {r.status}; nothing to approve.", code="not_awaiting_approval", status_code=409)
    agent = db.get(Agent, r.agent_id)
    spec = get_spec(agent.slug)
    before = {"status": r.status}
    if body.decision == "reject":
        r.status = "rejected"
        r.approval_result = {"decision": "reject", "note": body.note}
    else:
        if spec is None or spec.apply_actions is None:
            raise AppError("This agent has no approvable actions.", code="not_supported")
        r.approval_result = {"decision": "approve", "note": body.note, **spec.apply_actions(r.output or {}, r.pending_actions)}
        r.status = "approved"
    r.decided_by = user.id
    audit(db, user, f"agent_run.{body.decision}", "agent_run", r.id, before=before,
          after={"status": r.status, "actions": [p["tool"] for p in r.pending_actions]}, request=request)
    db.commit()
    return run_out(r, agent.slug)

