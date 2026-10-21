"""Node registry (typed configs) and static validation of workflow graphs."""

from __future__ import annotations

import re
from collections import defaultdict, deque
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from ..assertions import TYPES as ASSERTION_TYPES
from .tools import TOOLS

KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
REF = re.compile(r"{{\s*([A-Za-z_][\w\-]*)(?:[.\w\-]*)\s*}}")
MAX_NODES, MAX_EDGES = 40, 80


class InputField(BaseModel):
    name: str = Field(..., pattern=r"^[a-z][a-z0-9_]{0,39}$")
    label: str = Field("", max_length=80)
    type: Literal["text", "number", "json"] = "text"
    required: bool = True
    default: Any = None


class InputCfg(BaseModel):
    fields: list[InputField] = Field(default_factory=lambda: [InputField(name="question", label="Question")], max_length=10)


class PromptCfg(BaseModel):
    template: str = Field(..., min_length=1, max_length=8000)


class LlmCfg(BaseModel):
    system: str = Field("", max_length=6000)
    prompt: str = Field(..., min_length=1, max_length=12000)
    temperature: float = Field(0.0, ge=0, le=2)
    max_tokens: int = Field(512, ge=16, le=4000)
    json_schema: dict[str, Any] | None = None


class ToolCfg(BaseModel):
    tool: str
    args: dict[str, str] = Field(default_factory=dict)


class RetrievalCfg(BaseModel):
    dataset: str = Field("northwind-handbook", max_length=120)
    query: str = Field("{{input.question}}", min_length=1, max_length=2000)
    top_k: int = Field(4, ge=1, le=10)
    strategy: Literal["vector", "keyword", "hybrid"] = "hybrid"


class ConditionCfg(BaseModel):
    left: str = Field(..., min_length=1, max_length=500)
    op: Literal["equals", "not_equals", "contains", "not_contains", "gt", "lt", "exists", "is_true"] = "equals"
    right: str = Field("", max_length=500)


class MemoryCfg(BaseModel):
    key: str = Field(..., pattern=r"^[a-z][a-z0-9_]{0,39}$")
    mode: Literal["set", "append", "get"] = "set"
    value: str = Field("", max_length=4000)


class ApprovalCfg(BaseModel):
    message: str = Field("Approve this action?", min_length=1, max_length=2000)


class Check(BaseModel):
    type: str
    value: Any = None
    label: str | None = None


class EvaluationCfg(BaseModel):
    target: str = Field(..., min_length=1, max_length=2000)
    checks: list[Check] = Field(..., min_length=1, max_length=10)
    stop_on_fail: bool = False


class OutputCfg(BaseModel):
    value: str = Field(..., min_length=1, max_length=8000)


NODE_TYPES: dict[str, dict[str, Any]] = {
    "input": {"label": "Input", "cfg": InputCfg, "description": "Fields the run starts with.", "color": "signal"},
    "prompt": {"label": "Prompt", "cfg": PromptCfg, "description": "Render a template from earlier values.", "color": "muted"},
    "llm": {"label": "LLM", "cfg": LlmCfg, "description": "Call the model (simulator on Free, configured model on paid plans).",
            "color": "llm"},
    "tool": {"label": "Tool", "cfg": ToolCfg, "description": "Call an allowlisted tool. Side-effect tools need an approval upstream.",
             "color": "tool"},
    "retrieval": {"label": "Retrieval", "cfg": RetrievalCfg, "description": "Search a RAG dataset with your permissions.",
                  "color": "tool"},
    "condition": {"label": "Condition", "cfg": ConditionCfg, "description": "Branch on a value: true / false outputs.",
                  "color": "muted"},
    "memory": {"label": "Memory", "cfg": MemoryCfg, "description": "Set, append to or read run state.", "color": "muted"},
    "human_approval": {"label": "Human approval", "cfg": ApprovalCfg, "description": "Pause until a person approves.",
                       "color": "fail"},
    "evaluation": {"label": "Evaluation", "cfg": EvaluationCfg, "description": "Check a value with assertions.", "color": "pass"},
    "output": {"label": "Output", "cfg": OutputCfg, "description": "The run's result.", "color": "signal"},
}


