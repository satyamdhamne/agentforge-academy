"""Provider-agnostic model adapter.

Every agent talks to models through `LLMProvider.complete()`. Three providers ship:

* `MockProvider`   - deterministic, offline. Each agent registers a *mock responder* for its
                     task name. Mock output is clearly labelled `provider="mock"` everywhere.
* `OpenAICompatibleProvider` - any server that speaks the OpenAI Chat Completions API
                     (OpenAI, Azure OpenAI, vLLM, Ollama's /v1 endpoint, LM Studio, ...).
* `AnthropicProvider` - Anthropic Messages API.

Provider SDKs are intentionally not required: both real adapters use `httpx` directly so the
wire format is visible to learners and easy to stub in tests.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class CompletionRequest:
    task: str  # stable task name, used by the mock provider and for tracing
    messages: list[Message]
    tools: list[ToolSpec] | None = None
    response_schema: dict[str, Any] | None = None
    temperature: float = 0.0
    max_tokens: int = 1024
    model: str | None = None
    context: dict[str, Any] = field(default_factory=dict)  # structured data for mock responders only


@dataclass
class Completion:
    content: str
    tool_calls: list[ToolCall]
    usage: Usage
    model: str
    provider: str
    latency_ms: int = 0
    finish_reason: str = "stop"


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, request: CompletionRequest) -> Completion: ...


def estimate_tokens(text: str) -> int:
    """Rough heuristic (~4 chars/token for English). Good enough for budgets and mock accounting."""
    return max(1, len(text) // 4)


# --------------------------------------------------------------------------------------------
# Mock provider
# --------------------------------------------------------------------------------------------

MockResponder = Callable[[CompletionRequest], "str | dict | Completion"]


class MockProvider:
    """Deterministic provider for offline use, CI and free-tier demos.

    A responder receives the full request (including `request.context`, which real providers
    ignore) and returns either a string, a dict (serialised as JSON), or a full Completion
    (useful for returning tool calls).
    """

    name = "mock"

    def __init__(self, responders: dict[str, MockResponder] | None = None, model: str = "mock-1"):
        self.model = model
        self._responders: dict[str, MockResponder] = dict(responders or {})

    def register(self, task: str, responder: MockResponder) -> None:
        self._responders[task] = responder

    def register_default(self, task: str, responder: MockResponder) -> None:
        self._responders.setdefault(task, responder)

    def complete(self, request: CompletionRequest) -> Completion:
        started = time.perf_counter()
        responder = self._responders.get(request.task)
        if responder is None:
            raise LLMError(f"MockProvider has no responder registered for task '{request.task}'")
        result = responder(request)
        prompt_text = "\n".join(m.content for m in request.messages)
        if isinstance(result, Completion):
            result.latency_ms = int((time.perf_counter() - started) * 1000)
            return result
        content = json.dumps(result) if isinstance(result, (dict, list)) else str(result)
        return Completion(
            content=content,
            tool_calls=[],
            usage=Usage(estimate_tokens(prompt_text), estimate_tokens(content)),
            model=self.model,
            provider=self.name,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


# --------------------------------------------------------------------------------------------
# OpenAI-compatible provider
# --------------------------------------------------------------------------------------------


class OpenAICompatibleProvider:
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_s: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ):
        if not model:
            raise LLMError("OPENAI_MODEL must be set when LLM_PROVIDER=openai")
        self.model = model
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            timeout=timeout_s,
            transport=transport,
        )

    @staticmethod
    def _to_wire(m: Message) -> dict[str, Any]:
        if m.role == "tool":
            return {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content}
        msg: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.tool_calls:
            msg["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                for c in m.tool_calls
            ]
        return msg

    def complete(self, request: CompletionRequest) -> Completion:
        body: dict[str, Any] = {
            "model": request.model or self.model,
            "messages": [self._to_wire(m) for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.tools:
            body["tools"] = [
                {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
                for t in request.tools
            ]
        if request.response_schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": request.task.replace(".", "_")[:64], "schema": request.response_schema},
            }
        started = time.perf_counter()
        resp = self._client.post("/chat/completions", json=body)
        if resp.status_code >= 400:
            raise LLMError(f"OpenAI-compatible API error {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        choice = data["choices"][0]
        msg = choice["message"]
        calls = []
        for c in msg.get("tool_calls") or []:
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"__invalid_json__": c["function"].get("arguments")}
            calls.append(ToolCall(id=c["id"], name=c["function"]["name"], arguments=args))
        usage = data.get("usage") or {}
        return Completion(
            content=msg.get("content") or "",
            tool_calls=calls,
            usage=Usage(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)),
            model=data.get("model", body["model"]),
            provider=self.name,
            latency_ms=int((time.perf_counter() - started) * 1000),
            finish_reason=choice.get("finish_reason") or "stop",
        )


# --------------------------------------------------------------------------------------------
# Anthropic provider
# --------------------------------------------------------------------------------------------


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.anthropic.com",
        timeout_s: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ):
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY must be set when LLM_PROVIDER=anthropic")
        if not model:
            raise LLMError("ANTHROPIC_MODEL must be set when LLM_PROVIDER=anthropic")
        self.model = model
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            timeout=timeout_s,
            transport=transport,
        )

    def complete(self, request: CompletionRequest) -> Completion:
        system_parts = [m.content for m in request.messages if m.role == "system"]
        if request.response_schema:
            system_parts.append(
                "Respond with a single JSON object only (no prose, no code fences) that validates "
                f"against this JSON schema:\n{json.dumps(request.response_schema)}"
            )
        messages: list[dict[str, Any]] = []
        for m in request.messages:
            if m.role == "system":
                continue
            if m.role == "tool":
                block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
                if messages and messages[-1]["role"] == "user" and isinstance(messages[-1]["content"], list):
                    messages[-1]["content"].append(block)
                else:
                    messages.append({"role": "user", "content": [block]})
            elif m.role == "assistant" and m.tool_calls:
                blocks: list[dict[str, Any]] = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                blocks += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments} for c in m.tool_calls]
                messages.append({"role": "assistant", "content": blocks})
            else:
                messages.append({"role": m.role, "content": m.content})
        body: dict[str, Any] = {
            "model": request.model or self.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
        }
        if system_parts:
            body["system"] = "\n\n".join(system_parts)
        if request.tools:
            body["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in request.tools]
        started = time.perf_counter()
        resp = self._client.post("/v1/messages", json=body)
        if resp.status_code >= 400:
            raise LLMError(f"Anthropic API error {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        calls = [
            ToolCall(id=b["id"], name=b["name"], arguments=b.get("input") or {})
            for b in data.get("content", [])
            if b.get("type") == "tool_use"
        ]
        usage = data.get("usage") or {}
        return Completion(
            content=text,
            tool_calls=calls,
            usage=Usage(usage.get("input_tokens", 0), usage.get("output_tokens", 0)),
            model=data.get("model", body["model"]),
            provider=self.name,
            latency_ms=int((time.perf_counter() - started) * 1000),
            finish_reason=data.get("stop_reason") or "end_turn",
        )


# --------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
T = TypeVar("T", bound=BaseModel)


def extract_json(text: str) -> Any:
    """Parse JSON from a model reply, tolerating code fences and leading prose."""
    cleaned = _FENCE.sub("", text.strip()).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = min((i for i in (cleaned.find("{"), cleaned.find("[")) if i >= 0), default=-1)
        if start < 0:
            raise
        end = max(cleaned.rfind("}"), cleaned.rfind("]"))
        return json.loads(cleaned[start : end + 1])


def complete_structured(
    provider: LLMProvider,
    request: CompletionRequest,
    model_cls: type[T],
    max_retries: int = 2,
    on_completion: Callable[[Completion], None] | None = None,
) -> T:
    """Ask for JSON matching `model_cls`; on parse/validation failure, feed the error back and retry."""
    request.response_schema = request.response_schema or model_cls.model_json_schema()
    messages = list(request.messages)
    last_error = ""
    for attempt in range(max_retries + 1):
        req = CompletionRequest(**{**request.__dict__, "messages": messages})
        completion = provider.complete(req)
        if on_completion:
            on_completion(completion)
        try:
            return model_cls.model_validate(extract_json(completion.content))
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = str(exc)[:1000]
            messages = messages + [
                Message("assistant", completion.content),
                Message(
                    "user",
                    f"Your previous reply was not valid for the required schema (attempt {attempt + 1}). "
                    f"Error: {last_error}\nReturn only corrected JSON.",
                ),
            ]
    raise LLMError(f"Model did not return valid {model_cls.__name__} after {max_retries + 1} attempts: {last_error}")


def provider_from_env(mock_responders: dict[str, MockResponder] | None = None) -> LLMProvider:
    """Build a provider from LLM_PROVIDER / *_API_KEY / *_MODEL environment variables."""
    kind = os.getenv("LLM_PROVIDER", "mock").lower()
    if kind == "openai":
        return OpenAICompatibleProvider(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            model=os.getenv("OPENAI_MODEL", ""),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )
    if kind == "anthropic":
        return AnthropicProvider(api_key=os.getenv("ANTHROPIC_API_KEY", ""), model=os.getenv("ANTHROPIC_MODEL", ""))
    if kind != "mock":
        raise LLMError(f"Unknown LLM_PROVIDER '{kind}'. Use mock, openai or anthropic.")
    return MockProvider(mock_responders)
