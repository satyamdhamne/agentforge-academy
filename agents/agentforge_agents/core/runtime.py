"""Runtime primitives shared by every reference agent: tracing, budgets, tools and approvals."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .llm import Completion, CompletionRequest, LLMProvider, ToolSpec, complete_structured

try:  # OpenTelemetry is optional; spans are always recorded in our own trace as well.
    from opentelemetry import trace as _otel_trace  # type: ignore

    _tracer = _otel_trace.get_tracer("agentforge.agents")
except Exception:  # pragma: no cover - depends on optional install
    _tracer = None

T = TypeVar("T", bound=BaseModel)


class BudgetExceeded(RuntimeError):
    pass


class ToolError(RuntimeError):
    pass


@dataclass
class Span:
    name: str
    kind: str  # "llm" | "tool" | "step"
    start_ms: float
    duration_ms: float = 0.0
    status: str = "ok"
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "start_ms": round(self.start_ms, 2),
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status,
            "attributes": self.attributes,
        }


class Tracer:
    def __init__(self, trace_id: str | None = None):
        self.trace_id = trace_id or uuid.uuid4().hex
        self.spans: list[Span] = []
        self._t0 = time.perf_counter()

    def span(self, name: str, kind: str = "step", **attributes: Any) -> _SpanCtx:
        return _SpanCtx(self, name, kind, attributes)

    def to_list(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self.spans]


class _SpanCtx:
    def __init__(self, tracer: Tracer, name: str, kind: str, attributes: dict[str, Any]):
        self.tracer, self.name, self.kind, self.attributes = tracer, name, kind, attributes
        self._otel = None

    def __enter__(self) -> Span:
        now = (time.perf_counter() - self.tracer._t0) * 1000
        self.span = Span(self.name, self.kind, now, attributes=dict(self.attributes))
        self.tracer.spans.append(self.span)
        if _tracer is not None:
            self._otel = _tracer.start_as_current_span(f"{self.kind}:{self.name}")
            self._otel.__enter__()
        self._started = time.perf_counter()
        return self.span

    def __exit__(self, exc_type, exc, tb) -> None:
        self.span.duration_ms = (time.perf_counter() - self._started) * 1000
        if exc is not None:
            self.span.status = "error"
            self.span.attributes["error"] = f"{exc_type.__name__}: {str(exc)[:300]}"
        if self._otel is not None:
            self._otel.__exit__(exc_type, exc, tb)


@dataclass
class Budget:
    max_llm_calls: int = 12
    max_total_tokens: int = 60_000
    max_seconds: float = 60.0


@dataclass
class Usage:
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


SandboxRunner = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class AgentContext:
    """Everything an agent run needs from the outside world. Injected, never global."""

    provider: LLMProvider
    tracer: Tracer = field(default_factory=Tracer)
    budget: Budget = field(default_factory=Budget)
    usage: Usage = field(default_factory=Usage)
    sandbox: SandboxRunner | None = None
    user_groups: list[str] = field(default_factory=lambda: ["everyone"])
    started_at: float = field(default_factory=time.perf_counter)

    # ---- budget -------------------------------------------------------------------------
    def check_budget(self) -> None:
        if self.usage.llm_calls >= self.budget.max_llm_calls:
            raise BudgetExceeded(f"LLM call budget of {self.budget.max_llm_calls} exhausted")
        if self.usage.total_tokens >= self.budget.max_total_tokens:
            raise BudgetExceeded(f"Token budget of {self.budget.max_total_tokens} exhausted")
        if time.perf_counter() - self.started_at > self.budget.max_seconds:
            raise BudgetExceeded(f"Time budget of {self.budget.max_seconds}s exhausted")

    def _record(self, completion: Completion, span: Span) -> None:
        self.usage.llm_calls += 1
        self.usage.input_tokens += completion.usage.input_tokens
        self.usage.output_tokens += completion.usage.output_tokens
        span.attributes.update(
            provider=completion.provider,
            model=completion.model,
            input_tokens=completion.usage.input_tokens,
            output_tokens=completion.usage.output_tokens,
        )

    # ---- model calls ---------------------------------------------------------------------
    def llm(self, request: CompletionRequest) -> Completion:
        self.check_budget()
        with self.tracer.span(request.task, "llm") as span:
            completion = self.provider.complete(request)
            self._record(completion, span)
            if completion.tool_calls:
                span.attributes["tool_calls"] = [c.name for c in completion.tool_calls]
            return completion

    def structured(self, request: CompletionRequest, model_cls: type[T], max_retries: int = 2) -> T:
        self.check_budget()
        with self.tracer.span(request.task, "llm") as span:
            def on_completion(c: Completion) -> None:
                self.check_budget()
                self._record(c, span)

            return complete_structured(self.provider, request, model_cls, max_retries, on_completion)

    # ---- deterministic steps ---------------------------------------------------------------
    def step(self, name: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        with self.tracer.span(name, "step"):
            return fn(*args, **kwargs)


# --------------------------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------------------------


@dataclass
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    fn: Callable[..., Any]
    side_effect: bool = False  # side-effect tools never run without human approval

    def spec(self) -> ToolSpec:
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        return ToolSpec(self.name, self.description, schema)


@dataclass
class PendingAction:
    tool: str
    arguments: dict[str, Any]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "arguments": self.arguments, "reason": self.reason}


class ToolRegistry:
    """Allowlist of tools. Arguments are validated before a tool function is ever called."""

    def __init__(self, tools: list[Tool]):
        self._tools = {t.name: t for t in tools}

    def specs(self, include_side_effects: bool = True) -> list[ToolSpec]:
        return [t.spec() for t in self._tools.values() if include_side_effects or not t.side_effect]

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise ToolError(f"Tool '{name}' is not allowlisted")
        return self._tools[name]

    def validate(self, name: str, arguments: dict[str, Any]) -> BaseModel:
        tool = self.get(name)
        try:
            return tool.args_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolError(f"Invalid arguments for {name}: {exc.errors(include_url=False)}") from exc

    def call(self, ctx: AgentContext, name: str, arguments: dict[str, Any], approved: bool = False) -> Any:
        tool = self.get(name)
        args = self.validate(name, arguments)
        if tool.side_effect and not approved:
            raise ToolError(f"Tool '{name}' has side effects and requires human approval")
        ctx.usage.tool_calls += 1
        with ctx.tracer.span(name, "tool", arguments=args.model_dump()):
            return tool.fn(**args.model_dump())
