"""The 100-agent catalog.

Ten entries have full reference implementations (see registry.IMPLEMENTED). The other ninety are
*blueprints*: a problem statement, an honest verdict on whether an agent is the right tool, suggested
tools, the key risk and a reference architecture. They are labelled as blueprints in the product.
"""

from __future__ import annotations

import re
from typing import Any

DEV, DATA, OPS, RES = "Developer Productivity", "Data Engineering", "Business Operations", "Research & Knowledge"
CS, SM, FIN, HR = "Customer Support", "Sales & Marketing", "Finance Operations", "HR & Recruiting"
SEC, CLOUD, EDU, EKM = "Security & IT Operations", "Cloud & DevOps", "Education", "Enterprise Knowledge Management"
CATEGORIES = [DEV, DATA, OPS, RES, CS, SM, FIN, HR, SEC, CLOUD, EDU, EKM]

IMPLEMENTED_SLUGS = {
    1: "github-pr-review-agent", 3: "unit-test-generation-agent", 5: "bug-triage-agent", 6: "log-analysis-agent",
    7: "sql-query-assistant", 12: "release-notes-generator", 20: "csv-cleaning-agent", 23: "pdf-knowledge-agent",
    27: "customer-support-triage-agent", 48: "invoice-extraction-agent",
}

