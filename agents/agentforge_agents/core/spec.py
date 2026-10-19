"""AgentSpec: the contract every reference agent exports, plus a uniform runner."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from .llm import LLMError, LLMProvider, MockProvider, MockResponder
from .runtime import AgentContext, Budget, BudgetExceeded, SandboxRunner, ToolError, Tracer


@dataclass
class AgentSpec:
    slug: str
    name: str
    input_model: type[BaseModel]
    run: Callable[[Any, AgentContext], dict[str, Any]]
    mock_responders: dict[str, MockResponder]
    examples: list[dict[str, Any]]
    blueprint: dict[str, Any]
    package: str
    apply_actions: Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]] | None = None
    budget: Budget = field(default_factory=Budget)


@dataclass
class RunResult:
    status: str  # succeeded | failed | awaiting_approval
    output: dict[str, Any] | None
    trace_id: str
    trace: list[dict[str, Any]]
    provider: str
    model: str
    llm_calls: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    latency_ms: int
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def build_provider(spec: AgentSpec, provider: LLMProvider | None) -> LLMProvider:
    if provider is None:
        return MockProvider(spec.mock_responders)
    if isinstance(provider, MockProvider):
        for task, responder in spec.mock_responders.items():
            provider.register_default(task, responder)  # keep responders the caller already set
    return provider


def run_agent(
    spec: AgentSpec,
    raw_input: dict[str, Any],
    provider: LLMProvider | None = None,
    sandbox: SandboxRunner | None = None,
    budget: Budget | None = None,
    user_groups: list[str] | None = None,
    trace_id: str | None = None,
) -> RunResult:
    prov = build_provider(spec, provider)
    ctx = AgentContext(
        provider=prov,
        tracer=Tracer(trace_id),
        budget=budget or spec.budget,
        sandbox=sandbox,
        user_groups=user_groups or ["everyone"],
    )
    started = time.perf_counter()
    output: dict[str, Any] | None = None
    error: str | None = None
    status = "succeeded"
    try:
        parsed = spec.input_model.model_validate(raw_input)
        output = spec.run(parsed, ctx)
        if output.get("pending_actions"):
            status = "awaiting_approval"
    except ValidationError as exc:
        status, error = "failed", f"Invalid input: {exc.errors(include_url=False)}"
    except (BudgetExceeded, ToolError, LLMError) as exc:
        status, error = "failed", f"{type(exc).__name__}: {exc}"
    return RunResult(
        status=status,
        output=output,
        trace_id=ctx.tracer.trace_id,
        trace=ctx.tracer.to_list(),
        provider=getattr(prov, "name", "unknown"),
        model=getattr(prov, "model", "unknown"),
        llm_calls=ctx.usage.llm_calls,
        tool_calls=ctx.usage.tool_calls,
        input_tokens=ctx.usage.input_tokens,
        output_tokens=ctx.usage.output_tokens,
        latency_ms=int((time.perf_counter() - started) * 1000),
        error=error,
    )
