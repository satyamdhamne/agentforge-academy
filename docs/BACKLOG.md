# MVP scope and prioritized backlog

Priorities: **P0** blocks launch, **P1** needed soon after launch, **P2** valuable, scheduled by phase. Status reflects this repository.

## Done (Phases 1–3)

| ID | Item | Phase |
|---|---|---|
| F-01 | PostgreSQL schema (41 tables), Alembic migration, `alembic check` in CI | 1 |
| F-02 | Session auth: register, login, logout, logout everywhere, Argon2id, CSRF double-submit + Origin check, rate limits | 1 |
| F-03 | Email verification and password reset (single-use hashed tokens, no account enumeration) | 1 |
| F-04 | Roles (learner, author, reviewer, admin) and plan entitlements (free, pro, team) | 1 |
| F-05 | Catalog API and UI: 16 tracks, courses, modules, 60 outlined lessons | 1 |
| F-06 | Dashboard: continue lesson, stats, streak, 7-day activity, daily challenge, recommendations | 1 |
| F-07 | Idempotent seed loader with versioned content | 1 |
| F-08 | Backend integration tests on PostgreSQL; agent, sandbox and frontend tests; Playwright e2e | 1 |
| L-01 | Lesson player with all 15 lesson parts, outline navigation, prev/next | 2 |
| L-02 | 10 complete lessons across JS, Python, FastAPI, SQL, HTTP, GenAI, RAG and agentic AI | 2 |
| L-03 | Quizzes gating completion; achievements from verifiable records | 2 |
| L-04 | Sandbox runner (Python, JavaScript, SQLite) with container hardening; code lab UI | 2 |
| L-05 | CI verification that every runnable example prints its documented output | 2 |
| C-01 | Challenge engine: code (public + hidden tests), multiple choice, manual review with rubric | 2 |
| C-02 | Daily challenge, weekly project, timed interview challenges, hints with penalties | 2 |
| C-03 | Anti-gaming: first-success points, duplicate detection, cooldown, hourly cap, idempotency keys | 2 |
| C-04 | 25 standalone challenges across 9 categories; solutions pass and starters fail in CI | 2 |
| C-05 | Review queue for reviewers, with self-review prevention | 2 |
| A-01 | Provider-agnostic LLM adapter: mock, OpenAI-compatible (incl. Ollama), Anthropic | 3 |
| A-02 | Agent runtime: budgets, tracing (OTel-compatible), side-effect approval | 3 |
| A-03 | 100 blueprints with honest verdicts, architectures, risks, challenges, interview questions | 3 |
| A-04 | 10 reference agents with tests, eval datasets (45 cases, 100% pass with mock) | 3 |
| A-05 | Agent detail pages generated from code: prompts, tool schemas, source, evals | 3 |
| A-06 | Run agents from the UI with trace waterfall, metrics and approve/reject | 3 |
| M-01 | Admin CMS: versioned lessons, four-eyes publishing, audit log, announcements | 2 |
| M-02 | Admin analytics: activation, WAL, retention, completions, agent engagement, conversion, cost | 2 |
| O-01 | Docker Compose stack, GitHub Actions CI, deployment and security docs | 1 |

## Next: launch hardening (P0)

| ID | Item | Notes |
|---|---|---|
| H-01 | Move the rate limiter to Redis | Current limiter is per-process; required before running more than one API replica |
| H-02 | Run the sandbox under gVisor (`runsc`) or Firecracker | Container hardening is in place; a userspace kernel adds defence in depth for untrusted code |
| H-03 | SMTP / SES configuration and email templates | Production refuses the console mail backend |
| H-04 | Account deletion and data export endpoints | Privacy requirement before public launch |
| H-05 | Error tracking (Sentry or equivalent) wired to trace ids | |
| H-06 | Backups and restore drill for RDS | See DEPLOYMENT.md |

## Phase 4: prompt lab, RAG lab, evaluations (P1)

| ID | Item |
|---|---|
| P4-01 | Prompt templates with versions, variables and params (tables exist) |
| P4-02 | Side-by-side model comparison and A/B runs with rubric scoring |
| P4-03 | Prompt-injection exercises with automatic attack suites |
| P4-04 | RAG pipeline on pgvector: upload, parse, clean, chunk, embed, index, retrieve, rerank, generate, cite, evaluate |
| P4-05 | Tunable chunk size, overlap, top-k, embedding model, search strategy (vector, keyword, hybrid with RRF) |
| P4-06 | Retrieval metrics (recall@k, MRR), faithfulness spot checks, latency and cost per query |
| P4-07 | Tenant isolation and document-level permissions in retrieval queries |
| P4-08 | Evaluation runs stored in `evaluations` / `evaluation_cases` with regression comparison |
| P4-09 | 15 more complete lessons (RAG, prompting, LLM engineering, AI security) |

## Phase 5: Agent Builder Studio (P1)

| ID | Item |
|---|---|
| P5-01 | React Flow canvas with input, LLM, prompt, tool, retrieval, condition, memory, approval, evaluation and output nodes |
| P5-02 | Graph validation (DAG with bounded loops, typed ports, unknown-node rejection) shared by client and server |
| P5-03 | Allowlisted node registry; credentials referenced by `credential_refs` only |
| P5-04 | Mock execution in the browser, then server-side execution in a worker with budgets, timeouts and cancellation |
| P5-05 | Execution traces, state inspection per node, approval gates for side effects, audit logs |
| P5-06 | Run streaming over SSE once execution moves to a worker queue (SQS + ECS) |

## Phase 6: interview arena, portfolio, personalization (P2)

| ID | Item |
|---|---|
| P6-01 | Question banks for 19 interview tracks (concise answer, explanation, example, follow-ups, mistakes) |
| P6-02 | Mock interviews scored on accuracy, reasoning, trade-offs and communication with transparent rubrics |
| P6-03 | Portfolio entries with repo, diagrams, tests, evaluations and deployment URL; verification workflow; public pages |
| P6-04 | Opt-in AI mentor grounded in course content with solution-withholding policy and privacy controls |
| P6-05 | Adaptive difficulty from attempt history |

## Later (P2)

Team dashboards and shared paths · payments integration behind the subscriptions model · community discussions · cloud deployment lab · system design studio with diagram review · organization use-case library · 40 more reference agents (target: 50 runnable) · localisation.