# (number, name, category, level, build_hours, verdict, problem, why, suggested_tools, key_risk)
BLUEPRINTS: list[tuple] = [
    (2, "Code Explanation Agent", DEV, "beginner", 3, "workflow", "Developers onboarding to unfamiliar code need plain-language explanations of functions and modules.", "A single prompt over a code snippet plus retrieved related symbols is enough; there is no tool choice to make.", "ast_outline, fetch_related_symbols", "Confidently wrong explanations of subtle code - cite line ranges and show the code."),
    (4, "API Test Agent", DEV, "intermediate", 6, "workflow", "APIs need HTTP contract tests covering happy paths and edge cases.", "Requests can be generated from the OpenAPI spec deterministically; the model adds edge-case ideas; execution runs in a sandbox.", "load_openapi, generate_requests, run_in_sandbox", "Accidentally hitting production - enforce a base-URL allowlist."),
    (8, "SQL Optimization Agent", DATA, "advanced", 8, "workflow", "Slow queries hurt latency and cost; engineers lack time to read query plans.", "Fixed loop: EXPLAIN, model proposes index or rewrite, verify with EXPLAIN on a replica.", "explain_analyze (replica), list_indexes, compare_plans", "New indexes slow down writes - validate on a replica, never on production."),
    (9, "Documentation Generator", DEV, "beginner", 4, "workflow", "Docstrings and READMEs drift away from the code.", "Per-file generation in a fixed pipeline, opened as a pull request for review.", "ast_outline, read_file, open_pull_request (approval)", "Docs that describe intended rather than actual behaviour."),
    (10, "Migration Planning Agent", DEV, "advanced", 10, "agent", "Planning framework or database migrations requires surveying many files and dependencies.", "Exploration depth varies by codebase, so an agent with read-only code search explores, then hands a plan to humans.", "search_code, read_file, list_dependencies", "An incomplete survey presented as complete - report coverage statistics."),
    (11, "Dependency Risk Analyzer", DEV, "intermediate", 4, "deterministic", "Teams don't know which dependencies are vulnerable, abandoned or license-incompatible.", "Vulnerability databases (OSV), license metadata and maintenance signals are lookups; a model only summarises.", "parse_lockfile, query_osv, fetch_license", "False sense of safety from incomplete advisory data."),
    (13, "Incident Summary Agent", CLOUD, "intermediate", 4, "workflow", "Stakeholders need concise incident updates from noisy chat channels and alert timelines.", "Summarising a bounded timeline into a template needs one model call, not tool choice.", "fetch_channel_messages, fetch_alerts", "Leaking sensitive details to broad audiences - audience-specific templates."),
    (14, "Cloud Cost Advisor", CLOUD, "intermediate", 6, "workflow", "Cloud bills grow through idle resources and oversized instances.", "Cost/usage data and rules (idle, rightsizing) find savings; the model explains and prioritises.", "cost_explorer_query, cloudwatch_utilization, list_resources", "Recommending deletion of resources that only look idle - never auto-delete."),
    (15, "CI/CD Failure Investigator", CLOUD, "intermediate", 6, "agent", "Failed pipelines waste developer time on log spelunking.", "Failures differ (flaky test, dependency, infrastructure), so an agent chooses which logs and history to inspect.", "get_job_logs, get_previous_runs, get_diff, search_known_failures", "Retrying flaky jobs hides real failures - report flakiness rates."),
    (16, "Infrastructure Configuration Reviewer", CLOUD, "intermediate", 5, "deterministic", "Misconfigured infrastructure (public buckets, open security groups) causes breaches.", "Policy-as-code scanners (Checkov, OPA, tfsec) catch known misconfigurations deterministically; a model explains findings.", "run_policy_scanner, explain_finding", "A model-only review silently misses rules - scanners are the source of truth."),
    (17, "Data Quality Agent", DATA, "intermediate", 6, "workflow", "Bad data reaches dashboards before anyone notices.", "Expectations (nulls, ranges, freshness) are rules; the model drafts new expectations from profiles for review.", "profile_table, run_expectations, propose_expectations", "Alert fatigue from noisy thresholds."),
    (18, "ETL Pipeline Assistant", DATA, "intermediate", 6, "workflow", "Building ETL jobs for each new source is repetitive boilerplate.", "Template-driven code generation with schema inference; humans review generated jobs.", "infer_schema, generate_job_template, dry_run", "Silent type coercions - require a dry-run diff."),
    (19, "Schema Mapping Agent", DATA, "intermediate", 5, "workflow", "Mapping fields between systems (CRM to warehouse) is slow and error-prone.", "Name similarity plus model proposals with confidence, confirmed by humans.", "list_columns, sample_values, embed_names", "Plausible but wrong mappings - require sample-value evidence."),
    (21, "Research Assistant", RES, "intermediate", 8, "agent", "Researchers spend hours collecting and synthesising sources on a topic.", "Search depth varies by question; the agent decides queries and when to stop, within a budget.", "web_search, fetch_page, take_notes", "Fabricated citations - verify every citation by fetching it."),
    (22, "Web Research Agent", RES, "intermediate", 6, "agent", "Answering current-events or market questions needs live web data.", "An iterative search-read-refine loop justifies an agent.", "web_search, fetch_page (allowlist), extract_facts", "Prompt injection from web pages - pages are untrusted and no side-effect tools exist."),
    (24, "Multi-Document Comparison Agent", RES, "intermediate", 5, "workflow", "Comparing contracts, policies or proposals side by side is tedious.", "Align sections, then compare per section - a fixed pipeline.", "split_sections, align_sections, diff_clauses", "Missing differences in unaligned sections - report coverage."),
    (25, "Enterprise RAG Assistant", EKM, "advanced", 16, "rag", "Employees can't find answers across wikis, drives and tickets.", "A retrieval pipeline with connectors, permissions and citations; agentic search only where evals show multi-hop needs.", "connector_sync, hybrid_search, rerank, permission_filter", "Permission leaks across sources - enforce ACLs at retrieval time."),
    (26, "Knowledge Base Update Agent", EKM, "intermediate", 6, "workflow", "Help-center articles go stale as products change.", "Detect stale articles from release notes and tickets, then draft updates for editors.", "search_articles, fetch_release_notes, draft_update", "Publishing unreviewed changes - editor approval required."),
    (28, "Support Response Drafting Agent", CS, "intermediate", 5, "rag", "Support agents write similar replies repeatedly and inconsistently.", "Retrieve similar resolved tickets and KB articles, then draft a reply the agent edits.", "search_kb, search_resolved_tickets, draft_reply", "Promising refunds or policies that don't exist - ground replies in policy documents."),
    (29, "Ticket Routing Agent", CS, "beginner", 3, "workflow", "Tickets reach the wrong queue and bounce between teams.", "Classification plus a routing table; a classic classifier may be enough.", "classify, routing_table", "Skewed routing for under-represented categories."),
    (30, "Customer Feedback Analyzer", CS, "beginner", 4, "workflow", "Product teams can't read thousands of reviews and survey answers.", "Batch classification into themes and sentiment, aggregated in code.", "classify_theme, sentiment, aggregate", "Themes drifting between batches - use a fixed taxonomy."),
    (31, "Meeting Summary Agent", OPS, "beginner", 3, "workflow", "Meeting decisions and action items get lost.", "Transcript to structured summary (decisions, actions, owners) in one call.", "fetch_transcript, extract_actions", "Assigning actions to the wrong person - include supporting quotes."),
    (32, "Email Classification Agent", OPS, "beginner", 3, "workflow", "Shared inboxes overflow and urgent emails get buried.", "Classification with rules; no tool choice.", "classify, apply_label (approval)", "Misclassified urgent emails - confidence threshold plus a human queue."),
    (33, "Email Drafting Agent", OPS, "beginner", 3, "workflow", "Drafting routine replies takes time.", "A single generation with tone and thread context; sending always requires approval.", "fetch_thread, draft_reply", "Auto-sending inappropriate emails - never send without approval."),
    (34, "Calendar Planning Agent", OPS, "intermediate", 6, "agent", "Scheduling across time zones and constraints is tedious.", "Exploring constraints benefits from tool calls (free/busy, preferences), but booking requires approval.", "get_free_busy, propose_slots, create_event (approval)", "Double-booking and time-zone errors - validate slots with a solver."),
    (35, "CRM Enrichment Assistant", SM, "beginner", 4, "workflow", "CRM records are incomplete (industry, size, website).", "Enrichment API lookups; the model normalises fields.", "lookup_company, normalize_fields, update_record (approval)", "Overwriting good data with guesses - only fill empty fields."),
    (36, "Lead Qualification Agent", SM, "intermediate", 5, "workflow", "Sales teams waste time on unqualified leads.", "A transparent scoring rubric applied consistently; the model extracts signals from free text.", "fetch_lead, enrich_company, score_rubric", "Biased scoring - audit which features drive scores."),
    (37, "Sales Research Agent", SM, "intermediate", 6, "agent", "Reps research accounts manually before calls.", "Research depth varies per account; a bounded web research loop fits.", "web_search, fetch_page, crm_lookup", "Outdated or wrong facts in briefs - cite dated sources."),
    (38, "Proposal Drafting Agent", SM, "intermediate", 6, "rag", "Proposals reuse content from past wins, but assembling them is slow.", "Retrieve approved content blocks and fill a template.", "search_content_library, fill_template", "Committing to unapproved terms - legal review gate."),
    (39, "Content Planning Agent", SM, "beginner", 3, "workflow", "Marketing calendars need consistent topic planning.", "Generate a plan from goals and past performance; humans edit.", "fetch_analytics, draft_calendar", "Generic content - ground plans in audience data."),
    (40, "Social Media Draft Agent", SM, "beginner", 2, "workflow", "Teams need channel-specific drafts quickly.", "One constrained generation per channel (length, tone).", "draft_post, check_length", "Publishing without review - brand checks and approval."),
    (41, "SEO Audit Agent", SM, "intermediate", 5, "deterministic", "Pages lose ranking due to technical SEO issues.", "Crawlers check titles, meta tags, links and speed deterministically; a model prioritises fixes.", "crawl_site, lighthouse_audit, summarize_findings", "Crawling without permission or rate limits."),
    (42, "Competitor Research Agent", SM, "intermediate", 6, "agent", "Tracking competitor launches and pricing is manual.", "Sources vary per competitor; a bounded research loop fits.", "web_search, fetch_page, diff_snapshots", "Terms-of-service violations - respect robots.txt and site terms."),
    (43, "Resume Review Agent", HR, "beginner", 3, "workflow", "Candidates want actionable resume feedback.", "Rubric-based feedback in one call.", "parse_resume, rubric_feedback", "Biased feedback - exclude protected attributes."),
    (44, "Interview Preparation Agent", HR, "beginner", 3, "workflow", "Candidates need targeted practice questions for a role.", "Generate questions from the job description and level.", "parse_jd, generate_questions", "Fabricated company-specific facts."),
    (45, "Job Description Analyzer", HR, "beginner", 3, "workflow", "Job descriptions contain biased or unclear language.", "Term lists flag issues deterministically; the model suggests rewrites.", "detect_biased_terms, extract_requirements", "Over-sanitised, generic descriptions."),
    (46, "Onboarding Assistant", HR, "intermediate", 6, "rag", "New hires ask the same questions in their first weeks.", "RAG over onboarding docs plus a checklist tracker.", "search_docs, get_checklist", "Outdated answers - track document freshness."),
    (47, "Employee Policy Q&A Agent", HR, "beginner", 4, "rag", "HR answers repetitive policy questions.", "Grounded Q&A with citations and refusal when unsure (see the PDF Knowledge Agent).", "search_policies", "Wrong HR guidance - always offer escalation to HR."),
    (49, "Expense Categorization Agent", FIN, "beginner", 3, "workflow", "Expense reports need consistent ledger categories.", "Merchant rules first, a model only for the long tail.", "merchant_lookup, classify_expense", "Policy violations slipping through - run separate policy checks."),
    (50, "Financial Document Comparison Agent", FIN, "intermediate", 6, "workflow", "Analysts compare statements across periods by hand.", "Extract tables, then compute differences in code.", "extract_tables, compute_variance", "Misaligned line items - reconcile totals."),
    (51, "Contract Clause Extraction Agent", FIN, "intermediate", 6, "workflow", "Legal teams need key clauses (termination, liability, renewal) extracted.", "Extraction into a schema with verbatim quotes as evidence.", "split_clauses, extract_to_schema", "Missed clauses - require evidence spans for every field."),
    (52, "Procurement Document Analyzer", FIN, "intermediate", 5, "workflow", "Procurement reviews long RFP responses against requirements.", "Requirement-by-requirement checklist evaluation.", "extract_requirements, match_responses", "Unfair scoring - publish the rubric."),
    (53, "Vendor Comparison Agent", FIN, "intermediate", 5, "workflow", "Vendor quotes arrive in different structures.", "Normalise quotes into one schema; compute comparisons in code.", "extract_quote, normalize_units", "Unit mismatches - require explicit units."),
    (54, "Inventory Planning Assistant", OPS, "advanced", 10, "deterministic", "Stockouts and overstock come from poor forecasts.", "Forecasting is statistics (seasonal models), not LLM work; a model explains the forecast.", "load_sales_history, forecast, reorder_points", "LLM-generated numbers - numbers must come from the forecasting code."),
    (55, "Security Alert Triage Agent", SEC, "advanced", 8, "agent", "SOC analysts drown in alerts.", "Investigation steps vary by alert type; the agent gathers context through read-only tools.", "get_alert, query_siem, lookup_ip_reputation, get_asset_owner", "Attacker-controlled log content - read-only tools, analyst approval for any response."),
    (56, "Access Review Assistant", SEC, "intermediate", 5, "workflow", "Quarterly access reviews get rubber-stamped.", "Rules flag risky access (dormant, privileged, separation of duties); the model writes reviewer summaries.", "list_entitlements, last_login, sod_rules", "Auto-revoking access - a human decides."),
    (57, "Compliance Evidence Organizer", SEC, "intermediate", 6, "workflow", "Audits require collecting evidence for many controls.", "Classify evidence files against controls and track a checklist.", "list_controls, classify_evidence", "Mis-mapped evidence - auditor review."),
    (58, "Vulnerability Explanation Agent", SEC, "beginner", 3, "rag", "Developers don't understand scanner findings.", "Explain CVEs grounded in advisory text and the affected code.", "fetch_advisory, read_code", "Wrong remediation advice - cite advisories."),
    (59, "Phishing Awareness Trainer", SEC, "beginner", 4, "workflow", "Employees need safe, realistic phishing-awareness training.", "Generates clearly labelled training examples with red flags annotated; it has no ability to send email.", "generate_training_example, quiz", "Misuse for real phishing - labelled examples only, no sending capability."),
    (60, "AWS Architecture Review Agent", CLOUD, "advanced", 8, "workflow", "Architectures miss Well-Architected best practices.", "Checklist review by pillar against an architecture derived from IaC.", "parse_iac, well_architected_checklist", "Generic advice - tie each finding to a specific resource."),
    (61, "Terraform Review Agent", CLOUD, "intermediate", 5, "workflow", "Terraform plans hide risky destroy/replace operations.", "Parse plan JSON for destroys, run policy checks, then summarise impact.", "parse_plan_json, policy_check", "Approving destructive changes - block destroys without explicit approval."),
    (62, "Kubernetes Troubleshooting Agent", CLOUD, "advanced", 8, "agent", "Debugging CrashLoopBackOff or OOMKilled pods takes many commands.", "The diagnostic path depends on symptoms; read-only kubectl tools in a bounded loop.", "kubectl_get, kubectl_describe, kubectl_logs (read-only)", "Write access to clusters - strictly read-only RBAC."),
    (63, "SRE Runbook Assistant", CLOUD, "intermediate", 5, "rag", "On-call engineers can't find the right runbook step under pressure.", "Retrieve runbook sections by alert; the assistant takes no actions.", "search_runbooks, get_alert_context", "Executing steps automatically - humans execute."),
    (64, "Postmortem Draft Agent", CLOUD, "beginner", 3, "workflow", "Postmortems are delayed because drafting is tedious.", "Timeline and chat history into a template draft.", "fetch_timeline, fetch_channel", "Blameful language - follow a blameless style guide."),
    (65, "SLA Reporting Agent", CLOUD, "beginner", 3, "deterministic", "Monthly SLA reports are assembled manually.", "SLA math is deterministic from uptime data; a model writes the narrative only.", "query_uptime, compute_sla", "A model computing percentages - compute in code."),
    (66, "Cloud Resource Inventory Agent", CLOUD, "intermediate", 4, "deterministic", "Nobody knows which resources exist and who owns them.", "API enumeration and tagging rules; natural-language queries are optional.", "list_resources, check_tags", "Over-privileged credentials - scoped read-only role."),
    (67, "API Documentation Agent", DEV, "beginner", 4, "workflow", "API docs lag behind endpoints.", "Generate from the OpenAPI spec and code comments.", "load_openapi, draft_docs", "Documenting parameters that don't exist - derive from the spec."),
    (68, "OpenAPI Test Generator", DEV, "intermediate", 5, "deterministic", "APIs lack contract tests.", "Schema-driven generation (e.g. Schemathesis) is deterministic; a model adds scenario ideas.", "load_openapi, generate_cases, run_cases", "Testing against production - environment allowlist."),
    (69, "Database Migration Validator", DATA, "intermediate", 5, "deterministic", "Migrations lock tables or lose data in production.", "Static rules (NOT NULL without default, non-concurrent index builds) plus a dry run on a shadow database.", "parse_migration, lint_rules, dry_run_shadow_db", "Running on production - shadow database only."),
    (70, "Performance Bottleneck Investigator", DEV, "advanced", 8, "agent", "Latency regressions take a long time to pinpoint.", "The investigation path depends on traces and profiles; the agent explores telemetry.", "query_traces, get_profile, compare_releases", "Correlation mistaken for cause - propose experiments, not conclusions."),
    (71, "Memory Leak Investigation Assistant", DEV, "advanced", 8, "workflow", "Memory leaks are hard to diagnose from heap dumps.", "Diff heap snapshots deterministically; the model explains suspects.", "diff_heap_snapshots, top_retainers", "Heap dumps contain sensitive data - process locally."),
    (72, "Architecture Diagram Agent", DEV, "intermediate", 4, "workflow", "Architecture diagrams are missing or outdated.", "Generate Mermaid from IaC and service manifests.", "parse_iac, render_mermaid", "Diagrams implying connections that don't exist - derive edges from config."),
    (73, "Codebase Q&A Agent", DEV, "intermediate", 8, "rag", "Engineers spend hours finding where things live in large codebases.", "Code-aware retrieval (symbols plus embeddings); agentic search only for multi-hop questions.", "symbol_search, semantic_search, read_file", "Secrets in indexed code - run secret scanning before indexing."),
    (74, "Dependency Upgrade Planner", DEV, "intermediate", 6, "workflow", "Major upgrades stall because impact is unknown.", "Changelog retrieval plus usage search produce an upgrade checklist.", "fetch_changelog, search_usages", "Missed breaking changes - always run the test suite in CI."),
    (75, "Feature Specification Agent", OPS, "intermediate", 4, "workflow", "Vague feature ideas lead to rework.", "A structured interview fills a spec template.", "ask_questions, fill_spec_template", "Invented requirements - mark assumptions explicitly."),
    (76, "User Story Generator", OPS, "beginner", 2, "workflow", "Backlogs need well-formed user stories.", "Template generation from a feature brief.", "draft_stories", "Stories without user value - INVEST checklist."),
    (77, "Acceptance Criteria Agent", OPS, "beginner", 2, "workflow", "Stories lack testable acceptance criteria.", "Generate Given/When/Then criteria from each story.", "draft_criteria", "Untestable criteria - lint for measurability."),
    (78, "Regression Test Planner", DEV, "intermediate", 5, "workflow", "Teams don't know which tests to run for a change.", "Map changed files to tests via coverage data; the model fills gaps.", "get_diff, coverage_map", "Skipping needed tests - always run critical suites."),
    (79, "Accessibility Audit Assistant", DEV, "intermediate", 4, "deterministic", "Accessibility issues ship unnoticed.", "axe-core finds WCAG violations deterministically; a model explains fixes.", "run_axe, explain_violation", "Automated checks catch only part of WCAG - manual testing is still required."),
    (80, "Localization Assistant", OPS, "beginner", 4, "workflow", "Translating UI strings consistently is slow.", "Batch translation with a glossary and placeholder validation.", "load_strings, translate_batch, validate_placeholders", "Broken placeholders - validate every string."),
    (81, "Study Plan Agent", EDU, "beginner", 3, "workflow", "Learners don't know what to study next or how to schedule it.", "Plan from goals, time budget and the prerequisite graph.", "get_progress, prerequisite_graph", "Overloaded plans - respect the stated time budget."),
    (82, "Quiz Generator", EDU, "beginner", 3, "workflow", "Instructors need fresh quiz questions aligned to content.", "Generate from lesson content, then verify each answer against the source.", "fetch_lesson, generate_questions, verify_answer_in_source", "Wrong answer keys - verify against the source text."),
    (83, "Coding Interview Agent", EDU, "intermediate", 6, "agent", "Candidates want realistic mock coding interviews.", "The interviewer adapts hints and follow-ups to the candidate's progress.", "run_tests_in_sandbox, give_hint, score_rubric", "Implying hiring outcomes - transparent rubric only, no guarantees."),
    (84, "Learning Path Advisor", EDU, "beginner", 3, "workflow", "Learners take courses in the wrong order.", "A deterministic prerequisite-graph walk from a skills assessment; the model explains it.", "assess_skills, prerequisite_graph", "Recommendations driven by upsell - base them on learning goals only."),
    (85, "Technical Mentor Agent", EDU, "intermediate", 6, "rag", "Learners get stuck and need Socratic guidance, not answers.", "Grounded in course content; withholds full solutions unless the learner asks.", "search_course_content, get_attempt_history", "Revealing solutions - solution-withholding policy and explicit opt-in."),
    (86, "Flashcard Generator", EDU, "beginner", 2, "workflow", "Spaced repetition needs good flashcards.", "Extract atomic facts from lesson content.", "fetch_lesson, generate_cards", "Ambiguous cards - one fact per card."),
    (87, "Research Paper Summarizer", RES, "beginner", 3, "workflow", "Reading papers fully takes time.", "Section-aware summarisation into a structure (method, results, limitations).", "parse_pdf, summarize_sections", "Overstated results - quote key numbers exactly."),
    (88, "Citation Verification Assistant", RES, "intermediate", 4, "workflow", "Documents contain citations that don't support their claims.", "Fetch each cited source and check claim support - a fixed per-citation loop.", "fetch_source, check_support", "Paywalled sources - mark them unverifiable rather than guessing."),
    (89, "Dataset Labeling Assistant", DATA, "intermediate", 5, "workflow", "Labeling datasets is slow and inconsistent.", "Pre-label with a model; humans verify low-confidence items.", "prelabel, confidence_queue", "Labelers rubber-stamping model labels - measure inter-annotator agreement."),
    (90, "Synthetic Test Data Generator", DATA, "beginner", 3, "deterministic", "Tests need realistic data without real personal data.", "Schema-driven generators (Faker) are deterministic and reproducible; a model only for free-text fields.", "read_schema, generate_rows", "Copying real PII - generate, never sample production."),
    (91, "RAG Evaluation Agent", RES, "advanced", 8, "workflow", "Teams can't tell whether RAG changes improve quality.", "Retrieval metrics computed in code; LLM-as-judge for faithfulness, calibrated against human labels.", "run_queries, recall_at_k, judge_faithfulness", "Uncalibrated judges - spot-check with humans."),
    (92, "Prompt Evaluation Agent", DEV, "intermediate", 5, "workflow", "Prompt changes silently break edge cases.", "Run prompt variants over a test set and score with assertions and rubrics.", "run_variants, score_rubric, compare", "Overfitting to the eval set - keep hold-out cases."),
    (93, "Model Routing Agent", DEV, "advanced", 6, "deterministic", "Using the largest model for everything is expensive.", "Routing is a classifier or rules (task type, length) with fallbacks - not an agent.", "classify_request, route, fallback", "Quality drops on misrouted requests - monitor quality per route."),
    (94, "LLM Cost Analysis Agent", OPS, "beginner", 3, "deterministic", "AI spend is opaque across teams and features.", "Aggregate usage logs against a price table; a model writes insights.", "load_usage_events, price_table, aggregate", "Stale prices - version the price table."),
    (95, "Tool Selection Agent", DEV, "advanced", 6, "workflow", "Agents with many tools pick the wrong ones and waste tokens.", "Retrieve the top-k relevant tools per request before the agent loop starts.", "embed_tool_descriptions, select_tools", "Filtering out the tool that was needed - measure tool recall."),
    (96, "Workflow Planning Agent", OPS, "advanced", 8, "agent", "Complex goals need decomposition into steps.", "A planner proposes a DAG of allowlisted step types; a workflow engine executes with approvals.", "decompose_goal, validate_dag", "Plans with unsafe steps - allowlisted step types only."),
    (97, "Human Approval Coordinator", OPS, "intermediate", 5, "deterministic", "Agent actions need approvals routed to the right people with context.", "A state machine with timeouts and escalation; no model decisions are involved.", "create_approval, notify, escalate", "Approval fatigue - batch low-risk actions."),
    (98, "Multi-Agent Research Coordinator", RES, "expert", 16, "agent", "Broad research questions benefit from parallel investigation.", "An orchestrator spawns specialised sub-agents with budgets - only worth it when a single agent falls short on evals.", "spawn_subagent, merge_findings, budget_tracker", "Cost explosion and duplicated work - hard budgets per sub-agent."),
    (99, "Enterprise Workflow Orchestrator", EKM, "expert", 20, "agent", "Cross-system processes (onboarding, procurement) touch many systems and approvals.", "Durable execution (Temporal or LangGraph checkpoints) with agentic steps only where judgement is needed.", "durable_workflow, system_connectors, approvals", "Partial failures leaving inconsistent state - idempotent steps and compensation."),
    (100, "Agent Reliability Monitor", OPS, "advanced", 8, "deterministic", "Agent quality degrades silently in production.", "Metrics computed from traces (task success, tool errors, cost, latency) with alerts; sampled LLM-as-judge review.", "ingest_traces, compute_metrics, sample_for_review", "Monitoring only cost and not quality - track task success."),
]

