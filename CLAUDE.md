# Agent Context & Rules

## 1. Project Overview
- **Project Name:** Data Analytics Dashboard
- **Core Purpose:** An interactive multi-page dashboard to visualize live data tables from Google BigQuery and provide an analytics layer pipeline monitoring console.
- **Target Audience:** Internal business analysts, data engineers, and stakeholders.

## 2. Tech Stack & Environment
- **Language:** Python 3.[X]
- **Core Framework:** Plotly Dash (Multi-page via `dash.register_page` architecture)
- **Underlying Engine:** Flask (Used for server-side configurations and Flask-Caching)
- **Data Engine:** Google BigQuery (Live connection via Application Default Credentials) & dbt Artifact Telemetry
- **Data Libraries:** `google-cloud-bigquery`, `pandas`, `pandas-gbq`, `pyarrow`, `json`
- **Caching Framework:** `Flask-Caching` (Configured via FileSystemCache or Redis)
- **Styling:** Dash Bootstrap Components (DBC) + Modular CSS layout overrides
- **Code Formatters:** `black` for Python formatting, Prettier for CSS formatting

## 3. Architecture & File Structure
- **Application Structure:** Multi-page app using native `dash.register_page` architecture.
- **Data Flow:** `utils/data_loader.py` initializes the BigQuery client securely using GCP Application Default Credentials (ADC). Specific data-fetching functions are optimized with server-side caching (`@cache.memoize`) to return Pandas DataFrames efficiently. Layouts pull data inside callbacks or via a layout function, feeding into local browser memory (`dcc.Store`) or UI interfaces. 
- **Observability Data Flow:** Pipeline observability telemetry is evaluated by loading and processing metadata from `analytics_layer/target/manifest.json`. Raw contents must be transformed into a memory-efficient flat schema during application execution or layout building to ensure stable page responsiveness.
- **Directory Layout:**

# Directory Structure: demo-database

```text
demo-database/
├── .venv/                      # Python virtual environment
├── Scripts/                    # Data ingestion & DDL scripts
│   ├── ingest_bronze.py        # Bronze layer ingestion to BigQuery
│   ├── ingest_bigquery.py      # BigQuery load utilities
│   ├── ingest_dbt_artifacts.py # dbt artifact ingestion (manifest.json, run_results.json)
│   └── ddl_create_bronze_*.sql # DDL for bronze tables
├── analytics_layer/            # dbt project (analytics_layer profile)
│   ├── models/                 # dbt models (staging → marts)
│   │   ├── staging/            # Silver layer (cleaned/transformed)
│   │   └── marts/              # Gold layer (business-ready)
│   └── target/                 # dbt compile artifacts (manifest.json)
├── my-dash-app/                # Plotly Dash application
│   ├── assets/                 # Custom CSS styling sheets (auto-loaded by Dash)
│   ├── components/             # Reusable UI component modules
│   │   ├── filter_bar.py
│   │   ├── header.py
│   │   ├── kpi_bar.py
│   │   └── sidebar.py
│   ├── pages/                  # Individual dashboard layout modules (dash.register_page)
│   │   ├── overview.py         # Main overview dashboard
│   │   ├── customer_360.py     # Customer 360 detail page
│   │   └── pipeline_health.py  # Pipeline observability page
│   ├── utils/                  # Utility modules (cache config, helpers)
│   │   ├── cache.py            # Flask-Caching configuration
│   │   └── helpers.py          # DataFrame filtering helpers
│   ├── app.py                  # Main entry point: Dash init, cache, layout shell
│   ├── app_observability.py    # Standalone observability app (manifest parsing, lineage)
│   ├── data_loader.py          # BigQuery data fetchers with @cache.memoize
│   └── requirements.txt        # Pinned Python dependencies
├── AGENTS.md                   # This file (Global agent-specific rules)
├── CLAUDE.md                   # Comprehensive instruction file
└── Notebooks/                  # Jupyter notebooks for exploration
```
## 4. General Architecture & Standards
- **Global Variables**: Never use global variables to store user-specific state. All mutable state must live in the client browser using `dcc.Store` or URL parameters to maintain thread safety.
- **Server Variable**: Make sure the app file always exposes a server variable: `server = app.server`
- **Dash Pages**: Use `dash.page_registry`, keep all pages in a `pages/` directory, and register each page with `dash.register_page(__name__)`.
- **App IDs**: Prefer descriptive IDs like `"sales-filter-dropdown"` or `"observability-node-selector"` over `"dropdown-1"`. IDs must be unique across the entire app, including all pages.
- **Loading Data**: Load data inside callbacks, not at import time. Avoid `df = pd.read_csv(...)` or database fetches at the module level. Fetch or refresh data inside the callback that needs it.
- **Server-side Filtering**: Filter, aggregate, and paginate data in Python/SQL before passing it to graphs or `AgGrid`. Only send the rows or points needed for the current view to the client.
- **Pin Dependencies**: Specify minimum or exact versions for `dash`, `plotly`, and component libraries in `requirements.txt` to avoid breaking changes on deploy.

## 5. Callbacks & Optimization
- **Dataset Size**: Do not pass massive datasets through `dcc.Store` if they can be cached server-side. Use `dcc.Store` only for lightweight state (IDs, UI toggles, query filters, parsed dbt metadata objects) with a maximum of 5MB.
- **Caching**: Implement server-side caching using `flask_caching`. Decorate data-fetching operations inside `utils/data_loader.py` with the `@cache.memoize()` pattern. Ensure the cache key includes relevant query parameters.
- **BigQuery Query Efficiency**: BigQuery charges by data scanned. The AI must always use explicit column names instead of `SELECT *`, apply logical `WHERE` filters, and implement date/time boundaries where applicable.
- **Observability State Efficiency**: Always look up cached manifest dictionaries inside a `dcc.Store` module. Never programmatically trigger file read tasks to `analytics_layer/target/manifest.json` from within a dynamic layout update or loop callback.
- **Input IDs**: Every `Input`, `Output`, and `State` ID referenced in a callback must be present in the layout when the callback fires. Set `suppress_callback_exceptions = True` on app initialization for multi-page routing layout safety.
- **Prevent Callback Firing**: Apply `prevent_initial_call=True` in callback decorators that should not run on page load (e.g., actions triggered only by a button click).
- **Prevent Unnecessary Updates**: When a callback should leave an output unchanged, return `dash.no_update` instead of raising a `PreventUpdate` exception, unless halting the entire chain is explicitly desired.

## 6. Antigravity CLI Operations & Safety
- **Production Safety Guidelines**: The active workspace is connected to a production Google Cloud environment (`quantum-echo-data-eng-prod`). The agent must NEVER run destructive commands (e.g., `bq rm`, `dbt clean`, or dropping production datasets) without explicit, multi-turn user confirmation.
- **Resource Constraints**: When writing BigQuery SQL queries inside Python callbacks or scripts, the agent must enforce maximum optimization. Always include a `LIMIT` clause during structural testing to control data processing scan bills.
- **Progressive Skill Delegation**: For specialized UI component additions, the agent should search the `.agents/skills/` directory for dedicated task capsules (like `/loading-spinner`) rather than trying to build raw script logic directly into the global app space.