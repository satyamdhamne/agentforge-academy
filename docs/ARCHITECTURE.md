# Architecture

AgentForge Academy is a **modular monolith**: one FastAPI application with clear module boundaries, one PostgreSQL database, and one separate service only where isolation is a security requirement: the **sandbox runner** that executes learner code. Microservices would add operational cost without a scaling problem to justify them; module boundaries keep the option open.

## System context

```mermaid
flowchart LR
    U[Learner / author / admin<br/>browser] -->|HTTPS| W[Frontend<br/>React SPA on nginx]
    W -->|/api/v1 same origin<br/>session cookie + CSRF header| A[API<br/>FastAPI modular monolith]
    A --> DB[(PostgreSQL 16<br/>+ pgvector)]
    A -->|internal network<br/>X-Sandbox-Token| S[Sandbox runner<br/>no internet, read-only fs,<br/>no capabilities, rlimits]
    A -->|server-side keys only| P[Model providers<br/>mock / OpenAI-compatible / Anthropic]
    A -.->|optional| O[OpenTelemetry collector<br/>Langfuse / LangSmith via OTel]
    A -->|SMTP| M[Email]
```

| Component | Responsibility | Key technology |
|---|---|---|
| `frontend/` | SPA: catalog, lessons, lab, challenges, agent library, admin CMS | React 19, TypeScript, Vite, Tailwind 4, Radix (shadcn-style), TanStack Query, Monaco, Mermaid, Recharts |
| `backend/` | API, auth, content, grading orchestration, agent runs, analytics | FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, psycopg 3, Argon2id |
| `agents/` | Provider adapters, agent runtime (budgets, tracing), 10 reference agents, 100-entry catalog, eval harness | Plain Python, Pydantic, httpx, jsonschema |
| `sandbox/` | Runs untrusted Python / JavaScript / SQLite with limits; test harnesses | FastAPI, subprocess + rlimits, container hardening |
| PostgreSQL | System of record; JSONB for versioned content and traces | PostgreSQL 16 (pgvector image ready for Phase 4) |

## Backend module map

```
app/
├── core/       config (env-only, production guards) · db · errors (one envelope) · middleware · ratelimit · security
├── models/     identity · learning · agents · platform (workflows, prompts, evals, billing, analytics, audit)
├── modules/    auth · learning · challenges · codelab · agents · admin · misc · prompts · rag · evals · builder · career   ← routers, thin
├── services/   sandbox client · achievements · common (audit, events, entitlements, email, pagination)
│               llm (provider choice per plan, quotas, cost) · assertions · templating
│               rag/ (chunking, embeddings, retrieval: pgvector or Python cosine, BM25, RRF, rerank; pipeline, evaluation)
│               builder/ (node registry and validation, allowlisted tools, executor with budgets and approvals)
│               interview_scoring (transparent rubric; optional model grading cross-checked by the rubric)
└── seed/       loader + YAML/Markdown content
```

Modules talk to each other through services and models, never through HTTP. Every response error uses `{"error": {"code", "message", "details", "trace_id"}}`, and every request gets a trace id (honouring a safe `X-Request-Id`) that appears in logs, audit rows and agent runs.

## Key flows

### Sign-in and authenticated requests

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as API
    participant D as PostgreSQL
    B->>A: GET /auth/csrf
    A-->>B: Set-Cookie af_csrf (readable), {csrf_token}
    B->>A: POST /auth/login {email, password}<br/>X-CSRF-Token = af_csrf
    A->>A: CSRF double-submit + Origin check, rate limit (IP + account)
    A->>D: user by email; Argon2id verify (constant-time dummy hash if absent)
    A->>D: INSERT sessions (sha256(token), expires_at)
    A-->>B: Set-Cookie af_session (HttpOnly, SameSite=Lax, Secure in prod)
    B->>A: GET /me/dashboard (cookie)
    A->>D: session by token hash → user → plan (subscriptions)
