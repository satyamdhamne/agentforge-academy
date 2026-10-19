# AgentForge Academy

**Learn to build AI systems that actually work.** An interactive engineering lab for software engineering, cloud, generative AI, RAG and agentic AI: structured learning paths, code you can run in a sandbox, graded challenges, and a library of 100 agent blueprints, ten of which have complete, tested reference implementations you can run, trace and evaluate.

This repository contains **Phases 1–3** of the roadmap:

| Phase | Scope | Status |
|---|---|---|
| 1 | Foundation: auth, learning catalog, dashboard, database, seed lessons, tests | Done |
| 2 | Interactive learning and the challenge engine | Done |
| 3 | Agent library: 100 blueprints and 10 fully implemented agents | Done |
| 4 | Prompt lab, RAG lab, evaluation tools | Planned (schema in place) |
| 5 | Agent Builder Studio with safe execution | Planned (schema in place) |
| 6 | Interview arena, portfolio, personalization | Planned |

Everything runs **without paid API keys**: model calls go through a provider-agnostic adapter with a deterministic mock provider by default. OpenAI-compatible endpoints (including Ollama) and Anthropic plug in through environment variables.

---

## Quick start (Docker)

Requirements: Docker with Compose v2.24+.

```bash
git clone https://github.com/satyamdhamne/agentforge-academy.git
cd agentforge-academy
cp .env.example .env          # optional - every value has a development default
docker compose up --build
```

When the containers are healthy:

| What | URL |
|---|---|
| App | http://localhost:8080 |
| API docs (OpenAPI) | http://localhost:8000/api/v1/docs |
| PostgreSQL | localhost:5432 (agentforge / agentforge) |

