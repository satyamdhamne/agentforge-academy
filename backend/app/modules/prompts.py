"""Prompt Engineering Lab: templates with versions and test cases, a playground, and A/B comparison with scoring."""

from __future__ import annotations

import secrets
import time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from agentforge_agents.core import CompletionRequest, LLMError, Message

from ..api.deps import DB, CurrentUser, OptionalUser, rate_limit
from ..core.errors import AppError, Forbidden, NotFound
from ..models import Evaluation, EvaluationCase, PromptTemplate, PromptTestCase, PromptVersion, User
from ..services.assertions import TYPES, run_checks
from ..services.common import audit, track
from ..services.llm import cost_usd, enforce_quota, provider_for
from ..services.templating import render, variables

router = APIRouter(prefix="/prompts", tags=["prompt lab"])


# ------------------------------------------------------------------ helpers

def _visible(user: User | None):
    cond = PromptTemplate.owner_id.is_(None)
    return or_(cond, PromptTemplate.owner_id == user.id) if user else cond


def _template(db: Session, slug: str, user: User | None) -> PromptTemplate:
    t = db.scalar(select(PromptTemplate).where(PromptTemplate.slug == slug, _visible(user)))
    if t is None:
        raise NotFound("Prompt template not found")
    return t


def _version_out(v: PromptVersion) -> dict:
    return {"id": str(v.id), "version": v.version, "system": v.system, "user_template": v.user_template, "variables": v.variables,
            "params": v.params, "change_note": v.change_note, "created_at": v.created_at}


def _case_out(c: PromptTestCase) -> dict:
    return {"id": str(c.id), "name": c.name, "variables": c.variables, "assertions": c.assertions}


class Params(BaseModel):
    temperature: float = Field(0.0, ge=0, le=2)
    max_tokens: int = Field(512, ge=16, le=4000)
    json_schema: dict[str, Any] | None = None


class Variant(BaseModel):
    label: str = Field("A", max_length=40)
    system: str = Field("", max_length=8000)
    user_template: str = Field(..., min_length=1, max_length=12000)
    params: Params = Params()


class Assertion(BaseModel):
    type: str = Field(..., pattern="^(" + "|".join(TYPES) + ")$")
    value: Any = None
    label: str | None = Field(None, max_length=120)


class CaseIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    variables: dict[str, Any] = Field(default_factory=dict)
    assertions: list[Assertion] = Field(default_factory=list, max_length=12)


def _call(choice, variant: Variant, vars_: dict[str, Any]) -> dict[str, Any]:
    rendered = render(variant.user_template, vars_)
    req = CompletionRequest(task="lab.prompt", messages=[Message("system", variant.system), Message("user", rendered)],
                            temperature=variant.params.temperature, max_tokens=variant.params.max_tokens,
                            response_schema=variant.params.json_schema)
    t = time.perf_counter()
    try:
        c = choice.provider.complete(req)
    except LLMError as exc:
        return {"output": "", "error": str(exc), "rendered_user": rendered, "input_tokens": 0, "output_tokens": 0,
                "latency_ms": int((time.perf_counter() - t) * 1000), "model": "", "provider": choice.mode, "cost_usd": None}
    cost = cost_usd(c.model, c.usage.input_tokens, c.usage.output_tokens)
    return {"output": c.content, "error": None, "rendered_user": rendered, "input_tokens": c.usage.input_tokens,
            "output_tokens": c.usage.output_tokens, "latency_ms": c.latency_ms or int((time.perf_counter() - t) * 1000),
            "model": c.model, "provider": c.provider, "cost_usd": float(cost) if cost is not None else None}


# ------------------------------------------------------------------ catalog

@router.get("/templates")
def list_templates(category: str | None = None, user: User | None = OptionalUser, db: Session = DB) -> dict:
    stmt = select(PromptTemplate).where(_visible(user), PromptTemplate.status == "published").order_by(
        PromptTemplate.owner_id.is_(None).desc(), PromptTemplate.category, PromptTemplate.name)
    if category:
        stmt = stmt.where(PromptTemplate.category == category)
    rows = db.scalars(stmt).all()
    versions = dict(db.execute(select(PromptVersion.template_id, func.max(PromptVersion.version)).group_by(PromptVersion.template_id)).all())
    cases = dict(db.execute(select(PromptTestCase.template_id, func.count()).group_by(PromptTestCase.template_id)).all())
    return {"items": [{"slug": t.slug, "name": t.name, "category": t.category, "description": t.description,
                       "mine": user is not None and t.owner_id == user.id, "versions": versions.get(t.id, 0),
                       "test_cases": cases.get(t.id, 0)} for t in rows],
            "categories": sorted({t.category for t in rows}), "assertion_types": list(TYPES)}


