BLUEPRINT = {
    "category": "Research & Knowledge",
    "level": "intermediate",
    "build_hours": 8,
    "tags": ["rag", "retrieval", "citations", "permissions", "pdf"],
    "summary": "Permission-aware document Q&A: section-aware chunking, two-stage retrieval, grounded answers with verified citations and a refusal path.",
    "problem": "Employees can't find answers buried in policy PDFs and runbooks; generic chatbots invent answers and ignore who is allowed to see what.",
    "business_value": "Self-serve answers with sources people can verify, without leaking restricted documents.",
    "inputs": ["Question", "Optional documents (text or base64 PDF) with allowed groups; defaults to a seeded corpus",
               "Retrieval settings: top_k, chunk size, overlap, minimum score"],
    "outputs": ["Answer with [n] citations", "Citation details (document, section, score, snippet)",
                "All retrieved passages with similarity/coverage/score", "Answerable flag, confidence, ungrounded flag"],
    "prerequisites": ["Embeddings and cosine similarity", "Chunking trade-offs", "Access control basics"],
    "verdict": "rag",
    "verdict_reasoning": "This is a retrieval pipeline, not an agent: retrieve once, generate once. Agentic RAG (query rewriting, "
                         "multi-hop search) is only worth its latency when single-shot retrieval measurably fails on your eval set.",
    "architecture_mermaid": """flowchart LR
    D[Documents / PDFs] --> X[extract text]
    X --> F{permission filter}
    U[User groups] --> F
    F --> C[section-aware chunking]
    C --> I[(index: TF-IDF / pgvector)]
    Q[Question] --> R[retrieve top 3k]
    I --> R
    R --> RR[rerank: 0.7·cosine + 0.3·coverage]
    RR --> T{score ≥ min?}
    T -->|no| N[refuse]
    T -->|yes| G[LLM: grounded answer]
    G --> V{citation check}
    V --> A[Answer + sources]""",
    "data_flow": [
        "Documents are filtered by the caller's groups BEFORE chunking - restricted text never enters retrieval or the prompt.",
        "Chunks respect markdown sections and sentence boundaries; overlap is carried between neighbouring chunks.",
        "Retrieval recalls 3×top_k candidates by cosine similarity, then reranks with query-term coverage.",
        "Below the score threshold the system refuses instead of guessing.",
        "Citations in the answer are checked against retrieved passage numbers; answers with none are flagged ungrounded.",
    ],
    "framework": {"choice": "Plain Python (+ pgvector in production)", "reasoning": "LlamaIndex/LangChain retrievers are fine, but the "
                  "pipeline is short and the interesting decisions (chunking, filtering, thresholds) should be explicit."},
    "model_selection": {"recommended": "Mid-size model that follows citation instructions; embedding model chosen by retrieval eval.",
                        "reasoning": "Retrieval quality dominates answer quality. Spend effort on chunking and reranking first.",
                        "alternatives": ["Cross-encoder reranker (e.g. a MiniLM cross-encoder)", "Extractive answering (the mock) for high-precision use cases"]},
    "state_memory": "Index is the state. Production: incremental re-indexing on document change, per-tenant index partitioning, conversation memory only if follow-up questions are needed.",
    "security": [
        {"threat": "Users retrieving documents they cannot access", "mitigation": "Filter by permissions before retrieval (metadata filter in the vector query), never by post-filtering answers."},
        {"threat": "Indirect prompt injection inside documents", "mitigation": "Passages fenced as untrusted; no tools available to the model; citations verified."},
        {"threat": "Malicious or oversized PDFs", "mitigation": "Magic-byte check, size and page limits, parse in a worker with timeouts."},
        {"threat": "Cross-tenant leakage via shared index", "mitigation": "Tenant id in every chunk's metadata and in every query filter; separate indexes for strict isolation."},
    ],
    "cost_latency": "Embedding cost is one-time per chunk; query cost ≈ top_k × chunk tokens + question + ~150 prompt tokens. With top_k=4 and 120-word chunks, ~900 input tokens per question.",
    "failure_modes": [
        {"mode": "Answer spread across chunks lost by chunking", "mitigation": "Tune chunk size/overlap on the eval set; section-aware chunking."},
        {"mode": "Lexical mismatch (synonyms)", "mitigation": "Dense embeddings or hybrid search; query rewriting."},
        {"mode": "Confident wrong answers", "mitigation": "Score threshold refusal + citation verification + eval on unanswerable questions."},
    ],
    "improvements": ["pgvector + hybrid BM25", "Cross-encoder reranking", "Retrieval metrics (recall@k, MRR) dashboard", "Incremental indexing"],
    "production_checklist": ["Permission filter in the vector query", "Tenant isolation", "File validation", "Eval set incl. unanswerable questions", "Source freshness metadata"],
    "challenges": [
        {"level": "beginner", "title": "Tune chunking", "description": "Find chunk/overlap settings that answer all eval questions with top_k=2."},
        {"level": "intermediate", "title": "Hybrid search", "description": "Add a BM25 scorer and fuse rankings with reciprocal rank fusion; compare recall@4."},
        {"level": "advanced", "title": "pgvector", "description": "Store chunk embeddings in pgvector with a group filter and prove a restricted document can never be retrieved."},
    ],
    "interview_questions": [
        {"q": "Where should document permissions be enforced in RAG?", "a": "At retrieval time as a metadata filter, so unauthorised text never reaches the model."},
        {"q": "How do you evaluate a RAG system?", "a": "Separately: retrieval (recall@k, MRR against labelled passages) and generation (faithfulness, citation accuracy, refusal on unanswerable questions)."},
        {"q": "When does chunk overlap help?", "a": "When answers span chunk boundaries; too much overlap wastes context and duplicates results."},
    ],
}
