"""Server-side workflow executor.

Runs a *validated* graph in dependency order. A node runs once every predecessor has resolved and at least one
incoming edge was taken (condition nodes take only their true/false edge; other nodes take all edges). Nodes
whose incoming edges were all skipped are skipped. Human approval nodes pause the run; `resume()` continues it.

Budgets bound every run (steps, model calls, tokens, wall-clock time). Nothing here executes user-supplied code:
templates only interpolate values, conditions use fixed operators, and tools come from an allowlist.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from agentforge_agents.core import CompletionRequest, LLMError, LLMProvider, Message

from ..assertions import lenient_json, run_checks
from ..llm import cost_usd
from ..templating import VAR, lookup
from .graph import parse_config, topo_order
from .tools import TOOLS, ToolFailure, to_text


@dataclass
class Budget:
    max_steps: int = 60
    max_llm_calls: int = 15
    max_tokens: int = 40_000
    max_seconds: float = 30.0


class RunFailed(Exception):
    pass


@dataclass
class RunState:
    definition: dict[str, Any]
    input: dict[str, Any]
    state: dict[str, Any] = field(default_factory=dict)
    node_status: dict[str, str] = field(default_factory=dict)  # pending|running|done|skipped|paused|failed
    trace: list[dict[str, Any]] = field(default_factory=list)
    steps: int = 0
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    cost_known: bool = True
    status: str = "running"
    pending: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: str | None = None


def _resolve(template: str, data: dict[str, Any]) -> Any:
    """Single reference -> the raw value (dict/list/number); otherwise string interpolation."""
    m = VAR.fullmatch(template.strip())
    if m:
        return _get(data, m.group(1))
    return VAR.sub(lambda mm: to_text(_text(_get(data, mm.group(1)))), template)


def _get(data: dict[str, Any], path: str) -> Any:
    try:
        return lookup(data, path)
    except KeyError:
        raise RunFailed(f"Value '{path}' isn't available yet. Check the template or the connections.") from None


def _text(v: Any) -> Any:
    """Node outputs that carry a `text` field render as that text when used whole."""
    if isinstance(v, dict) and "text" in v and set(v) <= {"text", "json", "model", "tokens"}:
        return v["text"]
    if isinstance(v, dict) and "context" in v and "passages" in v:
        return v["context"]
    return v


def _str(template: str, data: dict[str, Any]) -> str:
    v = _resolve(template, data)
    return to_text(_text(v))


def _preview(v: Any, n: int = 400) -> Any:
    s = to_text(v)
    return s if len(s) <= n else s[:n] + "…"


class Executor:
    def __init__(self, db: Session, provider: LLMProvider, groups: list[str], owner_id: Any = None, budget: Budget | None = None):
        self.db, self.provider, self.groups, self.budget = db, provider, groups, budget or Budget()
        self.owner_id = owner_id  # whose private RAG datasets retrieval may read

    # ---------------------------------------------------------------- public API
    def start(self, definition: dict[str, Any], input_values: dict[str, Any]) -> RunState:
        rs = RunState(definition=definition, input=input_values)
        rs.node_status = {n["key"]: "pending" for n in definition["nodes"]}
        rs.state = {"memory": {}}
        return self._loop(rs)

    def resume(self, rs: RunState, approved: bool, note: str = "") -> RunState:
        key = (rs.pending or {}).get("node")
        if not key:
            raise RunFailed("Nothing is waiting for approval.")
        rs.pending = None
        if not approved:
            rs.node_status[key] = "failed"
            rs.status = "rejected"
            rs.trace.append({"node": key, "type": "human_approval", "status": "rejected", "start_ms": 0, "duration_ms": 0,
                             "output": {"approved": False, "note": note}})
            return rs
        rs.state[key] = {"approved": True, "note": note}
        rs.node_status[key] = "done"
        rs.trace.append({"node": key, "type": "human_approval", "status": "approved", "start_ms": 0, "duration_ms": 0,
                         "output": {"approved": True, "note": note}})
        rs.status = "running"
        return self._loop(rs)

    # ---------------------------------------------------------------- scheduling
    def _loop(self, rs: RunState) -> RunState:
        d = rs.definition
        nodes = {n["key"]: n for n in d["nodes"]}
        incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for e in d["edges"]:
            incoming[e["target"]].append(e)
        started = time.perf_counter()
        t0 = time.perf_counter()
        try:
            for key in topo_order(d["nodes"], d["edges"]):
                if rs.node_status.get(key) in ("done", "skipped", "failed"):
                    continue
                edges = incoming[key]
                if edges:
                    if any(rs.node_status.get(e["source"]) not in ("done", "skipped") for e in edges):
                        continue  # a predecessor is paused; wait
                    taken = [e for e in edges if self._taken(rs, nodes, e)]
                    if not taken:
                        rs.node_status[key] = "skipped"
                        rs.trace.append({"node": key, "type": nodes[key]["type"], "status": "skipped", "start_ms": 0, "duration_ms": 0})
                        continue
                if time.perf_counter() - started > self.budget.max_seconds:
                    raise RunFailed(f"Run exceeded the {self.budget.max_seconds:.0f}s time budget.")
                rs.steps += 1
                if rs.steps > self.budget.max_steps:
                    raise RunFailed(f"Run exceeded {self.budget.max_steps} steps.")
                node = nodes[key]
                if node["type"] == "human_approval":
                    self._pause(rs, node, nodes)
                    return rs
                rs.node_status[key] = "running"
                t = time.perf_counter()
                try:
                    out = self._run_node(rs, node)
                except RunFailed as exc:
                    rs.node_status[key] = "failed"
                    rs.trace.append({"node": key, "type": node["type"], "status": "error", "start_ms": round((t - t0) * 1000, 2),
                                     "duration_ms": round((time.perf_counter() - t) * 1000, 2), "error": str(exc)})
                    raise
                rs.state[key] = out
                rs.node_status[key] = "done"
                rs.trace.append({"node": key, "type": node["type"], "status": "ok", "start_ms": round((t - t0) * 1000, 2),
                                 "duration_ms": round((time.perf_counter() - t) * 1000, 2), "output": _preview(out),
                                 **({"tokens": out.get("tokens")} if isinstance(out, dict) and "tokens" in out else {})})
                if node["type"] == "evaluation" and not out["passed"] and out.get("stop"):
                    raise RunFailed(f"Evaluation '{key}' failed: {', '.join(r['label'] for r in out['results'] if not r['passed'])}")
            outs = {k: rs.state[k] for k, n in nodes.items() if n["type"] == "output" and rs.node_status.get(k) == "done"}
            rs.output = outs
            rs.status = "succeeded"
        except RunFailed as exc:
            rs.status, rs.error = "failed", str(exc)
        return rs

    def _taken(self, rs: RunState, nodes: dict[str, Any], e: dict[str, Any]) -> bool:
        src = e["source"]
        if rs.node_status.get(src) != "done":
            return False
        if nodes[src]["type"] == "condition":
            return (e.get("handle") or "") == rs.state[src]["branch"]
        return True

    def _data(self, rs: RunState) -> dict[str, Any]:
        return {**rs.state, "input": rs.input}

    def _pause(self, rs: RunState, node: dict[str, Any], nodes: dict[str, Any]) -> None:
        cfg = parse_config("human_approval", node.get("config") or {})
        data = self._data(rs)
        downstream = []
        for e in rs.definition["edges"]:
            if e["source"] == node["key"] and nodes[e["target"]]["type"] == "tool":
                tcfg = parse_config("tool", nodes[e["target"]].get("config") or {})
                args = {}
                for k, v in tcfg.args.items():
                    try:
                        args[k] = _str(v, data)
                    except RunFailed:
                        args[k] = v
                downstream.append({"node": e["target"], "tool": tcfg.tool, "side_effect": TOOLS[tcfg.tool].side_effect, "args": args})
        rs.node_status[node["key"]] = "paused"
        rs.status = "awaiting_approval"
        rs.pending = {"node": node["key"], "message": _str(cfg.message, data), "next_actions": downstream}
        rs.trace.append({"node": node["key"], "type": "human_approval", "status": "paused", "start_ms": 0, "duration_ms": 0,
                         "output": rs.pending["message"]})

    # ---------------------------------------------------------------- node implementations
    def _run_node(self, rs: RunState, node: dict[str, Any]) -> Any:
        t = node["type"]
        cfg = parse_config(t, node.get("config") or {})
        data = self._data(rs)
        if t == "input":
            values = {}
            for f in cfg.fields:
                v = rs.input.get(f.name, f.default)
                if f.required and (v is None or v == ""):
                    raise RunFailed(f"Input '{f.name}' is required.")
                if f.type == "number" and v not in (None, ""):
                    try:
                        v = float(v)
                    except (TypeError, ValueError):
                        raise RunFailed(f"Input '{f.name}' must be a number.") from None
                if f.type == "json" and isinstance(v, str):
                    v = lenient_json(v)
                values[f.name] = v
            rs.input = values
            return values
        if t == "prompt":
            return _str(cfg.template, data)
        if t == "llm":
            return self._llm(rs, cfg, data)
        if t == "tool":
            return self._tool(cfg, data)
        if t == "retrieval":
            return self._retrieve(cfg.dataset, _str(cfg.query, data), cfg.top_k, cfg.strategy)
        if t == "condition":
            left = _resolve(cfg.left, data)
            right = _str(cfg.right, data) if cfg.right else ""
            result = _compare(_text(left), cfg.op, right)
            return {"result": result, "branch": "true" if result else "false", "left": _preview(_text(left), 120)}
        if t == "memory":
            mem = rs.state.setdefault("memory", {})
            if cfg.mode == "get":
                return mem.get(cfg.key)
            value = _resolve(cfg.value, data) if cfg.value else None
            if cfg.mode == "append":
                mem.setdefault(cfg.key, [])
                if not isinstance(mem[cfg.key], list):
                    mem[cfg.key] = [mem[cfg.key]]
                mem[cfg.key].append(_text(value))
            else:
                mem[cfg.key] = _text(value)
            return mem[cfg.key]
        if t == "evaluation":
            target = _text(_resolve(cfg.target, data))
            r = run_checks([c.model_dump(exclude_none=True) for c in cfg.checks], target)
            return {"passed": r["passed"] == r["total"], "score": r["score"], "results": r["results"], "stop": cfg.stop_on_fail}
        if t == "output":
            return {"value": _text(_resolve(cfg.value, data))}
        raise RunFailed(f"Unsupported node type {t}")

    def _llm(self, rs: RunState, cfg: Any, data: dict[str, Any]) -> dict[str, Any]:
        if rs.llm_calls >= self.budget.max_llm_calls:
            raise RunFailed(f"Run exceeded {self.budget.max_llm_calls} model calls.")
        if rs.input_tokens + rs.output_tokens >= self.budget.max_tokens:
            raise RunFailed(f"Run exceeded the {self.budget.max_tokens}-token budget.")
        req = CompletionRequest(task="builder.llm", messages=[Message("system", _str(cfg.system, data) if cfg.system else ""),
                                                              Message("user", _str(cfg.prompt, data))],
                                temperature=cfg.temperature, max_tokens=cfg.max_tokens, response_schema=cfg.json_schema)
        try:
            c = self.provider.complete(req)
        except LLMError as exc:
            raise RunFailed(f"Model call failed: {exc}") from exc
        rs.llm_calls += 1
        rs.input_tokens += c.usage.input_tokens
        rs.output_tokens += c.usage.output_tokens
        cost = cost_usd(c.model, c.usage.input_tokens, c.usage.output_tokens)
        if cost is None:
            rs.cost_known = False
        else:
            rs.cost += float(cost)
        parsed = lenient_json(c.content) if (cfg.json_schema or "json" in (cfg.system + cfg.prompt).lower()) else None
        return {"text": c.content, "json": parsed, "model": c.model, "tokens": c.usage.input_tokens + c.usage.output_tokens}

    def _tool(self, cfg: Any, data: dict[str, Any]) -> Any:
        tool = TOOLS.get(cfg.tool)
        if tool is None:
            raise RunFailed(f"Tool '{cfg.tool}' isn't allowed.")
        args = {k: _str(v, data) for k, v in cfg.args.items() if k in tool.args}
        if cfg.tool == "kb_search":
            return self._retrieve(args.get("dataset") or "northwind-handbook", args.get("query", ""), 4, "hybrid")
        try:
            return tool.fn(**args)
        except ToolFailure as exc:
            raise RunFailed(f"{cfg.tool}: {exc}") from exc
        except TypeError as exc:
            raise RunFailed(f"{cfg.tool}: bad arguments ({exc})") from exc

    def _retrieve(self, dataset_key: str, query: str, top_k: int, strategy: str) -> dict[str, Any]:
        from sqlalchemy import or_, select

        from ...models import RagDataset
        from ..rag.pipeline import format_passages
        from ..rag.retrieval import allowed_documents, get_index, retrieve

        ds = self.db.scalar(select(RagDataset).where(RagDataset.slug == dataset_key,
                                                     or_(RagDataset.owner_id.is_(None), RagDataset.is_public.is_(True),
                                                         RagDataset.owner_id == self.owner_id)))
        if ds is None:
            raise RunFailed(f"Dataset '{dataset_key}' not found or not readable.")
        if not query.strip():
            raise RunFailed("Retrieval query is empty.")
        idx = get_index(self.db, ds, {})
        docs = allowed_documents(self.db, ds, self.groups)
        hits, _ = retrieve(self.db, idx, query, set(docs), strategy, top_k, True)
        return {"passages": [{"n": i, "document": docs[h.chunk["document_id"]].title, "text": h.chunk["text"],
                              "score": round(h.score, 3)} for i, h in enumerate(hits, start=1)],
                "context": format_passages(hits, docs) or "(no relevant passages)", "count": len(hits)}


def _compare(left: Any, op: str, right: str) -> bool:
    if op == "exists":
        return left not in (None, "", [], {})
    if op == "is_true":
        return str(left).strip().lower() in ("true", "yes", "1", "y")
    ls = to_text(left).strip()
    if op in ("gt", "lt"):
        try:
            a, b = float(ls), float(right)
        except ValueError:
            return False
        return a > b if op == "gt" else a < b
    if op == "equals":
        return ls.lower() == right.strip().lower()
    if op == "not_equals":
        return ls.lower() != right.strip().lower()
    if op == "contains":
        return right.strip().lower() in ls.lower()
    if op == "not_contains":
        return right.strip().lower() not in ls.lower()
    return False


def snapshot(rs: RunState) -> dict[str, Any]:
    return json.loads(json.dumps({"state": rs.state, "input": rs.input}, default=str))