@router.get("/templates/{slug}")
def get_template(slug: str, user: User | None = OptionalUser, db: Session = DB) -> dict:
    t = _template(db, slug, user)
    versions = db.scalars(select(PromptVersion).where(PromptVersion.template_id == t.id).order_by(PromptVersion.version.desc())).all()
    cases = db.scalars(select(PromptTestCase).where(PromptTestCase.template_id == t.id).order_by(PromptTestCase.order_index)).all()
    return {"slug": t.slug, "name": t.name, "category": t.category, "description": t.description,
            "mine": user is not None and t.owner_id == user.id, "editable": user is not None and t.owner_id == user.id,
            "current_version_id": str(t.current_version_id) if t.current_version_id else None,
            "versions": [_version_out(v) for v in versions], "test_cases": [_case_out(c) for c in cases]}


@router.post("/templates/{slug}/fork", status_code=201)
def fork(slug: str, user: User = CurrentUser, db: Session = DB) -> dict:
    src = _template(db, slug, user)
    base = src.slug.split("--")[0]
    t = PromptTemplate(slug=f"{base}--{secrets.token_hex(3)}", name=f"{src.name} (my copy)", category=src.category,
                       description=src.description, owner_id=user.id, status="published")
    db.add(t)
    db.flush()
    cur = db.get(PromptVersion, src.current_version_id) if src.current_version_id else None
    if cur:
        v = PromptVersion(template_id=t.id, version=1, system=cur.system, user_template=cur.user_template, variables=cur.variables,
                          params=cur.params, change_note=f"Forked from {src.slug} v{cur.version}")
        db.add(v)
        db.flush()
        t.current_version_id = v.id
    for c in db.scalars(select(PromptTestCase).where(PromptTestCase.template_id == src.id)).all():
        db.add(PromptTestCase(template_id=t.id, name=c.name, variables=c.variables, assertions=c.assertions, order_index=c.order_index))
    track(db, user.id, "prompt_forked")
    db.commit()
    return {"slug": t.slug}


def _own(db: Session, slug: str, user: User) -> PromptTemplate:
    t = _template(db, slug, user)
    if t.owner_id != user.id:
        raise Forbidden("Fork this template to edit it.")
    return t


class VersionIn(Variant):
    change_note: str = Field(..., min_length=3, max_length=500)


@router.post("/templates/{slug}/versions", status_code=201)
def create_version(slug: str, body: VersionIn, user: User = CurrentUser, db: Session = DB) -> dict:
    t = _own(db, slug, user)
    latest = db.scalar(select(func.max(PromptVersion.version)).where(PromptVersion.template_id == t.id)) or 0
    v = PromptVersion(template_id=t.id, version=latest + 1, system=body.system, user_template=body.user_template,
                      variables=variables(body.system + "\n" + body.user_template), params=body.params.model_dump(exclude_none=True),
                      change_note=body.change_note)
    db.add(v)
    db.flush()
    t.current_version_id = v.id
    audit(db, user, "prompt_version.create", "prompt_template", t.id, after={"version": v.version})
    db.commit()
    return _version_out(v)


class CasesIn(BaseModel):
    cases: list[CaseIn] = Field(..., max_length=20)


@router.put("/templates/{slug}/test-cases")
def replace_cases(slug: str, body: CasesIn, user: User = CurrentUser, db: Session = DB) -> dict:
    t = _own(db, slug, user)
    for c in db.scalars(select(PromptTestCase).where(PromptTestCase.template_id == t.id)).all():
        db.delete(c)
    db.flush()
    for i, c in enumerate(body.cases):
        db.add(PromptTestCase(template_id=t.id, name=c.name, variables=c.variables,
                              assertions=[a.model_dump(exclude_none=True) for a in c.assertions], order_index=i))
    db.commit()
    return {"saved": len(body.cases)}


# ------------------------------------------------------------------ playground & comparison

class RunIn(Variant):
    variables: dict[str, Any] = Field(default_factory=dict)
    assertions: list[Assertion] = Field(default_factory=list, max_length=12)
    live: bool = True


@router.post("/run", dependencies=[Depends(rate_limit("prompt", "rate_limit_agent_runs_per_minute"))])
def run(body: RunIn, user: User = CurrentUser, db: Session = DB) -> dict:
    enforce_quota(db, user, "prompt_runs_per_day", "prompt_run")
    choice = provider_for(db, user, body.live)
    out = _call(choice, body, body.variables)
    out["checks"] = run_checks([a.model_dump(exclude_none=True) for a in body.assertions], out["output"]) if body.assertions else None
    out["mode"], out["provider_label"] = choice.mode, choice.label
    track(db, user.id, "prompt_run", provider=out["provider"], mode=choice.mode, tokens=out["input_tokens"] + out["output_tokens"])
    db.commit()
    return out


