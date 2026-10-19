# Security checklist

Status legend: ✅ implemented and tested · 🟡 implemented, needs production configuration · ⏭ planned (see [BACKLOG.md](BACKLOG.md)).

## Threat model in one paragraph

The platform accepts **untrusted code** (challenge submissions, lab runs), **untrusted text** that reaches language models (agent inputs, documents, diffs, logs), and handles **accounts and plans**. The highest-impact risks are: learner code escaping its sandbox or reaching the network or cloud credentials; prompt injection causing an agent to take actions; account takeover; leakage of grading data or other learners' data; and runaway inference cost.

## Authentication and sessions

| Control | Status | Where |
|---|---|---|
| Argon2id password hashing with rehash-on-login | ✅ | `core/security.py` |
| Length-first password policy (≥10 chars, not common, not the email) | ✅ | `password_problems` |
| Timing-equalised login for unknown accounts; identical error message | ✅ | `auth.login` |
| Server-side sessions; cookie holds a random token, DB stores only its SHA-256 | ✅ | `models/identity.Session` |
| Session cookie `HttpOnly`, `SameSite=Lax`, `Secure` in production (enforced at startup) | ✅ | `auth.set_session_cookie`, `config._production_guards` |
| New session id on every login (fixation) | ✅ | |
| Logout, logout everywhere, and all sessions revoked on password reset | ✅ | tests: `test_auth.py` |
| Email verification and reset tokens: single-use, hashed, expiring (48 h / 30 min), older tokens invalidated | ✅ | `issue_token`, `consume_token` |
| No account enumeration on password reset | ✅ | tested |
| Rate limits per IP and per account on auth endpoints | ✅ (in-memory) / ⏭ Redis for multi-instance | `core/ratelimit.py` |
| MFA / SSO (Team plan) | ⏭ | |

## Request security

| Control | Status |
|---|---|
| CSRF: double-submit cookie (`af_csrf` → `X-CSRF-Token`) plus `Origin` allowlist on all unsafe `/api` requests | ✅ tested |
| CORS restricted to configured origins, credentials only for those | ✅ |
| Pydantic validation on every body/query; size limits on code, text and JSON inputs | ✅ |
| Consistent error envelope; no stack traces to clients; trace id for support | ✅ |
| Security headers on API (`nosniff`, `DENY` framing, referrer policy, permissions policy, `no-store` for API) | ✅ |
| Strict CSP on the SPA: no inline or third-party scripts; Monaco bundled locally (no CDN) | ✅ verified with the production build |
| `TRUSTED_PROXIES` controls which `X-Forwarded-For` hop is trusted for client IPs | 🟡 set to your proxy depth |
| HTTPS / HSTS at the load balancer or CDN | 🟡 see DEPLOYMENT.md |

## Authorization and tenancy

| Control | Status |
|---|---|
| Role checks (learner, author, reviewer, admin) on every admin route | ✅ tested |
| Four-eyes publishing: authors can't publish their own lesson versions | ✅ tested |
| Reviewers can't review their own submissions | ✅ |
| Object-level checks: runs and attempts readable only by their owner (or admin); 404 rather than 403 to avoid revealing existence | ✅ tested |
| Plan/tier checks server-side for lessons, challenges, agents; quotas per plan from `entitlements` | ✅ tested |
| Grading data (`exercises.spec`, quiz answers, hidden tests) never serialised before solving; hidden test inputs/outputs never returned | ✅ tested |
| Tenant boundary (`organizations`) for Team plans; RAG document permissions derived from roles, never from request input | ✅ foundation / ⏭ full team features |

## Untrusted code execution

The API process **never** executes learner code. It calls the sandbox runner over an internal network with a shared token.

