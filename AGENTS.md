# Agent Context & Rules

## 1. Project Overview
- **Project Name:** Data Analytics Dashboard
- **Core Purpose:** An interactive multi-page dashboard to visualize live data tables from Google BigQuery and provide an analytics layer pipeline monitoring console.
- **Target Audience:** Internal business analysts, data engineers, and stakeholders.

## 2. Tech Stack & Environment
- **Language:** Python 3.12 locally and in Docker; `pyproject.toml` requires Python >=3.12
- **Python Dependencies:** Root `pyproject.toml` and `uv.lock`, managed with uv. There is no `my-dash-app/requirements.txt`.
- **Core Framework:** Plotly Dash
- **Underlying Engine:** Flask, including Flask-Caching
- **Authentication:** Supabase Auth with `@supabase/supabase-js`, OAuth PKCE, and Flask server-side authorization
- **Frontend Build:** Node.js 22+, npm, and esbuild for the authentication bundle
- **Data Engine:** Google BigQuery via Application Default Credentials (ADC), plus dbt artifact telemetry
- **Data Libraries:** `google-cloud-bigquery`, `pandas`, `pandas-gbq`, `pyarrow`, `json`
- **Caching Framework:** Flask-Caching with FileSystemCache or Redis
- **Styling:** Dash component libraries and modular CSS
- **Code Formatters:** `black` for Python and Prettier for CSS

## 3. Architecture & File Structure
- Use Dash Pages with `dash.page_registry` and `dash.register_page(__name__)`, unless the Snapshot Engine is used. With Snapshot Engine, use callback routing instead of Dash Pages.
- Keep Dash page modules in a `pages/` directory.
- `my-dash-app/data_loader.py` owns dashboard data access and initializes BigQuery with ADC or the server-side `GCP_KEY_PATH` override. Shared caching lives in root `utils/cache.py`. Cache expensive data-fetching operations server-side.
- Pipeline Health reads cached BigQuery telemetry through `my-dash-app/data_loader.py`. `Scripts/ingest_dbt_artifacts.py` ingests `analytics_layer/target/run_results.json`; `analytics_layer/scripts/` calculates manifest coverage and uploads it to BigQuery. `my-dash-app/app_observability.py` also contains manifest parsing helpers. Transform raw artifacts into a memory-efficient flat schema.
- The app entry point must expose the Flask server: `server = app.server`.

Current project structure (key source files; generated and local-only files are noted):

```text
demo-database/
├── .agents/skills/                  # Project task capsules and design skills
├── .github/workflows/ci_pipeline.yml # Offline checks, dbt validation, Cloud Run deployment
├── Scripts/
│   ├── build-auth.mjs               # Builds auth.bundle.js and showcase.bundle.js
│   ├── ingest_bronze.py             # Local CSVs → SQL Server bronze
│   ├── ingest_bigquery.py           # SQL Server bronze → BigQuery
│   ├── ingest_dbt_artifacts.py      # dbt run results → BigQuery audit telemetry
│   ├── create_init_database.sql
│   ├── ddl_table_ingestion_logs.sql
│   └── ddl_create_bronze_*.sql
├── analytics_layer/
│   ├── dbt_project.yml
│   ├── packages.yml
│   ├── package-lock.yml
│   ├── models/
│   │   ├── _sources/
│   │   ├── staging/
│   │   └── marts/
│   ├── analyses/                    # Analytics and audit SQL
│   ├── macros/                      # Custom schema and data tests
│   ├── scripts/
│   │   ├── calculate_coverage.py
│   │   └── load_coverage_to_bq.py
│   ├── src/analytics_layer/
│   └── target/                      # Generated dbt artifacts
├── my-dash-app/
│   ├── app.py                       # Dash/Flask entry point; exposes server
│   ├── auth.py                      # Request guard, public config, session bridge
│   ├── data_loader.py               # Cached dashboard queries and data preparation
│   ├── app_observability.py         # Observability module outside Dash Pages directory
│   ├── theme.py                     # Shared Python chart and color helpers
│   ├── assets/                      # Modular CSS, browser JS, generated bundles
│   │   └── 00-theme.css             # CSS theme tokens
│   ├── auth_frontend/
│   │   ├── main.js
│   │   ├── supabase-client.js
│   │   └── showcase.js
│   ├── templates/
│   │   ├── auth.html
│   │   ├── landing.html
│   │   └── showcase.html
│   ├── components/                  # Sidebar, header, filters, KPIs, panels, revenue chart
│   └── pages/
│       ├── overview.py              # /dashboard
│       ├── customer_360.py          # /customers
│       └── pipeline_health.py       # /pipeline-health
├── utils/                           # Shared root package, imported by app and scripts
│   ├── __init__.py
│   ├── cache.py
│   ├── helpers.py
│   └── audit_logger.py
├── src/demo_database/__init__.py    # Package/CLI scaffold
├── docs/
│   ├── supabase-auth.md
│   └── images/                      # Dashboard screenshots
├── tests/                          # Offline Python regressions and auth browser tests
│   ├── test_auth.py
│   ├── test_dashboard_regressions.py
│   ├── test_revenue_chart.py
│   ├── test_sidebar.py
│   └── auth-browser.test.mjs
├── Notebooks/                      # Exploratory analytics and exported figures
├── logs/query_log.sql
├── run_pipeline.sh                 # Ingestion, dbt execution/tests, artifact upload
├── Dockerfile                      # Node build stage + Python/Gunicorn runtime
├── pyproject.toml
├── uv.lock
├── .python-version
├── package.json
├── package-lock.json
├── .env.example
├── .sqlfluff
├── .sqlfluffignore
├── app.py                          # Deployment trigger placeholder, not the Dash entry point
├── README.md
├── AGENTS.md
└── CLAUDE.md
```