def node_types() -> list[dict[str, Any]]:
    return [{"type": k, "label": v["label"], "description": v["description"], "color": v["color"],
             "schema": v["cfg"].model_json_schema(), "defaults": _defaults(k)} for k, v in NODE_TYPES.items()]


def _defaults(t: str) -> dict[str, Any]:
    return {
        "input": {"fields": [{"name": "question", "label": "Question", "type": "text", "required": True}]},
        "prompt": {"template": "Answer briefly: {{input.question}}"},
        "llm": {"system": "You are a concise assistant.", "prompt": "{{input.question}}", "temperature": 0, "max_tokens": 512},
        "tool": {"tool": "calculator", "args": {"expression": "2 + 2"}},
        "retrieval": {"dataset": "northwind-handbook", "query": "{{input.question}}", "top_k": 4, "strategy": "hybrid"},
        "condition": {"left": "{{input.question}}", "op": "contains", "right": "urgent"},
        "memory": {"key": "notes", "mode": "set", "value": "{{input.question}}"},
        "human_approval": {"message": "Approve the next step?"},
        "evaluation": {"target": "{{input.question}}", "checks": [{"type": "max_words", "value": 200}]},
        "output": {"value": "{{input.question}}"},
    }[t]


class Issue(BaseModel):
    level: Literal["error", "warning"]
    message: str
    node: str | None = None


def parse_config(node_type: str, config: dict[str, Any]) -> BaseModel:
    return NODE_TYPES[node_type]["cfg"].model_validate(config or {})


