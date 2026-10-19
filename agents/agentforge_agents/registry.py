"""Registry of implemented agents + helpers that assemble the full agent detail page from code.

Sections that can be derived from the implementation (prompts, tool schemas, input schema,
folder structure, source files, evaluation dataset) are read from the code itself, so the
documentation cannot drift from what actually runs.
"""

from __future__ import annotations

import importlib
import inspect
import re
from pathlib import Path
from typing import Any

from .bug_triage import SPEC as BUG_TRIAGE
from .core.spec import AgentSpec
from .csv_cleaning import SPEC as CSV_CLEANING
from .evals import load_cases
from .invoice_extraction import SPEC as INVOICE_EXTRACTION
from .log_analysis import SPEC as LOG_ANALYSIS
from .pdf_knowledge import SPEC as PDF_KNOWLEDGE
from .pr_review import SPEC as PR_REVIEW
from .release_notes import SPEC as RELEASE_NOTES
from .sql_assistant import SPEC as SQL_ASSISTANT
from .support_triage import SPEC as SUPPORT_TRIAGE
from .unit_test_gen import SPEC as UNIT_TEST_GEN

IMPLEMENTED: dict[str, AgentSpec] = {
    s.slug: s
    for s in [PR_REVIEW, LOG_ANALYSIS, SQL_ASSISTANT, UNIT_TEST_GEN, CSV_CLEANING, PDF_KNOWLEDGE, SUPPORT_TRIAGE,
              RELEASE_NOTES, INVOICE_EXTRACTION, BUG_TRIAGE]
}

PACKAGE_ROOT = Path(__file__).parent
REPO_AGENTS_DIR = PACKAGE_ROOT.parent  # agents/
SOURCE_SUFFIXES = {".py", ".jsonl", ".md"}


def get_spec(slug: str) -> AgentSpec | None:
    return IMPLEMENTED.get(slug)


def _pkg_dir(spec: AgentSpec) -> Path:
    return Path(importlib.import_module(spec.package).__file__).parent


def _short(spec: AgentSpec) -> str:
    return spec.package.rsplit(".", 1)[-1]


def prompts(spec: AgentSpec) -> list[dict[str, str]]:
    mod = importlib.import_module(f"{spec.package}.agent")
    return [{"name": name, "template": value.strip()} for name, value in vars(mod).items()
            if name.isupper() and isinstance(value, str) and re.search(r"PROMPT|TEMPLATE", name)]


def tool_definitions(spec: AgentSpec) -> list[dict[str, Any]]:
    """Model-callable tools (JSON schemas) for agents with a registry; otherwise the deterministic steps."""
    try:
        tools_mod = importlib.import_module(f"{spec.package}.tools")
    except ModuleNotFoundError:
        tools_mod = None
    registry = getattr(tools_mod, "REGISTRY", None) if tools_mod else None
    if registry is not None:
        return [{"name": t.name, "kind": "side-effect (approval required)" if t.side_effect else "model-callable",
                 "description": t.description, "schema": t.spec().parameters} for t in registry._tools.values()]
    out = []
    for module_name in ("tools", "agent"):
        try:
            mod = importlib.import_module(f"{spec.package}.{module_name}")
        except ModuleNotFoundError:
            continue
        for name, fn in inspect.getmembers(mod, inspect.isfunction):
            if fn.__module__ != mod.__name__ or name.startswith("_") or name in ("run", "apply_actions", "render"):
                continue
            doc = (inspect.getdoc(fn) or "").split("\n")[0]
            out.append({"name": name, "kind": "deterministic step", "description": doc, "signature": f"{name}{inspect.signature(fn)}"})
    return out


