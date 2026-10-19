# Product requirements: AgentForge Academy

## Problem

Engineers who want to build with AI face two bad options. Course catalogs teach concepts through videos and toy notebooks but never make learners run, test, evaluate or secure what they build. Framework documentation shows APIs but not engineering judgement: when an agent is the wrong tool, how to evaluate a RAG pipeline, how to stop a tool-calling model from doing damage. The result is demos that don't survive production.

## Vision

The most practical place to learn software engineering, cloud and AI engineering: an interactive laboratory where every concept comes with code that runs, a challenge that is graded, and a production concern that is made explicit. Learners progress from first API to production-grade AI systems by building, evaluating and deploying, not by watching.

## Target users

| Segment | Primary job | What success looks like |
|---|---|---|
| Absolute beginners | Learn to code with real feedback | Finish the CS fundamentals and Python tracks; pass beginner challenges |
| Frontend → full stack | Learn APIs, databases, deployment | Ship the URL-shortener project with tests and Docker |
| Backend → AI engineering | Learn LLMs, RAG, agents, evaluation | Run and extend reference agents; build the docs RAG project with an eval set |
| Full stack → GenAI / agentic | Learn when and how to use agents safely | Explain verdicts (workflow vs agent), add approval gates, measure cost |
| Cloud & DevOps | Deploy and operate AI systems | Complete the deployment weekly project and AWS track |
| Engineers implementing AI at work | Patterns that survive security review | Use blueprints with threat models, cost methodology, production checklists |
| Interview candidates | Practise under realistic conditions | Timed challenges, interview Q&A in every lesson, rubric-scored answers |
| Teams | Shared upskilling with admin controls | Team plan, shared paths, review workflows (Team dashboards in a later phase) |

## Principles

1. **Runnable over readable.** If a lesson shows code, the learner can run it, and the expected output is verified in CI.
2. **Honest engineering.** Every agent blueprint states whether an agent is appropriate. Mock execution is labelled as mock; unavailable sandboxes are labelled as unavailable.
3. **Verifiable progress.** Points and badges come only from server-side rules over records: a passed quiz, tests passed, a reviewed submission.
4. **Safe by construction.** Learner code never runs in the API process; provider keys never reach the browser; side effects need human approval.
5. **No paid dependency to start.** The full product runs with mock providers and no API keys.

## Scope by phase

| Phase | Deliverables |
|---|---|
| **1 Foundation** | Auth (sessions, CSRF, verification, reset, roles), catalog (16 tracks), dashboard, PostgreSQL schema and migrations, seed lessons, tests |
| **2 Interactive learning** | Lesson player (15 parts), runnable examples, quizzes gating completion, sandboxed code lab, challenge engine (code / MCQ / manual review, daily, weekly, timed, hints, anti-gaming), achievements, admin CMS with versioning and review |
| **3 Agent library** | 100 blueprints with verdicts, 10 complete reference agents with tests, eval datasets, traces, approvals and detail pages |
| 4 Labs | Prompt lab (versioning, A/B, rubrics), RAG lab on pgvector (pipeline visualisation, retrieval metrics, permissions), evaluation tools |
| 5 Agent Builder | React Flow canvas, validated graphs, allowlisted node registry, server-side execution with budgets, approvals, traces |
| 6 Career | Interview arena with rubric-scored mock interviews, public portfolios, opt-in AI mentor |

## Functional requirements (Phases 1–3)

**Learning engine.** Content hierarchy Track › Course › Module › Lesson, with exercises, quizzes, projects and assessments. Each lesson includes: simple explanation, why it matters, prerequisites, mental model, architecture illustration where applicable, annotated runnable code, expected output, real-world usage, common mistakes, debugging techniques, performance and security considerations, interview questions and answers, mini challenge, advanced challenge, further reading and version notes. Lessons are versioned; learners see the published version.

