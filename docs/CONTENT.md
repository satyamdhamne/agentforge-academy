# Content authoring guide

Content lives in the repository and is loaded by an idempotent seed (`python -m app.seed`). Editing a file and re-running the seed publishes a **new lesson version**; history is never overwritten. Authors can also edit lessons in the Admin CMS (draft → review → published).

```
backend/app/seed/content/
├── curriculum.yaml        # Track > Course > Module > Lesson outline (16 tracks)
├── lessons/<slug>.yaml    # one file per complete lesson; a lesson without a file shows as "coming soon"
├── challenges.yaml        # standalone challenges
└── platform.yaml          # plan entitlements, achievements, projects, announcements
```

## Lesson file

Every lesson must provide all of these `sections` (the API rejects versions with missing ones):

| Key | Content |
|---|---|
| `explanation` | Simple explanation (Markdown) |
| `why_it_matters` | Why an engineer should care |
| `prerequisites` | List of prior knowledge |
| `mental_model` | An analogy or mental model |
| `architecture` | `{caption, mermaid}` or `null` when a diagram wouldn't help |
| `code_examples` | List of `{title, language, runnable, code, setup?, annotations, expected_output}` |
| `real_world` | How it's used in production |
| `common_mistakes` | List of `{mistake, fix}` |
| `debugging` | Debugging techniques |
| `performance_security` | Performance and security considerations |
| `interview_questions` | List of `{q, a}` |
| `mini_challenge` | `{title, prompt, exercise?}` (link to an exercise slug) |
| `advanced_challenge` | `{title, prompt}` |
| `further_reading` | List of `{title, url}` |
| `version_notes` | Versions the lesson was written against |

Plus top-level `slug`, `title`, `summary`, `minutes`, `level`, `tier`, `tags`, `prerequisites` (lesson slugs), `quiz` (list of `{prompt, options, answer, explanation}`; 70% to pass) and optional `exercises`.

**Runnable examples are tested.** `python scripts/verify_content.py` runs every example with `runnable: true` in the sandbox executor and fails if the output differs from `expected_output`. Python, JavaScript and SQL (SQLite, with `setup`) are supported. YAML anchors (`&name` / `*name`) are handy for sharing SQL setup across examples.

## Exercises and challenges

Common fields: `slug`, `title`, `kind`, `category`, `difficulty`, `points`, `prompt_md`, `hints`, `explanation_md`, `tags`, optional `tier`, `time_limit_minutes`, `is_weekly_project`.

| `kind` | Extra fields | Grading |
|---|---|---|
| `code` (Python/JS) | `language`, `starter_code`, `solution`, `tests: {function, compare: exact\|approx\|unordered, cases: [{args, expected, hidden?}]}` | Sandbox runs `function(*args)` per case |
| `code` (SQL) | `language: sql`, `starter_code`, `solution`, `sql: {setup, expected_columns, expected_rows, ordered}` | Sandbox compares the result set |
| `multiple_choice` | `options`, `correct_index` | Server-side; repeated wrong guesses reduce points |
| `manual_review` | `rubric: [{criterion, weight, description}]`, `min_words` | Reviewer scores each criterion 0–1 in the Admin CMS |

`verify_content.py` also checks that every reference **solution passes** all its tests and that every **starter fails** at least one, so an exercise can't be accidentally pre-solved. Add at least one `hidden: true` case so hard-coding visible examples doesn't pass.

Categories: `coding`, `debugging`, `architecture`, `prompt`, `rag`, `agent`, `security`, `cloud`, `interview`.

## Agents

Reference agents live in `agents/agentforge_agents/<name>/` and export an `AgentSpec` (input model, run function, mock responders, examples, blueprint). The agent detail page is generated from the code: prompts are module-level constants whose names contain `PROMPT` or `TEMPLATE`, tool schemas come from the tool registry, and evaluation cases come from `evals/cases.jsonl`. Catalog-only blueprints are rows in `agents/agentforge_agents/catalog.py`.

To add a reference implementation: create the package, register it in `registry.IMPLEMENTED` and `catalog.IMPLEMENTED_SLUGS`, add `tests/test_<name>.py` and an eval set, then run `python -m agentforge_agents eval <slug>` and re-seed.

## Style

Write for a busy engineer: plain language, short paragraphs, concrete examples. Say what goes wrong in production and how to notice it. Prefer showing a failing case next to the fix. Date anything version-specific in `version_notes`.