def _refs(obj: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(obj, str):
        out |= {m.group(1) for m in REF.finditer(obj)}
    elif isinstance(obj, dict):
        for v in obj.values():
            out |= _refs(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= _refs(v)
    return out


def validate(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[Issue]:
    issues: list[Issue] = []
    err = lambda m, n=None: issues.append(Issue(level="error", message=m, node=n))  # noqa: E731
    warn = lambda m, n=None: issues.append(Issue(level="warning", message=m, node=n))  # noqa: E731
    if not nodes:
        return [Issue(level="error", message="Add an input node and an output node.")]
    if len(nodes) > MAX_NODES or len(edges) > MAX_EDGES:
        err(f"Workflows are limited to {MAX_NODES} nodes and {MAX_EDGES} edges.")
    by_key: dict[str, dict[str, Any]] = {}
    for n in nodes:
        k, t = n.get("key", ""), n.get("type", "")
        if not KEY.match(k):
            err(f"Node id '{k}' must be lowercase letters, digits and underscores.", k or None)
            continue
        if k in by_key:
            err(f"Duplicate node id '{k}'.", k)
            continue
        if t not in NODE_TYPES:
            err(f"Unknown node type '{t}'. Only built-in node types can run.", k)
            continue
        if k in ("input", "memory") and t != "input":
            err(f"'{k}' is reserved; rename this node.", k)
        by_key[k] = n
        try:
            cfg = parse_config(t, n.get("config") or {})
        except ValidationError as exc:
            for e in exc.errors()[:3]:
                err(f"{NODE_TYPES[t]['label']} config: {'.'.join(map(str, e['loc']))} - {e['msg']}", k)
            continue
        if t == "tool" and cfg.tool not in TOOLS:
            err(f"Tool '{cfg.tool}' isn't on the allowlist.", k)
        elif t == "tool":
            missing = [a for a in TOOLS[cfg.tool].args if a not in cfg.args and a not in ("path", "priority", "body", "dataset")]
            if missing:
                err(f"Tool '{cfg.tool}' needs argument(s): {', '.join(missing)}.", k)
        if t == "evaluation":
            for c in cfg.checks:
                if c.type not in ASSERTION_TYPES:
                    err(f"Unknown check type '{c.type}'.", k)

    inputs = [k for k, n in by_key.items() if n["type"] == "input"]
    outputs = [k for k, n in by_key.items() if n["type"] == "output"]
    if len(inputs) != 1:
        err("A workflow needs exactly one input node.")
    if not outputs:
        err("A workflow needs at least one output node.")

    succ: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
    pred: dict[str, list[str]] = defaultdict(list)
    seen_edges = set()
    for e in edges:
        s, t, h = e.get("source"), e.get("target"), e.get("handle") or None
        if s not in by_key or t not in by_key:
            err(f"Edge {s} → {t} references a missing node.")
            continue
        if s == t:
            err("A node can't connect to itself.", s)
            continue
        if (s, t, h) in seen_edges:
            continue
        seen_edges.add((s, t, h))
        if by_key[t]["type"] == "input":
            err("Nothing can connect into the input node.", t)
        if by_key[s]["type"] == "output":
            err("Output nodes can't have outgoing connections.", s)
        if by_key[s]["type"] == "condition":
            if h not in ("true", "false"):
                err("Connect condition nodes from their true or false handle.", s)
        elif h:
            err(f"Only condition nodes have '{h}' handles.", s)
        succ[s].append((t, h))
        pred[t].append(s)
    for k, n in by_key.items():
        if n["type"] == "condition":
            handles = {h for _, h in succ[k]}
            if "true" not in handles and "false" not in handles:
                err("Connect at least one branch of this condition.", k)

    # cycles (Kahn)
    indeg = {k: len(set(pred[k])) for k in by_key}
    q = deque(k for k, d in indeg.items() if d == 0)
    order = []
    while q:
        k = q.popleft()
        order.append(k)
        for t in {t for t, _ in succ[k]}:
            indeg[t] -= 1
            if indeg[t] == 0:
                q.append(t)
    if len(order) != len(by_key):
        err("The graph has a cycle. Loops aren't supported yet: unroll them or use a condition.")
        return issues

    if len(inputs) == 1:
        reach = _reachable(inputs[0], succ)
        for k in by_key:
            if k not in reach:
                warn("This node isn't connected to the input, so it will never run.", k)
        for k in outputs:
            if k not in reach:
                err("This output can't be reached from the input.", k)
        # Side-effect tools must be gated: every path from input passes through a human_approval node.
        approvals = {k for k, n in by_key.items() if n["type"] == "human_approval"}
        ungated = _reachable(inputs[0], succ, blocked=approvals)
        for k, n in by_key.items():
            if n["type"] == "tool":
                tool = (n.get("config") or {}).get("tool")
                if tool in TOOLS and TOOLS[tool].side_effect and k in ungated:
                    err(f"'{tool}' changes something outside the run. Put a human approval node before it on every path.", k)

    ancestors = _ancestors(by_key, pred)
    for k, n in by_key.items():
        for ref in _refs(n.get("config") or {}):
            if ref in ("input", "memory"):
                continue
            if ref not in by_key:
                err(f"Template refers to unknown node '{ref}'.", k)
            elif ref not in ancestors[k]:
                err(f"Template uses '{ref}', which doesn't run before this node. Connect it upstream.", k)
    llms = [k for k, n in by_key.items() if n["type"] == "llm"]
    if llms and not any(n["type"] == "evaluation" for n in by_key.values()):
        warn("No evaluation node: consider checking model output before it reaches the output.")
    return issues


def _reachable(start: str, succ: dict[str, list[tuple[str, str | None]]], blocked: set[str] | None = None) -> set[str]:
    seen = {start}
    q = deque([start])
    while q:
        k = q.popleft()
        if blocked and k in blocked:
            continue
        for t, _ in succ[k]:
            if t not in seen:
                seen.add(t)
                q.append(t)
    return seen


def _ancestors(by_key: dict[str, Any], pred: dict[str, list[str]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}

    def walk(k: str) -> set[str]:
        if k in out:
            return out[k]
        out[k] = set()
        acc: set[str] = set()
        for p in pred[k]:
            acc |= {p} | walk(p)
        out[k] = acc
        return acc

    for k in by_key:
        walk(k)
    return out


def topo_order(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[str]:
    keys = [n["key"] for n in nodes]
    indeg = {k: 0 for k in keys}
    succ: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        if e["target"] not in succ[e["source"]]:
            succ[e["source"]].add(e["target"])
            indeg[e["target"]] += 1
    q = deque(sorted(k for k in keys if indeg[k] == 0))
    order = []
    while q:
        k = q.popleft()
        order.append(k)
        for t in sorted(succ[k]):
            indeg[t] -= 1
            if indeg[t] == 0:
                q.append(t)
    return order