class CompareIn(BaseModel):
    template_slug: str | None = None
    variants: list[Variant] = Field(..., min_length=1, max_length=3)
    cases: list[CaseIn] | None = Field(None, max_length=10)
    live: bool = True
    name: str | None = Field(None, max_length=200)


@router.post("/compare", dependencies=[Depends(rate_limit("prompt", "rate_limit_agent_runs_per_minute"))])
def compare(body: CompareIn, user: User = CurrentUser, db: Session = DB) -> dict:
    template = _template(db, body.template_slug, user) if body.template_slug else None
    if body.cases is not None:
        cases = [c.model_dump() for c in body.cases]
        for c in cases:
            c["assertions"] = [{k: v for k, v in a.items() if v is not None} for a in c["assertions"]]
    elif template is not None:
        cases = [_case_out(c) for c in db.scalars(select(PromptTestCase).where(PromptTestCase.template_id == template.id)
                                                  .order_by(PromptTestCase.order_index)).all()][:10]
    else:
        raise AppError("Provide test cases or a template with test cases.", code="no_cases", status_code=422)
    if not cases:
        raise AppError("Add at least one test case.", code="no_cases", status_code=422)
    calls = len(cases) * len(body.variants)
    enforce_quota(db, user, "prompt_runs_per_day", "prompt_run", cost=calls)
    choice = provider_for(db, user, body.live)
    matrix = []
    summary = []
    for vi, variant in enumerate(body.variants):
        totals = {"passed_cases": 0, "checks_passed": 0, "checks_total": 0, "input_tokens": 0, "output_tokens": 0, "latency_ms": 0,
                  "cost_usd": 0.0, "errors": 0}
        for ci, case in enumerate(cases):
            try:
                out = _call(choice, variant, case.get("variables") or {})
            except AppError as exc:  # missing variables etc.
                out = {"output": "", "error": exc.message, "input_tokens": 0, "output_tokens": 0, "latency_ms": 0, "cost_usd": 0.0}
            checks = run_checks(case.get("assertions") or [], out["output"]) if not out.get("error") else \
                {"results": [], "passed": 0, "total": len(case.get("assertions") or []), "score": 0.0}
            ok = not out.get("error") and checks["passed"] == checks["total"]
            matrix.append({"variant": vi, "case": ci, "output": out["output"], "error": out.get("error"), "checks": checks, "passed": ok,
                           "input_tokens": out["input_tokens"], "output_tokens": out["output_tokens"], "latency_ms": out["latency_ms"]})
            totals["passed_cases"] += ok
            totals["checks_passed"] += checks["passed"]
            totals["checks_total"] += checks["total"]
            totals["errors"] += bool(out.get("error"))
            for k in ("input_tokens", "output_tokens", "latency_ms"):
                totals[k] += out[k]
            totals["cost_usd"] += out.get("cost_usd") or 0.0
        n = len(cases)
        summary.append({"variant": vi, "label": variant.label, "pass_rate": round(totals["passed_cases"] / n, 3),
                        "check_pass_rate": round(totals["checks_passed"] / totals["checks_total"], 3) if totals["checks_total"] else None,
                        "avg_input_tokens": round(totals["input_tokens"] / n), "avg_output_tokens": round(totals["output_tokens"] / n),
                        "avg_latency_ms": round(totals["latency_ms"] / n), "cost_usd": round(totals["cost_usd"], 6), "errors": totals["errors"]})
    best = max(summary, key=lambda s: (s["pass_rate"], s["check_pass_rate"] or 0, -s["avg_input_tokens"]))
    ev = Evaluation(name=body.name or (f"{template.name}: " if template else "") + " vs ".join(v.label for v in body.variants),
                    target_type="prompt", target_id=template.id if template else None, created_by=user.id,
                    summary={"kind": "prompt_compare", "variants": summary, "best": best["label"], "mode": choice.mode,
                             "provider": choice.label, "cases": len(cases),
                             "variant_defs": [v.model_dump() for v in body.variants],
                             "template": template.slug if template else None})
    db.add(ev)
    db.flush()
    for row in matrix:
        case = cases[row["case"]]
        db.add(EvaluationCase(evaluation_id=ev.id, case_key=f"{body.variants[row['variant']].label}:{case['name']}"[:100],
                              input={"variables": case.get("variables"), "variant": row["variant"]},
                              expected={"assertions": case.get("assertions")}, result=row, passed=row["passed"]))
    track(db, user.id, "prompt_compare", mode=choice.mode, tokens=sum(s["avg_input_tokens"] for s in summary))
    db.commit()
    return {"evaluation_id": str(ev.id), "mode": choice.mode, "provider_label": choice.label, "cases": cases,
            "variants": [v.model_dump() for v in body.variants], "summary": summary, "matrix": matrix, "best": best["label"]}
