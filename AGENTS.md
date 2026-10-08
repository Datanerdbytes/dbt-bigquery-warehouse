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
│   ├── banner-design/
│   ├── brand/
│   ├── design-system/
│   ├── design/
│   ├── loading-spinner/
│   ├── slides/
│   ├── ui-styling/
│   └── ui-ux-pro-max/
├── .claude/skills/loading-spinner.md
├── .github/workflows/ci_pipeline.yml # Offline checks, dbt validation, Cloud Run deployment
├── .kilocode/tasks/                 # Remediation task capsules
├── .dockerignore
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── .python-version
├── .secrets.baseline
├── .sqlfluff
├── .sqlfluffignore
├── .vscode/settings.json
├── Scripts/
│   ├── __init__.py
│   ├── build-auth.mjs               # Builds auth.bundle.js and showcase.bundle.js
│   ├── create_init_database.sql
│   ├── ddl_create_bronze_crm_cust_info.sql
│   ├── ddl_create_bronze_crm_prd_info.sql
│   ├── ddl_create_bronze_crm_sales_details.sql
│   ├── ddl_create_bronze_erp_cust_az12.sql
│   ├── ddl_create_bronze_erp_loc_a101.sql
│   ├── ddl_create_bronze_erp_px_cat_g1v2.sql
│   ├── ddl_table_ingestion_logs.sql
│   ├── ingest_bronze.py             # Local CSVs → SQL Server bronze
│   ├── ingest_bigquery.py           # SQL Server bronze → BigQuery
│   └── ingest_dbt_artifacts.py      # dbt run results → BigQuery audit telemetry
├── analytics_layer/
│   ├── .gitignore
│   ├── README.md
│   ├── dbt_project.yml
│   ├── packages.yml
│   ├── package-lock.yml
│   ├── analyses/                    # Analytics and audit SQL
│   │   ├── .gitkeep
│   │   ├── create_schema.sql
│   │   ├── cummulative_sales.sql
│   │   ├── customer_segment.sql
│   │   ├── date.sql
│   │   ├── ddl_metric_audit_sql_server.sql
│   │   ├── magnitude.sql
│   │   ├── metric_audit.sql
│   │   ├── product_performance.sql
│   │   ├── product_segment.sql
│   │   ├── rank.sql
│   │   ├── rpt_customer_360.sql
│   │   ├── sales_distribution.sql
│   │   ├── sales_performance.sql
│   │   ├── test_referential_integrity.sql
│   │   └── v_latest_pipeline_health.sql
│   ├── macros/                      # Custom schema and data tests
│   │   ├── .gitkeep
│   │   ├── get_custom_schema.sql
│   │   ├── test_is_clean_trimmed.sql
│   │   ├── test_is_date_before.sql
│   │   └── test_is_date_before_columns.sql
│   ├── models/
│   │   ├── _sources/
│   │   │   └── _sources.yml
│   │   ├── staging/
│   │   │   ├── _staging__models.yml
│   │   │   ├── stg_crm_cust_info.sql
│   │   │   ├── stg_crm_prd_info.sql
│   │   │   ├── stg_crm_sales_details.sql
│   │   │   ├── stg_erp_cust_az12.sql
│   │   │   ├── stg_erp_loc_a101.sql
│   │   │   └── stg_erp_px_cat_g1v2.sql
│   │   └── marts/
│   │       ├── _marts_models.yml
│   │       ├── dim_customers.sql
│   │       ├── dim_products.sql
│   │       ├── fct_sales.sql
│   │       └── product_360.sql
│   ├── seeds/                        # .gitkeep
│   ├── snapshots/                    # .gitkeep
│   ├── scripts/
│   │   ├── calculate_coverage.py
│   │   └── load_coverage_to_bq.py
│   ├── src/analytics_layer/
│   │   └── __init__.py
│   └── target/                      # Generated dbt artifacts
├── my-dash-app/
│   ├── app.py                       # Dash/Flask entry point; exposes server
│   ├── app_observability.py         # Observability module; registers /observability page
│   ├── auth.py                      # Request guard, public config, session bridge
│   ├── data_loader.py               # Cached dashboard queries, data prep, BQ init
│   ├── theme.py                     # Shared Python chart and color helpers
│   ├── assets/                      # Modular CSS, browser JS, generated bundles
│   │   ├── 00-theme.css             # CSS theme tokens
│   │   ├── 01-base.css
│   │   ├── 02-sidebar.css
│   │   ├── 03-header.css
│   │   ├── 04-filters.css
│   │   ├── 05-kpi-cards.css
│   │   ├── 06-components.css
│   │   ├── 08-auth.css
│   │   ├── 09-account-menu.js
│   │   ├── 09-revenue-chart.css
│   │   ├── auth.bundle.js           # Generated by build-auth.mjs
│   │   └── showcase.bundle.js       # Generated by build-auth.mjs
│   ├── auth_frontend/
│   │   ├── main.js
│   │   ├── showcase.js
│   │   └── supabase-client.js
│   ├── components/                  # Sidebar, header, filters, KPIs, panels, revenue chart
│   │   ├── filter_bar.py
│   │   ├── header.py
│   │   ├── kpi_bar.py
│   │   ├── panels.py
│   │   ├── revenue_chart.py
│   │   └── sidebar.py
│   ├── pages/
│   │   ├── overview.py              # /dashboard
│   │   ├── customer_360.py          # /customers
│   │   └── pipeline_health.py       # /pipeline-health
│   │   # (app_observability.py registers the /observability page outside pages/)
│   ├── templates/
│   │   ├── auth.html
│   │   ├── landing.html
│   │   └── showcase.html
│   └── cache-directory/             # Flask-Caching FileSystemCache (runtime write path)
├── utils/                           # Shared root package, imported by app and scripts
│   ├── __init__.py
│   ├── audit_logger.py              # Primary audit logger
│   ├── cache.py
│   ├── helpers.py
│   ├── logging_config.py
│   └── touch                        # Legacy module superseded by audit_logger.py
├── src/demo_database/__init__.py    # Package/CLI scaffold
├── docs/
│   ├── supabase-auth.md
│   └── images/                      # Dashboard screenshots
│       ├── customer_360.png
│       ├── export_modal.png
│       ├── pipeline_health.png
│       └── product_overview.png
├── tests/                          # Offline Python regressions and auth browser tests
│   ├── auth-browser.test.mjs
│   ├── test_auth.py
│   ├── test_bq_hardcoding_remediation.py
│   ├── test_dashboard_regressions.py
│   ├── test_ingest_bigquery_sql_injection.py
│   ├── test_manifest_path_safety.py
│   ├── test_revenue_chart.py
│   └── test_sidebar.py
├── Notebooks/                      # Exploratory analytics and exported figures
│   ├── Best_Selling_Products.png
│   ├── Executive_Performance_Dashboard.png
│   ├── bq_cost_metrics_test.ipynb
│   ├── cummulative_sales.ipynb
│   ├── customer_performance.ipynb
│   ├── customer_segment.ipynb
│   ├── load_customer_info.ipynb
│   ├── product.ipynb
│   └── sales_distribution.ipynb
├── logs/
│   ├── dbt.log
│   └── query_log.sql
├── run_pipeline.sh                 # Ingestion, dbt execution/tests, artifact upload
├── Dockerfile                      # Node build stage + Python/Gunicorn runtime
├── pyproject.toml
├── uv.lock
├── requirements.txt                # Autogenerated by uv
├── package.json
├── package-lock.json
├── .env.example
├── app.py                          # Deployment trigger placeholder, not the Dash entry point
├── README.md
├── AGENTS.md
└── CLAUDE.md
```

- Run the dashboard with `uv run python my-dash-app/app.py` from the repository root. Docker runs `app:server` from `/app/my-dash-app`.
- Python dependencies belong in root `pyproject.toml`, with resolved versions in `uv.lock`; there is no `my-dash-app/requirements.txt`.
- `utils/` is the shared root Python package. The local `my-dash-app/utils/`, `my-dash-app/cache-directory/`, and `api_service/` directories contain only cache remnants, not maintained source modules.
- `.venv/`, `node_modules/`, `__pycache__/`, and generated dbt outputs (`analytics_layer/target/`) are local/runtime artifacts, not source locations. Keep credentials and `.env` values out of documentation and version control.

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