```

Sessions are server-side, so sign-out, "sign out everywhere" and password reset revoke them immediately. Tokens for email verification and reset are single-use, hashed, and expire (48 h / 30 min).

### Grading a code challenge

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as API (challenges)
    participant S as Sandbox runner
    participant D as PostgreSQL
    B->>A: POST /challenges/{slug}/attempts {code}<br/>Idempotency-Key
    A->>A: auth, plan/tier check, rate limits,<br/>idempotency, duplicate-submission hash, cooldown
    A->>S: POST /v1/run {language, code, tests (incl. hidden)}
    S->>S: fresh temp dir, harness reads nonce + spec from stdin,<br/>runs code under CPU/memory/process/time limits
    S-->>A: {status, stdout, stderr, tests:{results}}
    A->>A: score, strip hidden test inputs/outputs,<br/>points (first success only, hint penalty)
    A->>D: challenge_attempts, usage_events, achievements
    A-->>B: verdict (+ explanation & solution if passed)
```

If no sandbox is configured, the attempt is stored as `not_graded` with zero points and the UI says why. The API process never executes learner code.

### Running a reference agent

```mermaid
flowchart TD
    R[POST /agents/slug/runs] --> V{plan tier,<br/>daily quota,<br/>rate limit}
    V --> P[Provider: mock for Free plan,<br/>server-configured for paid plans]
    P --> X[run_agent in worker thread<br/>with wall-clock timeout]
    X --> I[Pydantic input validation]
    I --> L[Agent logic: deterministic steps,<br/>model calls, allowlisted tools]
    L -->|every step| T[Tracer spans: step / llm / tool<br/>tokens, latency, errors]
    L --> B{Budget: model calls,<br/>tokens, seconds}
    L --> G[Guardrails]
    G -->|side effects proposed| AP[status = awaiting_approval<br/>pending_actions]
    G -->|no side effects| OK[status = succeeded]
    AP --> H[Human approves or rejects<br/>POST /agents/runs/id/decision → audit log]
    OK --> DB[(agent_runs: input, output,<br/>trace, tokens, cost, latency)]
    H --> DB
```

### Content publishing

Lessons are immutable `lesson_versions`. Authors save drafts (validated for all required sections), submit for review, and a **different** reviewer publishes; the previous version is archived and the lesson points to the new one. Every transition is audit-logged. The seed loader uses the same model: changed repository content becomes a new published version, never an in-place edit.

## Agent runtime design

