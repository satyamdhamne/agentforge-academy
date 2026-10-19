from collections import Counter

from agentforge_agents.catalog import CATEGORIES, all_entries


def test_catalog_has_100_unique_agents_in_12_categories():
    entries = all_entries()
    assert len(entries) == 100
    assert sorted(e["number"] for e in entries) == list(range(1, 101))
    assert len({e["slug"] for e in entries}) == 100
    assert set(e["category"] for e in entries) == set(CATEGORIES)


def test_honest_verdicts_include_non_agent_options():
    verdicts = Counter(e["verdict"] for e in all_entries())
    assert verdicts["deterministic"] >= 10 and verdicts["workflow"] >= 30
    assert verdicts["agent"] < 30  # most tasks do not need an autonomous agent


def test_implemented_entries_are_flagged():
    assert sum(e["has_reference_impl"] for e in all_entries()) == 10