**Challenges.** Difficulty levels beginner–expert; categories coding, debugging, architecture, prompt, RAG, agent reliability, security, cloud, timed interview; a deterministic daily challenge; weekly projects; automated tests (public and hidden) where appropriate; optional hints with a point penalty; explanations and reference solutions unlocked after solving; manual review against a published rubric; protection against meaningless repeated submissions (points once, duplicate detection, cooldown, hourly cap, idempotency keys).

**Code execution.** Python, JavaScript and SQL in an isolated runner with CPU, memory, process, filesystem, network and time limits. Without a runner, examples are read-only and submissions are saved but not graded, with explicit labelling.

**Agent library.** Searchable, filterable catalog of 100 entries across 12 categories. Every entry: problem, verdict with reasoning, suggested tools, key risk and mitigation, reference architecture, three progressive challenges and interview questions. Implemented entries add business value, inputs/outputs, prerequisites, data flow, framework decision, model selection, prompt templates, tool JSON schemas, state and memory design, folder structure, full source, environment variables, install and run commands, example inputs and outputs, unit and integration tests, evaluation dataset with pass criteria, security threats, cost and latency methodology, deployment, observability, failure modes, improvements and a production checklist, plus live runs with traces and approval of side effects.

**Accounts and plans.** Free, Pro and Team plans enforced through entitlements (content tier, daily sandbox and agent-run quotas, real-model runs). No payment provider in core logic.

**Admin.** Lesson CMS (draft, review, published, archived; four-eyes publishing; audit), manual review queue, user plan management, audit log, announcements, analytics (activation, weekly active learners, retention, completions, agent engagement, conversion, inference cost).

## Non-functional requirements

| Area | Requirement |
|---|---|
| Security | OWASP ASVS L2-aligned auth; see [SECURITY.md](SECURITY.md) |
| Privacy | Minimal personal data; analytics events carry allowlisted, non-personal properties; mentor and public portfolio are opt-in |
| Accessibility | WCAG 2.2 AA target: keyboard navigation, visible focus, labelled controls, reduced-motion support, sufficient contrast in both themes |
| Performance | p95 API latency < 300 ms for catalog/lesson reads; code runs bounded at 5 s; heavy editor and diagram code lazy-loaded |
| Reliability | Health/readiness endpoints; idempotent seed and submissions; stateless API instances (sessions in the database) |
| Portability | Runs with `docker compose up`; no paid API keys required |

## Success metrics

| Metric | Definition | Initial target |
|---|---|---|
| Activation | % of new learners who complete a lesson (quiz passed) within 7 days | 40% |
| Weekly active learners | Distinct learners with any learning event in 7 days | Growth week over week |
| Week-1 retention | % of a signup cohort active in their second week | 30% |
| Challenge completion | Challenges passed per active learner per week | ≥ 2 |
| Agent engagement | % of active learners who run a reference agent | 25% |
| Project completion | Verified portfolio projects per month | Tracked from Phase 6 |
| Conversion | Free → paid | Tracked once payments exist |
| Inference cost | USD per active learner per month | Below plan margin; alert on regressions |

## Out of scope for Phases 1–3

Payments, team dashboards, community features, the Agent Builder, prompt and RAG labs, LLM/SLM fine-tuning labs, interview arena, public portfolios, the AI mentor, and streaming agent runs. The schema already includes their tables so later phases don't require disruptive migrations.

## Risks

| Risk | Mitigation |
|---|---|
| Sandbox escape or abuse | Separate container, no network, no credentials, read-only fs, rlimits, token auth, rate limits, quotas; upgrade path to gVisor/Firecracker |
| Content quality at scale | Required-section validation, versioning, four-eyes review, CI verification of examples and solutions |
| Inference cost | Mock provider on Free, per-plan quotas, budgets per run, cost tracking with alerts |
| Learners gaming points | Hidden tests, first-success-only points, hint penalties, duplicate detection, cooldowns, human review |
| Outdated AI content | Version notes per lesson, dated evaluation reports, quarterly content review |
