import pytest

from agentforge_agents.core import MockProvider, run_agent
from agentforge_agents.pdf_knowledge import SPEC
from agentforge_agents.pdf_knowledge.tools import Document, chunk_document, load_seed_corpus


def test_seed_corpus_has_restricted_document():
    docs = {d.id: d for d in load_seed_corpus()}
    assert docs["compensation-bands-2026"].allowed_groups == ["hr", "people-managers"]


def test_chunking_respects_size_overlap_and_sections():
    doc = Document("d", "D", "# A\n\n" + " ".join(f"Sentence number {i} is here." for i in range(40)) + "\n\n# B\n\nOther section.")
    chunks = chunk_document(doc, chunk_words=40, overlap_words=10)
    assert all(len(c.text.split()) <= 45 for c in chunks)
    assert chunks[-1].section == "B"
    assert chunks[0].text.split(".")[-2] in chunks[1].text  # overlap carried forward
    with pytest.raises(ValueError):
        chunk_document(doc, 20, 20)


def test_restricted_text_never_reaches_the_model():
    prompts = []

    def responder(req):
        prompts.append(req.messages[-1].content)
        return {"answer": "x [1]", "citations": [1], "answerable": True}

    run_agent(SPEC, {"question": "paid leave days and salary band for E5", "min_score": 0.0},
              provider=MockProvider({"pdf_knowledge.answer": responder}))
    assert prompts and all("155,000" not in p for p in prompts)


def test_invalid_citations_are_removed_and_flagged():
    provider = MockProvider({"pdf_knowledge.answer": lambda r: {"answer": "Twenty days [9].", "citations": [9], "answerable": True, "confidence": "high"}})
    out = run_agent(SPEC, {"question": "How many PTO days?"}, provider=provider).output
    assert out["citations"] == [] and out["ungrounded"] is True and out["confidence"] == "low"


def test_custom_documents():
    out = run_agent(SPEC, {"question": "What is the refund window?", "documents": [
        {"id": "faq", "title": "FAQ", "text": "# Refunds\n\nRefunds are available within 14 days of purchase."}]}).output
    assert "14 days" in out["answer"]
