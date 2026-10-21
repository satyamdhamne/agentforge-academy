"""Agent Builder Studio: workflow CRUD, validation, server-side runs, approvals, cancellation and run history."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..api.deps import DB, CurrentUser, rate_limit
from ..core.errors import AppError, Conflict, NotFound
from ..models import User, Workflow, WorkflowEdge, WorkflowNode, WorkflowRun
from ..services.builder import tools as builder_tools
from ..services.builder.executor import Executor, RunState
from ..services.builder.graph import node_types, validate
from ..services.common import audit, track
from ..services.llm import enforce_quota, groups_for, provider_for

router = APIRouter(prefix="/builder", tags=["agent builder"])
CONTENT = Path(__file__).resolve().parent.parent / "seed" / "content"
MAX_WORKFLOWS = 25


@lru_cache(maxsize=1)
def _templates() -> list[dict[str, Any]]:
    return yaml.safe_load((CONTENT / "builder_templates.yaml").read_text(encoding="utf-8"))["templates"]


class NodeIn(BaseModel):
    key: str = Field(..., max_length=40)
    type: str = Field(..., max_length=30)
    config: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, float] = Field(default_factory=lambda: {"x": 0, "y": 0})


class EdgeIn(BaseModel):
    source: str = Field(..., max_length=40)
    target: str = Field(..., max_length=40)
    handle: str | None = Field(None, max_length=10)


class GraphIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    nodes: list[NodeIn] = Field(default_factory=list, max_length=60)
    edges: list[EdgeIn] = Field(default_factory=list, max_length=120)


def _graph(db: Session, wf: Workflow) -> dict[str, Any]:
    nodes = db.scalars(select(WorkflowNode).where(WorkflowNode.workflow_id == wf.id).order_by(WorkflowNode.node_key)).all()
    edges = db.scalars(select(WorkflowEdge).where(WorkflowEdge.workflow_id == wf.id)).all()
    return {"nodes": [{"key": n.node_key, "type": n.node_type, "config": n.config, "position": n.position} for n in nodes],
            "edges": [{"source": e.source_key, "target": e.target_key, "handle": (e.condition or {}).get("handle")} for e in edges]}


def _wf_out(db: Session, wf: Workflow, with_graph: bool = True) -> dict[str, Any]:
    out = {"id": str(wf.id), "name": wf.name, "description": wf.description, "version": wf.definition_version, "status": wf.status,
           "updated_at": wf.updated_at}
    if with_graph:
        g = _graph(db, wf)
        out.update(g)
        out["issues"] = [i.model_dump() for i in validate(g["nodes"], g["edges"])]
    return out


def _own(db: Session, wid: uuid.UUID, user: User) -> Workflow:
    wf = db.get(Workflow, wid)
    if wf is None or (wf.owner_id != user.id and "admin" not in user.role_names):
        raise NotFound("Workflow not found")
    return wf


def _save_graph(db: Session, wf: Workflow, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    db.execute(delete(WorkflowEdge).where(WorkflowEdge.workflow_id == wf.id))
    db.execute(delete(WorkflowNode).where(WorkflowNode.workflow_id == wf.id))
    db.flush()
    seen = set()
    for n in nodes:
        if n["key"] in seen:
            raise AppError(f"Duplicate node id '{n['key']}'.", code="duplicate_node", status_code=422)
        seen.add(n["key"])
        if n["type"] not in {t["type"] for t in node_types()}:
            raise AppError(f"Unknown node type '{n['type']}'.", code="bad_node_type", status_code=422)
        db.add(WorkflowNode(workflow_id=wf.id, node_key=n["key"], node_type=n["type"], config=n.get("config") or {},
                            position=n.get("position") or {"x": 0, "y": 0}))
    for e in edges:
        db.add(WorkflowEdge(workflow_id=wf.id, source_key=e["source"], target_key=e["target"],
                            condition={"handle": e["handle"]} if e.get("handle") else None))


# ------------------------------------------------------------------ catalog

@router.get("/node-types")
def get_node_types() -> dict:
    return {"items": node_types(), "tools": builder_tools.describe(),
            "budget": {"max_steps": 60, "max_llm_calls": 15, "max_tokens": 40000, "max_seconds": 30}}


@router.get("/templates")
def get_templates() -> dict:
    return {"items": [{"slug": t["slug"], "name": t["name"], "description": t["description"], "nodes": len(t["nodes"]),
                       "sample_input": t.get("sample_input", {})} for t in _templates()]}


# ------------------------------------------------------------------ workflows

@router.get("/workflows")
def list_workflows(user: User = CurrentUser, db: Session = DB) -> dict:
    rows = db.scalars(select(Workflow).where(Workflow.owner_id == user.id).order_by(Workflow.updated_at.desc())).all()
    counts = dict(db.execute(select(WorkflowNode.workflow_id, func.count()).where(
        WorkflowNode.workflow_id.in_([w.id for w in rows] or [uuid.uuid4()])).group_by(WorkflowNode.workflow_id)).all())
    return {"items": [{**_wf_out(db, w, with_graph=False), "nodes": counts.get(w.id, 0)} for w in rows]}


class CreateIn(BaseModel):
    name: str | None = Field(None, max_length=200)
    template: str | None = Field(None, max_length=100)


@router.post("/workflows", status_code=201)
def create_workflow(body: CreateIn, user: User = CurrentUser, db: Session = DB) -> dict:
    if (db.scalar(select(func.count()).select_from(Workflow).where(Workflow.owner_id == user.id)) or 0) >= MAX_WORKFLOWS:
        raise AppError(f"You can keep up to {MAX_WORKFLOWS} workflows.", code="limit")
    if body.template:
        tpl = next((t for t in _templates() if t["slug"] == body.template), None)
        if tpl is None:
            raise NotFound("Template not found")
        nodes, edges, name, desc = tpl["nodes"], tpl["edges"], body.name or tpl["name"], tpl["description"]
        sample = tpl.get("sample_input", {})
    else:
        nodes = [{"key": "input", "type": "input", "position": {"x": 0, "y": 100},
                  "config": {"fields": [{"name": "question", "label": "Question", "type": "text", "required": True}]}},
                 {"key": "result", "type": "output", "position": {"x": 320, "y": 100}, "config": {"value": "{{input.question}}"}}]
        edges, name, desc, sample = [{"source": "input", "target": "result"}], body.name or "Untitled workflow", "", {}
    wf = Workflow(owner_id=user.id, organization_id=user.organization_id, name=name, description=desc, status="draft")
    db.add(wf)
    db.flush()
    _save_graph(db, wf, nodes, edges)
    audit(db, user, "workflow.create", "workflow", wf.id, after={"template": body.template})
    track(db, user.id, "workflow_created", mode=body.template or "blank")
    db.commit()
    return {**_wf_out(db, wf), "sample_input": sample}


@router.get("/workflows/{wid}")
def get_workflow(wid: uuid.UUID, user: User = CurrentUser, db: Session = DB) -> dict:
    wf = _own(db, wid, user)
    tpl_sample = next((t.get("sample_input", {}) for t in _templates() if t["name"] == wf.name), {})
    return {**_wf_out(db, wf), "sample_input": tpl_sample}


@router.put("/workflows/{wid}")
def save_workflow(wid: uuid.UUID, body: GraphIn, user: User = CurrentUser, db: Session = DB) -> dict:
    wf = _own(db, wid, user)
    wf.name, wf.description = body.name.strip(), body.description
    wf.definition_version += 1
    _save_graph(db, wf, [n.model_dump() for n in body.nodes], [e.model_dump() for e in body.edges])
    audit(db, user, "workflow.save", "workflow", wf.id, after={"version": wf.definition_version, "nodes": len(body.nodes)})
    db.commit()
    return _wf_out(db, wf)


@router.delete("/workflows/{wid}", status_code=204)
def delete_workflow(wid: uuid.UUID, user: User = CurrentUser, db: Session = DB) -> None:
    wf = _own(db, wid, user)
    db.delete(wf)
    audit(db, user, "workflow.delete", "workflow", wid)
    db.commit()


@router.post("/validate")
def validate_graph(body: GraphIn) -> dict:
    issues = validate([n.model_dump() for n in body.nodes], [e.model_dump() for e in body.edges])
    return {"valid": not any(i.level == "error" for i in issues), "issues": [i.model_dump() for i in issues]}


# ------------------------------------------------------------------ runs

def _run_out(r: WorkflowRun) -> dict[str, Any]:
    return {"id": str(r.id), "workflow_id": str(r.workflow_id), "status": r.status, "mode": r.mode, "input": r.input,
            "output": r.output, "state": r.state, "trace": r.trace, "node_status": r.node_status, "pending": r.pending,
            "steps": r.steps, "llm_calls": r.llm_calls, "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
            "cost_usd": float(r.cost_usd) if r.cost_usd is not None else None, "latency_ms": r.latency_ms, "error": r.error,
            "created_at": r.created_at, "finished_at": r.finished_at}


def _apply(r: WorkflowRun, rs: RunState, elapsed_ms: int) -> None:
    import json

    r.status, r.error, r.pending = rs.status, rs.error, rs.pending
    r.state = json.loads(json.dumps(rs.state, default=str))
    r.output = json.loads(json.dumps(rs.output, default=str)) if rs.output is not None else None
    r.trace, r.node_status = rs.trace, rs.node_status
    r.input = json.loads(json.dumps(rs.input, default=str))
    r.steps, r.llm_calls, r.input_tokens, r.output_tokens = rs.steps, rs.llm_calls, rs.input_tokens, rs.output_tokens
    r.cost_usd = Decimal(str(round(rs.cost, 6))) if rs.cost_known else None
    r.latency_ms += elapsed_ms
    if rs.status in ("succeeded", "failed", "rejected", "cancelled"):
        r.finished_at = datetime.now(UTC)


class RunIn(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    live: bool = False


@router.post("/workflows/{wid}/runs", status_code=201, dependencies=[Depends(rate_limit("workflow", "rate_limit_agent_runs_per_minute"))])
def run_workflow(wid: uuid.UUID, body: RunIn, user: User = CurrentUser, db: Session = DB) -> dict:
    wf = _own(db, wid, user)
    g = _graph(db, wf)
    issues = validate(g["nodes"], g["edges"])
    errors = [i for i in issues if i.level == "error"]
    if errors:
        raise AppError("Fix the workflow before running it.", code="invalid_workflow", status_code=422,
                       details=[i.model_dump() for i in errors])
    enforce_quota(db, user, "workflow_runs_per_day", "workflow_run")
    choice = provider_for(db, user, body.live)
    r = WorkflowRun(workflow_id=wf.id, user_id=user.id, status="running", mode=choice.mode, definition=g, input=body.input)
    db.add(r)
    db.flush()
    t = time.perf_counter()
    rs = Executor(db, choice.provider, groups_for(user), owner_id=user.id).start(g, body.input)
    _apply(r, rs, int((time.perf_counter() - t) * 1000))
    track(db, user.id, "workflow_run", status=r.status, mode=choice.mode, tokens=r.input_tokens + r.output_tokens)
    audit(db, user, "workflow_run.start", "workflow_run", r.id, after={"status": r.status, "workflow": str(wf.id)})
    db.commit()
    return _run_out(r)


@router.get("/workflows/{wid}/runs")
def list_runs(wid: uuid.UUID, user: User = CurrentUser, db: Session = DB) -> dict:
    wf = _own(db, wid, user)
    rows = db.scalars(select(WorkflowRun).where(WorkflowRun.workflow_id == wf.id).order_by(WorkflowRun.created_at.desc()).limit(20)).all()
    return {"items": [{k: v for k, v in _run_out(r).items() if k not in ("state", "trace")} for r in rows]}


def _own_run(db: Session, rid: uuid.UUID, user: User) -> WorkflowRun:
    r = db.get(WorkflowRun, rid)
    if r is None or (r.user_id != user.id and "admin" not in user.role_names):
        raise NotFound("Run not found")
    return r


@router.get("/runs/{rid}")
def get_run(rid: uuid.UUID, user: User = CurrentUser, db: Session = DB) -> dict:
    return _run_out(_own_run(db, rid, user))


class DecisionIn(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject)$")
    note: str = Field("", max_length=1000)


@router.post("/runs/{rid}/decision")
def decide(rid: uuid.UUID, body: DecisionIn, user: User = CurrentUser, db: Session = DB) -> dict:
    r = _own_run(db, rid, user)
    if r.status != "awaiting_approval":
        raise Conflict(f"Run is {r.status}; nothing to approve.")
    choice = provider_for(db, user, r.mode == "live")
    rs = RunState(definition=r.definition, input=r.input, state=dict(r.state), node_status=dict(r.node_status), trace=list(r.trace),
                  steps=r.steps, llm_calls=r.llm_calls, input_tokens=r.input_tokens, output_tokens=r.output_tokens,
                  cost=float(r.cost_usd or 0), cost_known=r.cost_usd is not None, status=r.status, pending=r.pending)
    pending = r.pending or {}
    t = time.perf_counter()
    rs = Executor(db, choice.provider, groups_for(user), owner_id=r.user_id).resume(rs, body.decision == "approve", body.note)
    _apply(r, rs, int((time.perf_counter() - t) * 1000))
    r.decided_by = user.id
    audit(db, user, f"workflow_run.{body.decision}", "workflow_run", r.id,
          before={"status": "awaiting_approval", "node": pending.get("node")},
          after={"status": r.status, "actions": [a["tool"] for a in pending.get("next_actions", [])], "note": body.note})
    db.commit()
    return _run_out(r)


@router.post("/runs/{rid}/cancel")
def cancel(rid: uuid.UUID, user: User = CurrentUser, db: Session = DB) -> dict:
    r = _own_run(db, rid, user)
    if r.status not in ("awaiting_approval", "running"):
        raise Conflict(f"Run is already {r.status}.")
    r.status, r.pending, r.finished_at = "cancelled", None, datetime.now(UTC)
    audit(db, user, "workflow_run.cancel", "workflow_run", r.id)
    db.commit()
    return _run_out(r)