- **Provider protocol** (`agents/core/llm.py`): `complete(CompletionRequest) -> Completion`, with `MockProvider` (deterministic, per-task responders), `OpenAICompatibleProvider` (OpenAI, Azure-compatible gateways, Ollama, vLLM) and `AnthropicProvider`. Structured output uses JSON extraction + Pydantic validation with one repair retry.
- **Budgets**: max model calls, total tokens and seconds per run; exceeding any stops the run as `failed` with the reason.
- **Tools**: registered with JSON schemas, validated arguments, and a `side_effect` flag. Side-effect tools are never executed by the agent; they are returned as `pending_actions` for human approval.
- **Untrusted data**: retrieved documents, diffs, logs and tool outputs are fenced as data in prompts; guardrails re-check outputs (for example, dropping review comments on lines not in the diff, or citations to passages that weren't retrieved).
- **Self-documenting**: the agent detail page reads prompts, tool schemas, input schema, folder structure and source files from the code (`registry.py`), so documentation can't drift from what runs.

## Database schema

41 tables, UUID primary keys, explicit foreign keys with `ON DELETE` behaviour, check constraints for enums, unique constraints for natural keys, and indexes for every hot query. JSONB stores versioned content, specs, traces and analytics properties.

```mermaid
erDiagram
    users ||--|| profiles : has
    users ||--o{ user_roles : has
    roles ||--o{ user_roles : grants
    users ||--o{ sessions : "signs in"
    users ||--o{ auth_tokens : "verify / reset"
    organizations ||--o{ users : "tenant (Team plan)"
    users ||--o{ subscriptions : plan
    entitlements }o--|| subscriptions : "limits by plan"

    learning_tracks ||--o{ courses : contains
    courses ||--o{ modules : contains
    modules ||--o{ lessons : contains
    lessons ||--o{ lesson_versions : "immutable versions"
    lessons ||--o| assessments : quiz
    assessments ||--o{ questions : has
    lessons ||--o{ exercises : "lesson exercises"
    users ||--o{ enrollments : enrolls
    users ||--o{ progress : tracks
    users ||--o{ challenge_attempts : submits
    exercises ||--o{ challenge_attempts : graded
    exercises ||--o{ hint_reveals : hints

    agents ||--o{ agent_versions : versions
    agent_versions ||--o{ agent_files : source
    agents ||--o{ agent_runs : runs
    users ||--o{ agent_runs : owns

    achievements ||--o{ user_achievements : awarded
    users ||--o{ usage_events : analytics
    users ||--o{ audit_logs : actor
```

| Area | Tables |
|---|---|
| Identity & access | `users`, `profiles`, `roles`, `user_roles`, `sessions`, `auth_tokens`, `organizations`, `credential_refs` |
| Learning | `learning_tracks`, `courses`, `modules`, `lessons`, `lesson_versions`, `enrollments`, `progress`, `assessments`, `questions` |
| Challenges | `exercises` (lesson exercises and standalone challenges; grading spec server-only), `challenge_attempts`, `hint_reveals` |
| Agents | `agents`, `agent_versions` (blueprint, example runs, eval report), `agent_files`, `agent_runs` (trace, tokens, cost, approvals) |
| Phase 4–5 (schema ready) | `workflows`, `workflow_nodes`, `workflow_edges`, `prompt_templates`, `prompt_versions`, `evaluations`, `evaluation_cases` |
| Engagement | `achievements`, `user_achievements`, `projects`, `portfolios`, `portfolio_entries`, `announcements` |
| Billing | `subscriptions` (provider fields null until a payment provider exists), `entitlements` |
| Operations | `usage_events` (allowlisted, non-personal properties), `audit_logs` |

Secrets never live in ordinary rows: `credential_refs` stores a *reference* (for example a Secrets Manager ARN) and the last four characters only, and workflow node configs may reference credentials by id only.

Migrations live in `backend/alembic/versions`; CI runs `alembic check` to fail if models and migrations diverge.

## API

Versioned REST under `/api/v1`, documented at `/api/v1/docs` (OpenAPI 3.1). Lists are paginated (`page`, `page_size`) and filterable; unsafe requests need the CSRF header; `POST /challenges/{slug}/attempts` honours `Idempotency-Key`.

| Area | Endpoints |
|---|---|
| Auth | `GET /auth/csrf` · `POST /auth/register` · `POST /auth/login` · `POST /auth/logout` · `POST /auth/logout-all` · `GET /auth/me` · `POST /auth/verify-email` · `POST /auth/resend-verification` · `POST /auth/password-reset/request` · `POST /auth/password-reset/confirm` |
| Profile | `GET, PATCH /me/profile` · `GET /me/dashboard` · `GET /me/progress` |
| Catalog & lessons | `GET /tracks` · `GET /tracks/{slug}` · `POST /tracks/{slug}/enroll` · `GET /lessons/{slug}` · `POST /lessons/{slug}/quiz` · `POST /lessons/{slug}/progress` · `GET /achievements` · `GET /projects` · `GET /plans` · `GET /announcements` |
| Challenges | `GET /challenges` · `GET /challenges/daily` · `GET /challenges/{slug}` · `POST /challenges/{slug}/hints/{index}` · `POST, GET /challenges/{slug}/attempts` |
| Code lab | `GET /sandbox/status` · `POST /sandbox/run` |
| Agents | `GET /agents` · `GET /agents/{slug}` · `GET /agents/{slug}/files/{path}` · `POST /agents/{slug}/runs` · `GET /agents/runs/mine` · `GET /agents/runs/{id}` · `POST /agents/runs/{id}/decision` |
| Prompt lab | `GET /prompts/templates` · `GET /prompts/templates/{slug}` · `POST /prompts/templates/{slug}/fork` · `POST /prompts/templates/{slug}/versions` · `PUT /prompts/templates/{slug}/test-cases` · `POST /prompts/run` · `POST /prompts/compare` |
| RAG lab | `GET /rag/options` · `GET, POST /rag/datasets` · `GET /rag/datasets/{key}` · `POST /rag/datasets/{key}/documents` · `DELETE /rag/datasets/{key}/documents/{id}` · `POST /rag/datasets/{key}/chunk-preview` · `POST /rag/query` · `POST /rag/evaluate` |
| Evaluations & models | `GET /evaluations` · `GET /evaluations/{id}` · `GET /evaluations/{a}/compare/{b}` · `POST /agents/{slug}/evaluate` · `GET /llm-lab/catalog` · `GET /llm-lab/providers` |
| Agent Builder | `GET /builder/node-types` · `GET /builder/templates` · `GET, POST /builder/workflows` · `GET, PUT, DELETE /builder/workflows/{id}` · `POST /builder/validate` · `POST, GET /builder/workflows/{id}/runs` · `GET /builder/runs/{id}` · `POST /builder/runs/{id}/decision` · `POST /builder/runs/{id}/cancel` |
| Career | `GET /interviews/tracks` · `GET /interviews/questions` · `POST, GET /interviews/sessions` · `GET /interviews/sessions/{id}` · `POST /interviews/sessions/{id}/answers` · `POST /interviews/sessions/{id}/finish` · `GET, PATCH /me/portfolio` · `POST /me/portfolio/entries` · `PUT, DELETE /me/portfolio/entries/{id}` · `POST /me/portfolio/entries/{id}/submit` · `GET /portfolios/{slug}` · `GET /admin/portfolio-reviews` · `POST /admin/portfolio-entries/{id}/review` · `GET /mentor/status` · `GET, POST /mentor/assessment` · `GET /mentor/recommendations` · `POST /mentor/ask` · `GET, DELETE /mentor/history` |
| Admin | `GET /admin/lessons` · `GET /admin/lessons/{id}` · `POST /admin/lessons/{id}/versions` · `POST /admin/lesson-versions/{id}/submit\|publish\|reject` · `GET /admin/reviews` · `POST /admin/attempts/{id}/review` · `GET /admin/users` · `PATCH /admin/users/{id}/plan` · `GET /admin/audit-logs` · `GET /admin/analytics` · `POST /admin/announcements` |
| Health | `GET /healthz` (liveness) · `GET /readyz` (database) |

Agent runs are synchronous with a server-side timeout (typical runs finish in milliseconds with the mock provider and seconds with real models). Streaming via SSE is deferred until runs are moved to a worker queue (see the backlog), where it is actually needed.

## Frontend structure

```
src/
├── lib/          api client (CSRF, error envelope), auth context, types, theme
├── components/   ui primitives (shadcn-style on Radix), layout (sidebar, ⌘K palette), CodeRunner,
│                 Monaco (bundled locally, no CDN), TraceView, Mermaid, Markdown, CodeBlock
└── pages/        Landing, auth, Dashboard, Paths, Lesson, CodeLab, Challenges, ChallengeWorkspace,
                  Agents, AgentDetail, Projects, Progress, Settings, Pricing, Planned, admin/*,
                  labs/{PromptLab, RagLab, ModelsLab}, Evaluations, builder/{BuilderHome, BuilderStudio (React Flow)},
                  Interviews, Portfolio (+ public /u/:slug), Mentor
```

Routes are code-split; Monaco and Mermaid load only on pages that need them. The production CSP forbids inline and third-party scripts.

## Observability

- Structured JSON logs with `trace_id`, path, method, status and duration for every request.
- `X-Trace-Id` response header; error envelopes include it so users can quote it.
- Agent runs persist their spans; when `opentelemetry-api` is installed, spans are also emitted to your collector (Langfuse and LangSmith ingest OTel).
- `/healthz` and `/readyz` for orchestrators; admin analytics for activation, retention, completion, agent engagement, conversion and inference cost.