On first start the backend applies migrations and seeds the curriculum, challenges, the agent catalog (running every reference agent's examples and evaluation set) and three development accounts:

| Role | Email | Password |
|---|---|---|
| Learner (Free plan) | `learner@example.com` | `ChangeMe-Learner-123!` |
| Author (Pro plan) | `author@example.com` | `ChangeMe-Learner-123!` |
| Admin + reviewer (Team plan) | `admin@example.com` | `ChangeMe-Admin-123!` |

Email verification and password-reset links are printed to the backend log in development (`docker compose logs -f backend`).

## Local development (without Docker for the app)

Requirements: Python 3.12+, Node 22, PostgreSQL 16, and `node` on your PATH (the sandbox runs JavaScript).

```bash
# 1. Database
createuser -s agentforge 2>/dev/null; psql -c "ALTER USER agentforge PASSWORD 'agentforge'"
createdb -O agentforge agentforge          # or: docker compose up -d db

# 2. Python packages (agents, API, sandbox runner) and the frontend
python -m venv .venv && source .venv/bin/activate
make install

# 3. Migrate and seed
make seed

# 4. Run each in its own terminal
make dev-sandbox    # code runner on :8080 - dev only: outside Docker it has rlimits but no container isolation
make dev-api        # FastAPI on :8000 (hot reload)
make dev-web        # Vite on :5173, proxies /api to :8000
```

Open http://localhost:5173.

## Tests

```bash
make test             # everything below
make test-agents      # 96 unit tests for the 10 reference agents + eval harness
make test-sandbox     # sandbox executor: limits, timeouts, harness integrity
make test-backend     # 46 API integration tests on a real PostgreSQL (creates agentforge_test)
make test-frontend    # TypeScript check + Vitest/React Testing Library
make verify-content   # every runnable lesson example prints its documented output; every
                      # exercise solution passes its tests and every starter fails them
make e2e              # Playwright against a running stack (E2E_BASE_URL, default :8080)
python -m agentforge_agents eval all   # (in agents/) run every agent's evaluation dataset
```

CI (`.github/workflows/ci.yml`) runs lint, all suites, `alembic check` (migrations match models), the production build, and a Docker Compose + Playwright end-to-end job.

## What's in the box

- **16 learning tracks**, 60 outlined lessons and **10 complete lessons**. Every lesson has the same fifteen parts: explanation, why it matters, prerequisites, mental model, architecture diagram, annotated runnable code with expected output, real-world usage, common mistakes, debugging, performance and security, interview Q&A, a mini and an advanced challenge, and further reading with version notes. A quiz gates completion.
- **Challenge engine**: 35 challenges (25 standalone + 10 lesson exercises) across coding, debugging, architecture, prompting, RAG tuning, agent reliability, security, cloud and timed interviews, plus a weekly project. Code is graded in the sandbox against public and hidden tests; multiple choice discourages guessing; open-ended work goes to a human review queue with a published rubric. Points are awarded once, hints cost 20% each (floor 40%), identical resubmissions aren't re-graded, and attempts are rate-limited and idempotent.
- **Interactive coding lab**: Monaco editor running Python, JavaScript and SQL through an isolated runner. When no runner is configured, the UI says so and shows expected output instead of pretending to execute anything.
- **AI Agent Library**: 100 catalog entries across 12 categories, each with an honest verdict: deterministic code (15), workflow (60), retrieval pipeline (10) or agent (15). Ten reference implementations ship with prompts, tool JSON schemas, source, tests, an evaluation dataset, recorded runs with traces, security analysis, cost methodology and deployment notes. You can run them from the UI, inspect the span waterfall, and approve or reject side effects.
- **Admin CMS**: versioned lessons (draft → review → published, with four-eyes publishing), review queue, users and plans, audit log, announcements, and a privacy-conscious analytics dashboard.
- **Plans**: Free, Pro and Team are configuration (`entitlements` table), not code. Admins assign plans; a payment provider can be added later by writing `subscriptions` rows.

## Repository layout

```
agentforge-academy/
├── agents/                 # Reference agents package (provider adapters, runtime, tracing, 10 agents, 100-entry catalog, evals)
│   ├── agentforge_agents/
│   │   ├── core/           # LLM provider protocol (mock / OpenAI-compatible / Anthropic), runtime, budgets, tracer
│   │   ├── <agent>/        # agent.py, tools.py, mock.py, blueprint.py, evals/cases.jsonl
│   │   ├── catalog.py      # the 100 blueprints
│   │   └── registry.py     # builds detail pages from the code itself (prompts, schemas, files)
│   └── tests/
├── backend/                # FastAPI modular monolith
│   ├── app/
│   │   ├── core/           # config, DB, errors, middleware (trace ids, CSRF, headers), rate limiting, security
│   │   ├── models/         # SQLAlchemy models (41 tables)
│   │   ├── modules/        # auth, learning, challenges, codelab, agents, admin, misc (routers)
│   │   ├── services/       # sandbox client, achievements, audit, analytics events, entitlements
│   │   └── seed/           # idempotent loader + content (curriculum, lessons, challenges, platform)
│   ├── alembic/            # migrations
│   └── tests/              # integration tests (PostgreSQL)
├── sandbox/                # Isolated code runner service (Python / JavaScript / SQLite)
├── frontend/               # React + TypeScript + Vite + Tailwind
│   ├── src/{components,pages,lib}
│   └── e2e/                # Playwright
├── docs/                   # PRD, backlog, architecture, security, deployment, content guide
├── scripts/verify_content.py
├── docker-compose.yml
└── .github/workflows/ci.yml
```

## Documentation

- [Product requirements](docs/PRD.md)
- [MVP scope and prioritized backlog](docs/BACKLOG.md)
- [Architecture, data flows, database schema and API](docs/ARCHITECTURE.md)
- [Security checklist](docs/SECURITY.md)
- [Deployment guide (AWS)](docs/DEPLOYMENT.md)
- [Content authoring guide](docs/CONTENT.md)

## Configuration

All configuration is environment variables; see [.env.example](.env.example). Production (`ENV=production`) refuses to start with insecure settings: non-secure cookies, the console mail backend, a sandbox without a token, or default seed passwords.

To use a real model, set `LLM_PROVIDER=openai` (with `OPENAI_API_KEY`, `OPENAI_MODEL`, optional `OPENAI_BASE_URL`) or `LLM_PROVIDER=anthropic` (with `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`). Keys stay on the server. Free-plan users always get the mock provider; add `MODEL_PRICES` so cost estimates are accurate.