def source_files(spec: AgentSpec) -> list[dict[str, str]]:
    pkg = _pkg_dir(spec)
    files = []
    for path in sorted(pkg.rglob("*")):
        if path.is_file() and path.suffix in SOURCE_SUFFIXES and "__pycache__" not in path.parts:
            rel = path.relative_to(REPO_AGENTS_DIR).as_posix()
            files.append({"path": f"agents/{rel}", "language": {".py": "python", ".jsonl": "json", ".md": "markdown"}[path.suffix],
                          "content": path.read_text(encoding="utf-8")})
    test_file = REPO_AGENTS_DIR / "tests" / f"test_{_short(spec)}.py"
    if test_file.exists():
        files.append({"path": f"agents/tests/{test_file.name}", "language": "python", "content": test_file.read_text(encoding="utf-8")})
    core = PACKAGE_ROOT / "core"
    for name in ("llm.py", "runtime.py", "spec.py", "text.py"):
        files.append({"path": f"agents/agentforge_agents/core/{name}", "language": "python",
                      "content": (core / name).read_text(encoding="utf-8")})
    return files


def folder_structure(spec: AgentSpec) -> str:
    short = _short(spec)
    names = sorted(p.relative_to(_pkg_dir(spec)).as_posix() for p in _pkg_dir(spec).rglob("*")
                   if p.is_file() and p.suffix in SOURCE_SUFFIXES and "__pycache__" not in p.parts)
    lines = ["agents/", "├── agentforge_agents/", "│   ├── core/            # provider adapters, runtime, tracing, text utils",
             f"│   └── {short}/"]
    lines += [f"│       ├── {n}" for n in names[:-1]] + ([f"│       └── {names[-1]}"] if names else [])
    lines += ["└── tests/", f"    └── test_{short}.py"]
    return "\n".join(lines)


def build_blueprint(spec: AgentSpec) -> dict[str, Any]:
    short = _short(spec)
    bp = dict(spec.blueprint)
    bp.update({
        "name": spec.name,
        "slug": spec.slug,
        "has_reference_impl": True,
        "input_schema": spec.input_model.model_json_schema(),
        "prompts": prompts(spec),
        "tools": tool_definitions(spec),
        "folder_structure": folder_structure(spec),
        "env_vars": [
            {"name": "LLM_PROVIDER", "example": "mock", "description": "mock | openai | anthropic. mock needs no key."},
            {"name": "OPENAI_API_KEY / OPENAI_MODEL / OPENAI_BASE_URL", "example": "", "description": "Any OpenAI-compatible endpoint (incl. Ollama at http://localhost:11434/v1)."},
            {"name": "ANTHROPIC_API_KEY / ANTHROPIC_MODEL", "example": "", "description": "Anthropic Messages API."},
            {"name": "SANDBOX_URL / SANDBOX_TOKEN", "example": "http://sandbox:8080", "description": "Isolated code runner (used by agents that execute code)."},
        ],
        "install": "cd agents\npython -m venv .venv && source .venv/bin/activate\npip install -e \".[dev,pdf]\"",
        "run_local": f"python -m agentforge_agents run {spec.slug} --example 0\n"
                     f"python -m agentforge_agents eval {spec.slug}\n"
                     f"pytest tests/test_{short}.py -q\n\n"
                     f"# Real model instead of mock:\nLLM_PROVIDER=anthropic ANTHROPIC_API_KEY=... ANTHROPIC_MODEL=... "
                     f"python -m agentforge_agents run {spec.slug} --example 0",
        "tests": {"unit": f"agents/tests/test_{short}.py", "integration": "backend/tests/test_agents_api.py (runs through the API, persistence and approval flow)"},
        "evaluation": {"cases": load_cases(spec),
                       "criteria": "A case passes when every check passes. Ship only if the pass rate does not regress versus the last release; review every failing case manually."},
        "deployment": "Agents run inside the FastAPI backend (modular monolith) via POST /api/v1/agents/{slug}/runs. "
                      "Provider credentials live in server-side environment/secrets only. For long or bursty workloads, move runs to a "
                      "worker (SQS/ECS) and stream status to the client; the AgentSpec contract stays the same.",
        "observability": "Every run records a trace id and spans (step / llm / tool) with token usage and latency, stored on the agent_runs row "
                         "and shown in the run viewer. If opentelemetry-api is installed, spans are also emitted to your OTel collector "
                         "(Langfuse/LangSmith can ingest OTel). Debug by replaying a stored run input with the mock provider first.",
    })
    return bp
