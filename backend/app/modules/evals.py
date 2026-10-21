"""Evaluation history across the prompt lab, RAG lab and reference agents, plus the LLM & SLM lab catalog."""

from __future__ import annotations

import uuid
from functools import lru_cache
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentforge_agents.evals import run_eval
from agentforge_agents.registry import get_spec

from ..api.deps import DB, CurrentUser, OptionalUser, rate_limit
from ..core.config import get_settings
from ..core.errors import AppError, NotFound
from ..models import Agent, Evaluation, EvaluationCase, User
from ..services.common import plan_for, track
from ..services.llm import enforce_quota, provider_for
from ..services.sandbox import get_sandbox

router = APIRouter(tags=["evaluations"])
CONTENT = Path(__file__).resolve().parent.parent / "seed" / "content"


def _eval_out(e: Evaluation, with_cases: list[EvaluationCase] | None = None) -> dict:
    out = {"id": str(e.id), "name": e.name, "target_type": e.target_type, "target_id": str(e.target_id) if e.target_id else None,
           "summary": e.summary, "created_at": e.created_at}
    if with_cases is not None:
        out["cases"] = [{"key": c.case_key, "input": c.input, "expected": c.expected, "result": c.result, "passed": c.passed}
                        for c in with_cases]
    return out


@router.get("/evaluations")
def list_evaluations(target_type: str | None = Query(None, pattern="^(prompt|rag|agent)$"), limit: int = Query(50, ge=1, le=200),
                     user: User = CurrentUser, db: Session = DB) -> dict:
    stmt = select(Evaluation).where(Evaluation.created_by == user.id).order_by(Evaluation.created_at.desc()).limit(limit)
    if target_type:
        stmt = stmt.where(Evaluation.target_type == target_type)
    return {"items": [_eval_out(e) for e in db.scalars(stmt).all()]}


def _own_eval(db: Session, eid: uuid.UUID, user: User) -> Evaluation:
    e = db.get(Evaluation, eid)
    if e is None or (e.created_by != user.id and "admin" not in user.role_names):
        raise NotFound("Evaluation not found")
    return e


@router.get("/evaluations/{eid}")
def get_evaluation(eid: uuid.UUID, user: User = CurrentUser, db: Session = DB) -> dict:
    e = _own_eval(db, eid, user)
    cases = db.scalars(select(EvaluationCase).where(EvaluationCase.evaluation_id == e.id).order_by(EvaluationCase.case_key)).all()
    return _eval_out(e, list(cases))


@router.get("/evaluations/{a}/compare/{b}")
def compare_evaluations(a: uuid.UUID, b: uuid.UUID, user: User = CurrentUser, db: Session = DB) -> dict:
    ea, eb = _own_eval(db, a, user), _own_eval(db, b, user)
    if ea.target_type != eb.target_type:
        raise AppError("Compare evaluations of the same kind.", code="mismatch")

    def metrics(e: Evaluation) -> dict:
        s = e.summary or {}
        if s.get("kind") == "rag_eval":
            return s.get("metrics", {})
        if s.get("kind") == "prompt_compare":
            best = next((v for v in s.get("variants", []) if v["label"] == s.get("best")), {})
            return {"pass_rate": best.get("pass_rate"), "avg_input_tokens": best.get("avg_input_tokens")}
        return {"pass_rate": s.get("pass_rate"), "passed": s.get("passed"), "cases": s.get("cases")}

    ma, mb = metrics(ea), metrics(eb)
    keys = sorted(set(ma) | set(mb))
    return {"a": _eval_out(ea), "b": _eval_out(eb),
            "metrics": [{"metric": k, "a": ma.get(k), "b": mb.get(k),
                         "delta": round(mb[k] - ma[k], 4) if isinstance(ma.get(k), (int, float)) and isinstance(mb.get(k), (int, float)) else None}
                        for k in keys]}


@router.post("/agents/{slug}/evaluate", dependencies=[Depends(rate_limit("agent_runs", "rate_limit_agent_runs_per_minute"))])
def evaluate_agent(slug: str, live: bool = False, user: User = CurrentUser, db: Session = DB) -> dict:
    a = db.scalar(select(Agent).where(Agent.slug == slug, Agent.status == "published"))
    spec = get_spec(slug) if a else None
    if a is None or spec is None:
        raise NotFound("Runnable agent not found")
    enforce_quota(db, user, "agent_runs_per_day", "agent_run", cost=5)
    choice = provider_for(db, user, live)
    # The simulator can't play an agent's scripted mock responses; agent evals use the agent's own mock unless live.
    provider = None if choice.mode == "mock" else choice.provider
    sandbox = get_sandbox()
    report = run_eval(spec, provider=provider, sandbox=sandbox.run if sandbox else None)
    ev = Evaluation(name=f"{a.name} evaluation ({'live' if provider else 'mock'})", target_type="agent", target_id=a.id,
                    created_by=user.id, summary={"kind": "agent_eval", "agent": slug, "cases": report["cases"], "passed": report["passed"],
                                                  "pass_rate": report["pass_rate"], "mode": "live" if provider else "mock"})
    db.add(ev)
    db.flush()
    for r in report["results"]:
        db.add(EvaluationCase(evaluation_id=ev.id, case_key=r["id"][:100], input={}, expected={}, result=r, passed=r["passed"]))
    for _ in range(5):
        track(db, user.id, "agent_run", agent=slug, mode="eval")
    db.commit()
    return {"evaluation_id": str(ev.id), **report}


# ------------------------------------------------------------------ LLM & SLM lab

@lru_cache(maxsize=1)
def _models() -> dict:
    return yaml.safe_load((CONTENT / "models.yaml").read_text(encoding="utf-8"))


@router.get("/llm-lab/catalog")
def llm_catalog() -> dict:
    return _models()


@router.get("/llm-lab/providers")
def llm_providers(user: User | None = OptionalUser, db: Session = DB) -> dict:
    s = get_settings()
    plan = plan_for(db, user)
    base = s.openai_base_url.lower()
    local = s.llm_provider == "openai" and any(h in base for h in ("localhost", "127.0.0.1", "ollama", "host.docker.internal", ":11434"))
    return {"server_provider": s.llm_provider,
            "server_model": s.openai_model if s.llm_provider == "openai" else (s.anthropic_model if s.llm_provider == "anthropic" else "simulator-1"),
            "local_model": local, "your_plan": plan,
            "you_get": "simulator" if plan == "free" or s.llm_provider == "mock" else "live",
            "how_to_run_locally": "Install Ollama, run `ollama pull llama3.1:8b`, then set LLM_PROVIDER=openai, "
                                  "OPENAI_BASE_URL=http://host.docker.internal:11434/v1, OPENAI_MODEL=llama3.1:8b and OPENAI_API_KEY=ollama."}
