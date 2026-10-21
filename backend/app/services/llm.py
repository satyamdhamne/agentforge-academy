"""Model access for the labs, Agent Builder, interviews and mentor.

Free plan (or LLM_PROVIDER=mock): the deterministic prompt simulator. Paid plans: the server-configured provider.
Provider credentials stay in server configuration; nothing here is exposed to the browser.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentforge_agents.core import AnthropicProvider, LLMProvider, OpenAICompatibleProvider, SimulatedProvider

from ..core.config import get_settings
from ..core.errors import AppError
from ..models import UsageEvent, User
from .common import entitlement_limit, plan_for


@dataclass
class ProviderChoice:
    provider: LLMProvider
    mode: str  # "mock" | "live"
    label: str


def provider_for(db: Session, user: User | None, want_live: bool = True) -> ProviderChoice:
    s = get_settings()
    plan = plan_for(db, user)
    if not want_live or plan == "free" or s.llm_provider == "mock":
        why = "Free plan" if plan == "free" else ("server configured for mock" if s.llm_provider == "mock" else "simulation requested")
        return ProviderChoice(SimulatedProvider(), "mock", f"Prompt simulator ({why})")
    if s.llm_provider == "openai":
        return ProviderChoice(OpenAICompatibleProvider(s.openai_api_key, s.openai_model, s.openai_base_url), "live",
                              f"OpenAI-compatible: {s.openai_model}")
    return ProviderChoice(AnthropicProvider(s.anthropic_api_key, s.anthropic_model), "live", f"Anthropic: {s.anthropic_model}")


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal | None:
    """Estimated cost from MODEL_PRICES; zero for the mock/simulator; None when the price is unknown."""
    if model.startswith(("mock", "simulator")):
        return Decimal(0)
    price = get_settings().model_prices.get(model)
    if not price:
        return None
    return Decimal(str(round(input_tokens / 1e6 * price.get("input_per_mtok", 0) + output_tokens / 1e6 * price.get("output_per_mtok", 0), 6)))


def groups_for(user: User | None) -> list[str]:
    """Document-permission groups derive from roles on the server, never from request input."""
    groups = ["everyone"]
    if user is None:
        return groups
    if user.role_names & {"admin", "author", "reviewer"}:
        groups.append("engineering")
    if "admin" in user.role_names:
        groups += ["hr", "people-managers"]
    return groups


def enforce_quota(db: Session, user: User, feature_key: str, event_type: str, cost: int = 1) -> None:
    """Daily allowance per plan from the entitlements table. Raises 429 when exhausted."""
    plan = plan_for(db, user)
    limit = entitlement_limit(db, plan, feature_key)
    if limit is None:
        return
    since = datetime.now(UTC) - timedelta(days=1)
    used = db.scalar(select(func.count()).select_from(UsageEvent).where(
        UsageEvent.user_id == user.id, UsageEvent.event_type == event_type, UsageEvent.created_at >= since)) or 0
    if used + cost > limit:
        raise AppError(f"Daily limit reached for the {plan} plan ({limit} per day). It resets on a rolling 24-hour window.",
                       code="quota_exceeded", status_code=429, details={"limit": limit, "used": used})