| Layer | Control | Status |
|---|---|---|
| Network | Sandbox is only on an `internal: true` Docker network: no internet, no route to the database or cloud metadata | ✅ compose |
| Credentials | No secrets or cloud credentials in the sandbox container; separate IAM-less task in production | ✅ / 🟡 |
| Container | Non-root user (uid 10001), read-only root filesystem, `/tmp` tmpfs (`noexec,nosuid,nodev`, 64 MB), `cap_drop: ALL`, `no-new-privileges`, `pids_limit: 128`, 512 MB memory, 1 CPU | ✅ compose |
| Process | Per-run temp directory, `setsid` process group killed on timeout, `RLIMIT_CPU`, `RLIMIT_AS` 512 MB (Python/SQL), `RLIMIT_FSIZE` 1 MB, `RLIMIT_NOFILE` 64, no core dumps, minimal environment, `python -I` isolated mode | ✅ tested |
| Time and output | Wall-clock timeout (default 5 s, max 15 s), stdout/stderr capped at 64 KB | ✅ tested |
| Grading integrity | Harness reads a per-run nonce and the spec from stdin before learner code runs; only the nonce-tagged result line is trusted | ✅ (points are a learning aid, not a security boundary) |
| Abuse | Per-user rate limits, per-challenge hourly cap, daily quotas by plan | ✅ |
| Kernel isolation | gVisor (`runsc`) or Firecracker microVMs | ⏭ H-02 |

Development note: `make dev-sandbox` runs the runner directly on your machine with rlimits but **without** container isolation. Use it only for local development.

## AI and agent safety

| Control | Status |
|---|---|
| Provider keys only in server environment / secrets manager; never in the browser, the database or workflow definitions (`credential_refs` stores references) | ✅ |
| Free plan uses the mock provider only; real-model runs gated by plan | ✅ |
| Per-run budgets (model calls, tokens, seconds) and API-side wall-clock timeout | ✅ |
| Tools are allowlisted with JSON-schema-validated arguments | ✅ |
| Side-effect tools are never executed by the agent: proposed as `pending_actions`, applied only after human approval, decision audit-logged | ✅ tested |
| Retrieved documents, diffs, logs and tool outputs are fenced as untrusted data in prompts; guardrails re-validate outputs (citations must reference retrieved passages, review comments must target changed lines) | ✅ per agent, covered by eval cases |
| Document permissions enforced at retrieval time (PDF Knowledge Agent) | ✅ eval case |
| PII redaction before model calls (`core/text.py`, used by the Customer Support Triage agent; also taught in a security challenge) | ✅ partial: extend to every agent that sends free text to a provider |
| Cost tracking per run with configurable prices; unknown prices flagged in analytics | ✅ |

## Data protection and privacy

| Control | Status |
|---|---|
| Analytics events: allowlisted, non-personal properties only; pseudonymous user ids | ✅ `services/common.track` |
| AI mentor and public portfolio are opt-in profile settings | ✅ |
| Audit log for security-relevant actions (login, verify, reset, publish, review, plan change, approvals) with actor, before/after and trace id | ✅ |
| Encryption at rest (RDS, S3) and in transit (TLS) | 🟡 see DEPLOYMENT.md |
| Account deletion and data export | ⏭ H-04 |
| Retention policy for `usage_events` and `agent_runs` inputs | ⏭ |

## Production configuration guardrails

`ENV=production` refuses to start unless: `COOKIE_SECURE=true`, `MAIL_BACKEND=smtp`, `SANDBOX_TOKEN` is set when `SANDBOX_URL` is, and the seed admin password no longer contains `ChangeMe`.

## Pre-launch checklist

- [ ] Generate a long random `SANDBOX_TOKEN`; store all secrets in AWS Secrets Manager / SSM
- [ ] `COOKIE_SECURE=true`, HTTPS everywhere, HSTS at the edge
- [ ] `CORS_ORIGINS` and `FRONTEND_URL` set to the production domain only
- [ ] Change or disable seed accounts (`python -m app.seed --no-users` after the first admin exists)
- [ ] `TRUSTED_PROXIES` matches the number of proxies in front of the API
- [ ] Redis-backed rate limiter before scaling the API horizontally
- [ ] Sandbox on its own ECS service/subnet with no NAT route and no task role permissions
- [ ] Database backups enabled and a restore tested
- [ ] `MODEL_PRICES` configured for every enabled model; budget alarms on provider spend
- [ ] Dependency scanning (Dependabot / `pip-audit` / `npm audit`) enabled on the repository
- [ ] Run the OWASP ZAP baseline scan against staging

## Reporting a vulnerability

Please report security issues privately to the maintainers rather than opening a public issue.