- Run the dashboard with `uv run python my-dash-app/app.py` from the repository root. Docker runs `app:server` from `/app/my-dash-app`.
- Python dependencies belong in root `pyproject.toml`, with resolved versions in `uv.lock`; there is no `my-dash-app/requirements.txt`.
- `utils/` is the shared root Python package. The local `my-dash-app/utils/` and `api_service/` directories contain only cache remnants, not maintained source modules.
- `.venv/`, `node_modules/`, `cache-directory/`, `__pycache__/`, and generated dbt outputs are local/runtime artifacts, not source locations. Keep credentials and `.env` values out of documentation and version control.

## 4. General Architecture
- Never use global variables to store user-specific state. Keep mutable client state in `dcc.Store` or URL parameters.
- Use descriptive, globally unique component IDs, such as `"sales-filter-dropdown"`.
- Load data inside callbacks, not at import time. Avoid module-level data reads or database queries; startup-loaded data will not refresh until the process restarts.
- Use a layout function such as `def serve_layout(): ...` when the layout must be rebuilt on each page load.
- Filter, aggregate, and paginate data in Python or SQL before sending it to graphs or `AgGrid`. Send only the rows or points needed for the current view.
- Pin minimum or exact versions of Dash, Plotly, and component libraries in root `pyproject.toml` and update `uv.lock` when dependencies change.
- Use explicit BigQuery column names, logical filters, and date/time boundaries where applicable. Include a `LIMIT` during structural testing to control scan costs.

## 5. Callbacks, Data, and Performance
- Do not pass massive datasets through `dcc.Store`. Use it only for lightweight state such as IDs, UI toggles, or query filters, with a maximum of 5 MB.
- For large datasets, expensive queries, heavy computations, or API requests, use Flask-Caching and `@cache.memoize()`. Include relevant query parameters in cache keys.
- Fetch the merged dataset through `data_loader.get_prepared_dataset()`. It reuses one process-local copy per cache TTL so a single filter change does not fan out into repeated deserialization. The frame it returns is shared by every caller: treat it as read-only and build derived frames with `filter_dataframe()` or `.copy()` instead of mutating it.
- Monetary columns (`gross_sales_amount`, `unit_price`) are normalized to `float64` at load time. Do not reintroduce `Decimal`/object dtypes into downstream KPI math.
- Ensure every callback `Input`, `Output`, and `State` ID exists in the layout when the callback fires. For dynamic or multi-page layouts, set `suppress_callback_exceptions=True`.
- Use `prevent_initial_call=True` for callbacks that should not run on page load, such as button-triggered actions.
- Return `dash.no_update` when an output should remain unchanged. Use `raise PreventUpdate` when the entire callback should be skipped.
- Keep callbacks focused: prefer one callback per user interaction and split large callbacks into smaller, composable ones.
- Wrap potentially slow components in `dcc.Loading` to show a loading indicator.
- Use background callbacks for work that takes more than a few seconds, with `background=True` and a configured manager such as `manager=background_callback_manager`.
- Return output types appropriate to the component: strings or component lists for `children`, dictionaries for figures, and lists of dictionaries for `AgGrid` `rowData` and `columnDefs`.
- Avoid blocking `time.sleep` loops in callbacks. Use `dcc.Interval` for asynchronous polling or an external task queue for long-running work.
- The in-process dataset cache is a single-slot cache keyed by `limit`, so alternating `limit` values reload the dataset. Keep all callers on one limit unless a distinct size is genuinely required.