ARCHITECTURES = {
    "deterministic": "flowchart LR\n    I[Input] --> E[Deterministic engine: rules / statistics / scanners]\n    E --> R[Results]\n    R --> L[Optional LLM: explain & prioritise]\n    L --> O[Report]",
    "workflow": "flowchart LR\n    I[Input] --> P[Preprocess & redact]\n    P --> L[LLM step → JSON schema]\n    L --> V{Validate & policy rules}\n    V --> O[Output]\n    V -->|low confidence| H[Human review]",
    "rag": "flowchart LR\n    Q[Question] --> F{Permission filter}\n    F --> R[Retrieve]\n    R --> RR[Rerank]\n    RR --> L[LLM: grounded answer]\n    L --> C{Citation check}\n    C --> A[Answer + sources]",
    "agent": "flowchart TD\n    I[Goal] --> L{LLM chooses next step}\n    L -->|tool call| T[Allowlisted read-only tools]\n    T --> L\n    L -->|finalize| G[Guardrails]\n    G --> P[[Side effects need approval]]\n    L -->|budget exhausted| H[Hand off to human]",
}
CHALLENGES = {
    "deterministic": ["Implement the deterministic core with unit tests and no model calls.", "Add an optional model step that only explains results; prove it cannot change numbers.", "Benchmark against an LLM-only version on accuracy, cost and latency."],
    "workflow": ["Build the pipeline with the mock provider and a 10-case eval set.", "Add schema validation with retries and policy rules that override the model.", "Swap in a real provider and compare quality, cost and latency against the mock baseline."],
    "rag": ["Index a small corpus and answer questions with citations.", "Add permission filtering and prove restricted documents never reach the prompt.", "Measure recall@k and faithfulness; tune chunking and reranking."],
    "agent": ["Implement the tool loop with a step budget and the mock policy.", "Add an approval gate for any side-effect action and an audit log.", "Compare against a fixed workflow on the same eval set and justify the agent."],
}
INTERVIEW = {
    "deterministic": [{"q": "Why isn't this an LLM agent?", "a": "The task is rule- or math-based; deterministic code is exact, cheap, testable and explainable. A model can add explanations on top."}],
    "workflow": [{"q": "Workflow or agent?", "a": "A workflow: the steps are known in advance, so a fixed pipeline with validation is cheaper and more reliable than letting a model choose."}],
    "rag": [{"q": "Where do you enforce permissions in RAG?", "a": "In the retrieval query (metadata filters), before any text reaches the model."}],
    "agent": [{"q": "What keeps this agent safe?", "a": "Allowlisted tools with validated arguments, read-only by default, step/token budgets, and human approval for side effects."}],
}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def blueprint_entries() -> list[dict[str, Any]]:
    """The 90 catalog-only blueprints as detail-page dictionaries."""
    out = []
    for num, name, cat, level, hours, verdict, problem, why, tools, risk in BLUEPRINTS:
        out.append({
            "number": num, "slug": slugify(name), "name": name, "category": cat, "level": level, "build_hours": hours,
            "verdict": verdict, "has_reference_impl": False, "summary": problem, "problem": problem,
            "verdict_reasoning": why, "suggested_tools": [t.strip() for t in tools.split(",")],
            "security": [{"threat": risk.split(" - ")[0], "mitigation": risk.split(" - ")[1] if " - " in risk else "Design a guardrail and test it."}],
            "architecture_mermaid": ARCHITECTURES[verdict],
            "challenges": [{"level": lvl, "title": f"Step {i + 1}", "description": d}
                           for i, (lvl, d) in enumerate(zip(["beginner", "intermediate", "advanced"], CHALLENGES[verdict]))],
            "interview_questions": INTERVIEW[verdict],
            "tags": [verdict, cat.split(" ")[0].lower()],
        })
    return out


def all_entries() -> list[dict[str, Any]]:
    """All 100 catalog entries, ordered by number. Implemented agents carry their full blueprint."""
    from .registry import IMPLEMENTED, build_blueprint

    entries = blueprint_entries()
    for num, slug in IMPLEMENTED_SLUGS.items():
        bp = build_blueprint(IMPLEMENTED[slug])
        entries.append({"number": num, **bp})
    entries.sort(key=lambda e: e["number"])
    return entries
