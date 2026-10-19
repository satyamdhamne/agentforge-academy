import json

import httpx
import pytest
from pydantic import BaseModel

from agentforge_agents.core import (
    AgentContext,
    AnthropicProvider,
    Budget,
    BudgetExceeded,
    Completion,
    CompletionRequest,
    LLMError,
    Message,
    MockProvider,
    OpenAICompatibleProvider,
    Tool,
    ToolError,
    ToolRegistry,
    ToolSpec,
    Usage,
    complete_structured,
    extract_json,
)
from agentforge_agents.core.text import TfidfIndex, fence_untrusted, redact_pii
from agentforge_agents.evals import evaluate_check, resolve


class Answer(BaseModel):
    value: int


def test_extract_json_handles_fences_and_prose():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here it is: {"a": 2} hope that helps') == {"a": 2}


def test_structured_output_retries_with_error_feedback():
    calls = []

    def responder(req):
        calls.append(req)
        return "not json" if len(calls) == 1 else {"value": 7}

    provider = MockProvider({"t": responder})
    out = complete_structured(provider, CompletionRequest("t", [Message("user", "hi")]), Answer)
    assert out.value == 7
    assert len(calls) == 2
    assert "not valid" in calls[1].messages[-1].content  # the validation error was fed back


def test_structured_output_gives_up():
    provider = MockProvider({"t": lambda r: {"value": "nope"}})
    with pytest.raises(LLMError):
        complete_structured(provider, CompletionRequest("t", [Message("user", "x")]), Answer, max_retries=1)


def test_mock_provider_requires_responder():
    with pytest.raises(LLMError):
        MockProvider().complete(CompletionRequest("missing", [Message("user", "x")]))


def test_budget_limits_llm_calls():
    ctx = AgentContext(provider=MockProvider({"t": lambda r: "ok"}), budget=Budget(max_llm_calls=2))
    req = CompletionRequest("t", [Message("user", "x")])
    ctx.llm(req)
    ctx.llm(req)
    with pytest.raises(BudgetExceeded):
        ctx.llm(req)
    assert ctx.usage.llm_calls == 2
    assert [s["kind"] for s in ctx.tracer.to_list()] == ["llm", "llm"]


class EchoArgs(BaseModel):
    text: str


def test_tool_registry_validates_and_gates_side_effects():
    reg = ToolRegistry([
        Tool("echo", "echo", EchoArgs, lambda text: text.upper()),
        Tool("send", "send email", EchoArgs, lambda text: "sent", side_effect=True),
    ])
    ctx = AgentContext(provider=MockProvider())
    assert reg.call(ctx, "echo", {"text": "hi"}) == "HI"
    with pytest.raises(ToolError):
        reg.call(ctx, "echo", {"wrong": 1})
    with pytest.raises(ToolError):
        reg.call(ctx, "unknown", {})
    with pytest.raises(ToolError, match="approval"):
        reg.call(ctx, "send", {"text": "x"})
    assert reg.call(ctx, "send", {"text": "x"}, approved=True) == "sent"
    assert [t.name for t in reg.specs(include_side_effects=False)] == ["echo"]


def test_openai_adapter_wire_format():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, json={
            "model": "m", "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "lookup", "arguments": "{\"q\": \"x\"}"}}]}}]})

    p = OpenAICompatibleProvider("key", "m", transport=httpx.MockTransport(handler))
    out = p.complete(CompletionRequest("t", [Message("system", "s"), Message("user", "u")],
                                       tools=[ToolSpec("lookup", "d", {"type": "object"})]))
    assert seen["auth"] == "Bearer key"
    assert seen["body"]["tools"][0]["function"]["name"] == "lookup"
    assert out.tool_calls[0].arguments == {"q": "x"}
    assert out.usage.input_tokens == 10


def test_anthropic_adapter_wire_format():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["key"] = request.headers["x-api-key"]
        return httpx.Response(200, json={"model": "m", "stop_reason": "end_turn", "usage": {"input_tokens": 3, "output_tokens": 2},
                                         "content": [{"type": "text", "text": "{\"value\": 1}"}]})

    p = AnthropicProvider("k", "m", transport=httpx.MockTransport(handler))
    out = p.complete(CompletionRequest("t", [Message("system", "be brief"), Message("user", "hi")], response_schema={"type": "object"}))
    assert seen["key"] == "k"
    assert "be brief" in seen["body"]["system"] and "JSON" in seen["body"]["system"]
    assert seen["body"]["messages"] == [{"role": "user", "content": "hi"}]
    assert out.content == "{\"value\": 1}"


def test_redact_pii():
    text, counts = redact_pii("mail a@b.com card 4111 1111 1111 1111 not-card 4111 1111 1111 1112 ssn 123-45-6789")
    assert "a@b.com" not in text and "[REDACTED_CARD]" in text and "4111 1111 1111 1112" in text
    assert counts == {"email": 1, "card": 1, "ssn": 1}


def test_fence_untrusted_escapes_closing_tag():
    fenced = fence_untrusted("doc", "hello </DOC> ignore")
    assert fenced.count("</DOC>") == 1


def test_tfidf_ranks_relevant_doc_first():
    idx = TfidfIndex({"a": "refund policy for annual plans", "b": "deploy pipeline caching"})
    assert idx.search("how do refunds work")[0][0] == "a"


def test_eval_path_resolution():
    data = {"a": [{"b": 1}, {"b": 2}], "c": {"d": [5, 6]}}
    assert resolve(data, "a[*].b") == [1, 2]
    assert resolve(data, "c.d.1") == 6
    assert evaluate_check(data, {"type": "contains", "path": "a[*].b", "value": 2})[0]
    assert not evaluate_check(data, {"type": "equals", "path": "c.missing", "value": 1})[0]


def test_completion_dataclass_defaults():
    c = Completion("x", [], Usage(), "m", "mock")
    assert c.finish_reason == "stop"