## 6. Layout and Styling
- Use the [ui-ux-pro-max skill](/Users/roelsomido/.codex/skills/ui-ux-pro-max/SKILL.md) when designing, building, reviewing, or fixing interfaces. Read the skill before UI work and apply its guidance for accessibility, interaction, responsive layout, typography, color, and visual consistency. Skip it for purely non-visual backend work.
- Follow the skill's scoped workflow: use `--design-system` for new pages or product-wide design and a focused `--domain` search for component changes. Run its search script from the resolved skill directory; adapt guidance to Plotly Dash and preserve the existing shared theme.
- Put core layout styles, grids, and structural overrides in CSS files under `assets/`.
- Use a shared `theme.py` or `theme.js` for color, spacing, and font constants.
- Use inline Python style dictionaries only for dynamic, runtime-computed styling. Avoid static inline style blocks.
- Format Python with `black` and CSS with Prettier.

## 7. Charts and Components
- Prefer `plotly.express`; use `plotly.graph_objects` when fine-grained control is needed.
- Prefer [Dash Bootstrap Components](https://www.dash-bootstrap-components.com/) for supported UI components, imported as `import dash_bootstrap_components as dbc`. Consult the official component documentation and verify props against the installed version before implementation.
- Use Dash Core Components and Dash HTML Components for Dash-specific functionality and semantic structure, and retain Plotly graphs and AG Grid for charts and tables. Use other component libraries only when needed; minimize library mixing.
- Use `dbc.Badge` for KPI trend indicators, preserving readable positive/negative colors, values, and directional cues. Style Bootstrap components with the shared dashboard tokens and CSS under `assets/`.
- Do not use `dash_table.DataTable`; use `dash.AgGrid`.
- When creating `dag.AgGrid`, set these properties:

```python
dashGridOptions = {
    "theme": "themeBalham",
    "animateRows": True,
    "pagination": True,
    "paginationPageSize": 10,
}
columnSize = "responsiveSizeToFit"
defaultColDef = {"filter": True, "sortable": True}
```

## 8. Observability and New Pages
- Do not read `analytics_layer/target/manifest.json` from dynamic layout updates or loop callbacks. Reuse cached manifest dictionaries through a `dcc.Store` where appropriate.
- Page layout functions must return quickly with placeholders or empty grids. Do not run database queries or intensive data loaders inside them.
- Fetch data in callbacks triggered by page or tab selection.
- For multi-tab pages, fetch data only for the active tab and return `dash.no_update` for unselected tab outputs.
- Handle `None` and empty DataFrames without column lookup failures or `IndexError`.

## 9. Avoid Hallucinations and Unsafe Patterns
- Use `app.run`; never use `app.run_server`.
- Do not use `app.validation_layout`. For dynamic layouts, use `suppress_callback_exceptions=True` during app initialization.
- Import callback primitives using modern Dash syntax, for example: `from dash import Input, Output, State, callback, clientside_callback, no_update, ALL, MATCH`.
- Never assign to callback `Input` values or mutate callback arguments in place.
- Never put secrets, API keys, or credentials in layout code or `dcc.Store`. Use environment variables and server-side logic.
- Never run destructive commands against production resources without explicit, multi-turn user confirmation.
- For specialized UI additions, check `.agents/skills/` for a relevant task capsule before implementing.

## 10. Production Safety
- The workspace is connected to the production Google Cloud environment `quantum-echo-data-eng-prod`.
- Never run destructive commands such as `bq rm`, `dbt clean`, or commands that drop production datasets without explicit, multi-turn user confirmation.
- `gcp-key.json` and `.env` are gitignored local credential files. Never commit them, paste their contents into docs, logs, or chat, or reference them from layout code or `dcc.Store`.

## 11. Tests
- Python tests are offline `unittest` suites under `tests/`, discovered from the repository root. They must never construct a production BigQuery client; `tests/test_dashboard_regressions.py` patches `google.cloud.bigquery.Client` to raise on access and stubs `cache.init_app`.
- Run the full Python suite with `.venv/bin/python -B -m unittest discover -s tests -v` from the repository root.
- Run the browser authentication tests with `npm run test:auth` after rebuilding the bundle with `npm run build:auth`.
- When a test needs the dashboard dataset, patch `get_prepared_dataset` with a DataFrame, not the lower-level `load_and_prep_data` tuple. The exception is a test of the cache wrapper itself, which patches `load_and_prep_data` to assert load counts, TTL expiry, and identity reuse.
- Add regression coverage for behavior you change. New caching, dtype, and filter-safety behavior needs a test that fails without the change.

## 12. Authentication & Access Control
- Keep authentication in the existing Dash/Flask application; do not introduce Next.js routing or SSR middleware. See [Supabase authentication setup](docs/supabase-auth.md).
- Register `install_auth(server)` from `my-dash-app/auth.py` before constructing Dash so authorization runs before Dash request hooks, data callbacks, and exports.
- Serve `/login`, `/signup`, and `/auth/callback` as Flask-rendered pages outside the dashboard layout. Product Overview lives at `/dashboard`; authenticated `/` requests redirect there. Keep navigation and route-dependent callbacks consistent.
- Email/password signup requires email confirmation. Google and GitHub OAuth use PKCE and require separately enabled/configured providers in Supabase. Never assume a rendered provider button means the provider is enabled.
- Verify access tokens against Supabase Auth on every protected request, then require a confirmed email on the case-insensitive, exact-email `AUTH_ALLOWED_EMAILS` allowlist. An empty allowlist denies everyone. Never authorize from client state, editable metadata, or unverified JWT claims.
- Keep the public route/asset allowlist explicit. `/auth/config` exposes only the public project URL and anon key; `/auth/session` POST validates the token and sets the access cookie, while DELETE clears it. Authentication endpoints must remain usable before a session exists.
- Require exact `Origin` matching for mutations. Cookies must be HttpOnly and SameSite=Lax, with Secure enabled except for explicitly configured HTTP localhost development. Preserve `private, no-store` response headers.
- Keep refresh tokens managed by Supabase JS. Never put access/refresh tokens, provider secrets, or the approval allowlist in `dcc.Store`, logs, templates, or browser configuration.
- Wait for session synchronization before releasing Dash data requests or revealing the dashboard. Preserve token refresh, sign-out across tabs, callback error recovery, and visible startup failure states. Do not automatically replay rejected mutations.
- Return 401 for invalid sessions, 403 for denied access, and 503 for configuration/service failures; fail closed before data loaders run. Redirect unauthorized page navigation to `/login`.
- Read `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `AUTH_APP_ORIGIN`, and `AUTH_ALLOWED_EMAILS` from root `.env` locally or the deployment environment. Runtime environment values take precedence. Use only the public anon key in browser configuration; never a service-role key.
- Keep browser and server pointed at the same Supabase project. The default build uses `/auth/config` at runtime; optional build-time public values override it. Leave build-time values unset for portable Docker/CI builds.
- Distinguish Google Cloud's authorized redirect URI (`https://<project-ref>.supabase.co/auth/v1/callback`) from Supabase's allowed app redirect URLs (`<app-origin>/auth/callback`). Do not substitute one for the other.
- Edit `auth_frontend/` sources, then run `npm ci` and `npm run build:auth`. Never fix authentication by editing only the generated bundle or disabling the server guard. Exclude the bundle from Dash auto-injection and load it exactly once through the index template.
- Commit the backend, templates, CSS, frontend sources, generated tracked bundle, package manifests, build script, and Docker integration together. Docker builds the bundle in a Node stage and runs only Python/Gunicorn in the final image.
- After auth changes, run `.venv/bin/python -B -m unittest discover -s tests -v` and `npm run test:auth`. Verify unauthenticated page/data access, approval and confirmation checks, expiry/refresh, logout, OAuth errors, and loading states without querying production BigQuery or creating real accounts.

## 13. Parallel Development & Integration Policy

### 13.1 Scope, precedence, and actual capabilities

- Sections 1–12 remain in force for every role and worktree. This section adds coordination rules; it does not relax architecture, authentication, production safety, credential handling, or testing requirements. If a task or integration plan conflicts with an existing requirement, report the conflict before acting.
- `AGENTS.md` is policy, not an executable scheduler, a filesystem lock, or merge authorization. It does not itself launch sessions, assign tasks, configure Agent Manager, run checks, merge branches, or enforce permissions.
- Kilo Agent Manager supports isolated worktree sessions. Its extension `agent_manager` tool can orchestrate sessions when available and permitted; otherwise the user must perform the session-management steps. Check the installed version and available tools before promising automation.
- Separate sessions inside the same worktree share files, branch, and terminal state. Use separate worktrees for concurrent writers. Independent Agent Manager sessions do not automatically share a Swarm board; maintain explicit coordination records and deliver updates to the affected sessions.
- Automated integration requires a scoped user instruction, an assigned integrator, available Git/Agent Manager tools, and permission to perform the proposed operations. Record that authorization once; do not ask again for routine actions already covered by it. This file alone grants no authorization to push, merge PRs, promote to `main`, deploy, delete worktrees/branches, or access production.

### 13.2 Roles and single-writer rule

- **Coordinator:** Decompose work, identify dependencies and shared contracts, assign ownership, communicate decisions, and maintain the authoritative task/integration queue. The coordinator may also serve as integrator, but must perform both roles' checks.
- **Worker:** Implement only its assigned task in its recorded worktree, preserve existing requirements, run checks, and deliver a handoff tied to an exact commit. Workers do not integrate their own branches into `integration` or `main`.
- **Integrator:** Review handoffs and diffs, integrate ready commits in dependency order, resolve only unambiguous conflicts, verify the combined result, and record acceptance or failure. Only one integrator may write the integration target at a time.
- **User:** Decide unresolved business/architecture conflicts and authorize release, production operations, or cleanup where not already authorized.
- Never edit another active worker's checkout, switch its branch, reset its state, or run commands in its terminal. Send the requested change to its owner. Read-only inspection is allowed.

### 13.3 Plan and task ownership before launching workers

Use `integration` as the intended development base and integration target for this workflow. Confirm it exists and identify its upstream; do not silently substitute `main` or create/reset it from an assumed baseline. Existing branch restrictions and remote protections still apply.

Before parallel editing, create one authoritative batch record in the coordinator's checkout, for example `docs/agent-work/<batch-id>.md`. Only the coordinator/integrator writes that record. Workers send updates through session messages; they must not create competing copies of the queue in their branches. Do not store secrets in records or prompts.

Record the following for each task and include it in the worker's launch prompt:

```text
Batch / task ID:
Objective and acceptance criteria:
Owner / Agent Manager session ID:
Branch / absolute worktree path:
Base branch / remote / exact base commit:
Owned paths (including specific tests):
Allowed shared-file edits and designated owner:
Out-of-scope paths and behavior:
Dependencies / required commit or contract version:
Interface contract (IDs, columns/dtypes, function signatures, routes):
Required checks and safe test environment:
Allocated ports / caches / temporary resources:
Authorized operations (commit, push, integration target, cleanup):
Status / handoff commit / blockers:
```

- Parallelize tasks with disjoint edits and compatible contracts. Serialize dependencies or agree an explicit interface first; do not guess another worker's unfinished implementation.
- Assign tests as well as application files. Two workers editing `tests/test_dashboard_regressions.py` still overlap even when their page files differ.
- Keep task scope narrow. Start with a small batch; increase concurrency only when review and integration can keep up. A dependency blocked worker may do independent read-only investigation, but must not claim the dependent task is complete.
- Use explicit statuses: `planned`, `running`, `blocked`, `ready-for-review`, `integrating`, `verification-failed`, `integrated`, `closed`. Worker completion means ready for review; only the integrator declares integration successful.

### 13.4 Shared files and cross-task contracts

- Default to one owner per shared file per batch. Treat `AGENTS.md`, `CLAUDE.md`, root `utils/`, `my-dash-app/app.py`, `auth.py`, `data_loader.py`, `app_observability.py`, `theme.py`, `assets/00-theme.css`, shared components, dependency manifests/locks, `Dockerfile`, CI, `run_pipeline.sh`, and dbt project/package/source definitions as coordination-sensitive. This list supplements each task's explicit path ownership.
- Before changing a shared file outside the assignment, send the coordinator the exact path, required change, affected consumers, and dependency impact. Continue independent in-scope work while ownership is resolved. The coordinator either expands the assignment explicitly or assigns a separate prerequisite task; silence is not approval.
- Ownership records are procedural agreements, not automatic locks. Confirm there is no concurrent writer before changing a shared checkout. Avoid repository-wide formatting, mass renames, and unrelated cleanup during parallel batches.
- Agree contracts for Dash component IDs/callback outputs, prepared dataset columns and dtypes, cache keys/TTL behavior, authentication routes/response codes, and dbt model/source schemas before dependent work. Notify consumers when a contract changes; update their task records and tests.
- Assign dependency changes to one owner. Regenerate each lockfile with its normal tool from the resolved manifest; do not manually splice conflicting lockfile contents. Preserve the existing rule to build tracked auth bundles from frontend sources and commit the related integration files together.
- Shared-file ownership does not authorize bypassing authentication, changing production schemas, or weakening tests. Architectural or safety conflicts require escalation.

### 13.5 Branch and worktree lifecycle

1. Inspect repository status, current branch, upstream, existing worktrees, and any merge/rebase in progress. Preserve pre-existing user changes. Do not reset, clean, or overwrite a checkout to make it usable.
2. In the primary repository, configure the project's Agent Manager Default Base Branch as `integration`, or explicitly select it when creating each worktree. This is a separate Agent Manager setting; this document does not set it. Verify the actual branch and base commit after creation.
3. Use one unique task branch and managed worktree per worker, for example `agent/<batch-id>/<task-id>`. Record the actual path; do not assume the directory name equals the branch name. Never check out a branch already in use by another worktree or make direct worker commits on `main` or `integration`.
4. Establish a known current base without destructive resets. If the local base and its upstream diverge, resolve the intended source before launching work. Prefer the same recorded baseline for independent tasks; launch dependent tasks from the verified integration result that contains their prerequisite.
5. Prepare each worktree using existing project setup conventions and Python 3.12/uv and Node 22+/npm requirements. Keep credentials local and server-side; never copy secret files into tracked paths or print their contents. A setup script may prepare dependencies, but must not run ingestion, deployment, database writes, or `run_pipeline.sh` by default.
6. Allocate unique local ports, writable cache directories, test outputs, container names, and temporary resources where supported. FileSystemCache paths must not collide across concurrent runs. Redis caches need a supported per-worktree namespace or isolated test instance. Do not modify production cache state or shared cloud resources to simulate isolation.
7. Commit only reviewed task files; inspect staged changes and exclude secrets, runtime artifacts, and unrelated edits. Preserve the project's explicit requirements for tracked generated auth bundles. No force pushes, destructive resets, or Git stash in worktrees: stashes are shared across the repository. Prefer clean task commits; if a temporary recovery commit/copy is necessary, record and verify it and keep unfinished work out of accepted integration commits.
8. When the base advances, coordinate an update at a safe checkpoint. `/update-from-base` uses a managed worktree's saved base; verify it is the intended `integration` source. Changing the default setting or diff comparison base does not change an existing worktree's saved base. For local-only/unpublished integration commits, explicitly establish the correct source rather than assuming a fetched remote contains them. Preserve and verify staged, unstaged, and untracked edits before updating; stop if preservation cannot be verified.
9. After any update or worker revision, rerun affected checks and issue a new handoff commit. Previous validation does not certify the new commit. Check Kilo's push-related settings before invoking updates; do not allow automatic push behavior beyond the recorded authorization.

### 13.6 Worker handoff

Freeze the submitted commit while it is reviewed. If further work is needed, notify the integrator and submit a new SHA rather than silently moving the accepted branch head.

```text
Task / owner / session:
Branch / worktree / base SHA / submitted head SHA:
Acceptance criteria met:
Changed files and purpose:
Shared contracts / dependency / generated-file changes:
Required predecessor tasks and commit SHAs:
Exact check commands, results, and tested SHA:
Skipped or unavailable checks and reason:
Manual verification and safe environment used:
Known limitations / conflicts / production impact:
Working tree clean? Outstanding edits/untracked files:
Rollback considerations / resources retained:
Requested next action:
```

- Run all task-relevant checks from sections 11 and 12 and the existing CI configuration. Include meaningful regression coverage required by section 11. Do not disable a failing guard, delete a test, or replace a failure with a success claim.
- Separate reproducible baseline failures from newly introduced failures and provide evidence. A skipped check, unavailable runtime, missing dependency, or unavailable credentials is not a passing check.
- A handoff may report a blocker without committing incomplete work as ready. Do not send credential contents or production data as evidence.

### 13.7 Serialized automated integration

The integrator may execute this sequence without repeated confirmation when the user has already authorized the batch and target. Workers' passing checks are necessary evidence; the combined tree needs its own verification.

1. Confirm scope, target, merge method, permission, ownership, and a clean integration checkout. Inspect each handoff's exact commits and diff, including unexpected files, secrets, shared contracts, missing generated outputs, and dependencies. Do not integrate a branch that has moved beyond its submitted SHA without a refreshed handoff.
2. Record the target's current SHA and order tasks by prerequisites, integrating foundational changes first. Reject out-of-scope or incomplete work rather than silently dropping hunks. Do not mix Apply to local, cherry-picking, and branch merging for the same contribution.
3. Prefer an isolated candidate branch/worktree such as `integrate/<batch-id>` created from the recorded current `integration` SHA. Merge each accepted submitted commit there using the agreed merge method; do not pull an unchecked moving branch head. Keep the integration queue single-writer.
4. After each merge, inspect the combined diff and run affected checks. For ordinary integration fixes within the authorized scope, preserve both tasks' intended behavior, commit the fix separately, record it, and rerun checks. If an intent decision or unsafe operation is required, follow section 13.8.
5. Before accepting the candidate, run the full verification gate in section 13.9 on its exact head. Mark failures as `verification-failed` and retain the candidate for diagnosis; do not promote it.
6. Recheck the actual `integration` head immediately before promotion. If it changed, incorporate the new target into the candidate and rerun the gate on the new combined head. If unchanged and authorized, fast-forward `integration` to the verified candidate. Coordinate checkout ownership; do not switch or update a branch being edited by another session. If fast-forward is unavailable, stop and reassess instead of resetting the target.
7. Record the resulting SHA, accepted task SHAs, conflict resolutions, checks, and remaining blockers. A push to the integration upstream needs existing authorization and must respect protections/CI. PR merges and GitHub auto-merge are separate configured operations, not consequences of this policy.
8. Keep `integration` → `main`, release, Cloud Run deployment, and production changes outside routine batch integration unless the user explicitly authorizes them. Inspect whether a push would trigger deployment in existing CI before treating it as a routine remote update.

An explicitly authorized direct-to-`integration` workflow may be used instead of a candidate branch. Preserve a recoverable pre-merge SHA, verify after each merge, and stop subsequent integration on failure. Use a reviewed revert when authorized if recovery is needed; never rewrite a shared target with a reset or force push.

### 13.8 Conflict handling and escalation

- Resolve a textual conflict autonomously only when both intents and the correct combined behavior are clear from the tasks, contracts, and tests. Inspect the full affected behavior, not just conflict markers. Never choose all `ours`/`theirs` merely to make Git finish.
- Resolve generated-file conflicts by reconciling sources and rebuilding with the existing toolchain. Recheck the resulting changes. A clean merge can still break callback wiring, schemas, data types, cache behavior, or authorization.
- Stop the affected merge for incompatible business logic or API/schema contracts, ambiguous ownership, auth/allowlist/cookie changes with unclear intent, destructive production operations, or unexplained failing checks. Continue unrelated safe tasks only if they do not depend on the blocked result.
- Report task IDs, branches/SHAs, affected paths, each side's intended behavior, failure evidence, recovery state, and the smallest decision needed. Keep secrets out of reports.
- Preserve the conflict state for inspection or abort only the merge initiated by this integrator after verifying recoverability. Do not abort another session's pre-existing operation, discard user edits, or mark the task integrated while conflicts remain.

### 13.9 Integration verification gate

Run checks from the repository root of the combined candidate. Preserve the existing commands exactly:

```bash
.venv/bin/python -B -m unittest discover -s tests -v
npm run build:auth
npm run test:auth
```

- The full offline Python suite is required for every accepted batch. Keep the production BigQuery client guard and cache stubs intact. Build the auth bundle before running browser authentication tests; verify whether rebuilding leaves tracked bundle changes, and include required changes before certifying the final SHA.
- For auth work, also follow all section 12 checks: unauthenticated page/data access, confirmation and approval, expiry/refresh, logout, OAuth errors, and loading states without production BigQuery queries or real-account creation.
- Run applicable existing CI, formatting, and dbt validation checks using the repository's actual configured commands. Inspect `.github/workflows/ci_pipeline.yml` first; do not invent commands or blindly run deployment steps locally. dbt checks must use a verified safe target. Do not execute `dbt clean`, ingestion, artifact upload, `run_pipeline.sh`, or production-connected dashboard queries as routine verification.
- Check the combined Dash component IDs, callback inputs/outputs, page routes, prepared-data contracts, read-only shared frames, dtypes, cache behavior, auth ordering, and any dbt producer/consumer contracts affected by the batch. Use offline fixtures/mocks; visually verify UI changes when relevant.
- Inspect final status and diff for conflict markers, unrelated changes, credentials, generated/runtime artifacts, and unintended dependency churn. Confirm acceptance criteria and record the exact tested head SHA, command outcomes, and remaining limitations.
- If a required check cannot run, report the batch as awaiting verification and retain its worktrees. Do not promote it as verified. Any changes after the gate require relevant checks again; a changed target requires checks on the new combined result.

### 13.10 Cleanup and recovery

- Treat cleanup as a separate recorded step after successful integration and any required remote acceptance. Completion alone is not permission to delete a worktree or branch.
- Before authorized cleanup, stop its sessions/processes, verify staged/unstaged/untracked files, confirm accepted work exists in the target, and preserve any unmerged work and required recovery references. For squash/rebase integrations, verify accepted changes explicitly rather than relying only on Git ancestry.
- Use Agent Manager's managed lifecycle for managed worktrees. Check the installed version's close behavior and confirmation: official documentation differs on whether closing also deletes the local branch. Assume closing may delete both checkout and branch until verified. Preserve needed commits in a recovery ref outside the potentially deleted branch before closing. Never remove `.kilo/worktrees/` directories manually while registered or active.
- Delete remote branches only when separately authorized and no task/PR still needs them. Do not delete `main`, `integration`, or another agent's branch.
- Clean up only the task's allocated local resources. Worktree closure does not imply external containers, caches, databases, or cloud resources are removed. Production cleanup still requires the explicit, multi-turn confirmation in sections 9 and 10.
- Finish the batch record with integrated SHAs, verification evidence, retained recovery refs, cleanup actions, and any unresolved tasks.

### 13.11 Kilo capability references

Documentation checked on 2026-10-08; verify against the installed extension before using version-dependent actions:

- [Agent Manager](https://kilo.ai/docs/automate/agent-manager): project base settings, isolated/shared sessions, recorded-base updates, orchestration tools, and managed lifecycle.
- [Agent Manager Workflows](https://kilo.ai/docs/automate/agent-manager-workflows): integration choices, dependency ordering, shared-worktree coordination, Swarm boundaries, and stash cautions.

These references describe available mechanisms. The ownership, authorization, verification, and cleanup requirements above are project policy and must be carried out by an assigned agent or the user.
