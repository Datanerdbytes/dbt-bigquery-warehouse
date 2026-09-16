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

```
demo-database/
├── .venv/                      # Python virtual environment
├── Scripts/                    # Data ingestion & DDL scripts
│   ├── ingest_bronze.py        # Bronze layer ingestion to BigQuery
│   ├── ingest_bigquery.py      # BigQuery load utilities
│   ├── ingest_dbt_artifacts.py # dbt artifact ingestion (manifest.json, run_results.json)
│   └── ddl_create_bronze_*.sql # DDL for bronze tables
├── analytics_layer/            # dbt project (analytics_layer profile)
│   ├── analyses/               # dbt analyses (SQL files for reporting)
│   │   ├── v_latest_pipeline_health.sql  # Pipeline health view
│   │   └── *.sql               # Other analytical queries
│   ├── macros/                 # Custom dbt macros
│   ├── models/                 # dbt models (staging → marts)
│   │   ├── _sources/           # Source definitions
│   │   │   └── _sources.yml    # Bronze layer source configs with tests
│   │   ├── staging/            # Silver layer (cleaned/transformed)
│   │   │   ├── _staging__models.yml  # Staging model configs with column tests
│   │   │   └── stg_*.sql       # Staging models
│   │   └── marts/              # Gold layer (business-ready)
│   │       ├── _marts_models.yml     # Mart model configs with column tests
│   │       └── *.sql           # dim_*, fct_*, product_360.sql
│   ├── scripts/                # Python scripts for dbt artifacts
│   │   ├── calculate_coverage.py     # Parse manifest.json → test coverage
│   │   └── load_coverage_to_bq.py    # Load coverage to BigQuery
│   ├── seeds/                  # dbt seed files (static reference data)
│   ├── snapshots/              # dbt snapshots (SCD Type 2)
│   ├── src/                    # dbt project source (if any)
│   ├── tests/                  # dbt test definitions (generic tests)
│   ├── dbt_project.yml         # dbt project configuration
│   ├── packages.yml            # dbt package dependencies
│   └── target/                 # dbt compile artifacts (manifest.json, run_results.json)
├── my-dash-app/                # Plotly Dash application
│   ├── assets/                 # Custom CSS styling sheets (auto-loaded by Dash)
│   │   ├── 01-base.css
│   │   ├── 02-sidebar.css
│   │   ├── 03-header.css
│   │   ├── 04-filters.css
│   │   ├── 05-kpi-cards.css
│   │   └── 06-components.css
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
│   ├── AGENTS.md               # This file (agent-specific instructions)
│   ├── CLAUDE.md               # Comprehensive context, rule, and instruction file
│   ├── app.py                  # Main entry point: Dash init, cache, layout shell
│   ├── app_observability.py    # Standalone observability app (manifest parsing, lineage)
│   ├── data_loader.py          # BigQuery data fetchers with @cache.memoize
│   └── requirements.txt        # Pinned Python dependencies
├── src/                        # Additional Python packages
│   └── demo_database/          # Package root
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
- **Prevent Unnecessary Updates**: When a callback should leave an output unchanged, return `dash.no_update` instead of re-fetching or re-computing data. Use `raise PreventUpdate` to skip updating the entire callback.
- **Keep Callbacks Focused**: One callback per user interaction when possible. Split large callbacks into smaller, composable ones rather than updating many outputs from a single function.
- **Loading Spinners**: Show a spinner while data is loading by wrapping components that may be slow to update with `dcc.Loading`.
- **Background Callbacks**: Use background callbacks for long-running work. For tasks that take more than a few seconds, use `background=True` in the callback decorator.

## 6. Layout, Styling & Components
- **Custom Style Sheets**: Keep modular presentation layers organized inside files within the `assets/` directory.
- **Inline Styles**: Use inline Python dictionaries (`style={"marginRight": "10px"}`) only for highly dynamic, runtime-computed values. Avoid static inline styling blocks.
- **Graphing Library**: Use `plotly.express` for charts first—it is simpler and covers most use cases. Switch to `plotly.graph_objects` (`go`) only when you need fine-grained control, such as implementing dual-axis or combo charts.
- **Data Tables**: Do not use `dash.datatable`; use `dash.AgGrid` instead.
- **AgGrid Configs**: When instantiating `dag.AgGrid`, always set the following properties:
  - `dashGridOptions={"theme": "themeBalham", "animateRows": True, "pagination": True, "paginationPageSize": 10}`
  - `columnSize="responsiveSizeToFit"`
  - `defaultColDef={"filter": True, "sortable": True}`
- **Observability Controls**: Interface adjustments made to `pages/pipeline_health.py` must leverage `dash_bootstrap_components` elements (`dbc.Row`, `dbc.Col`, `dbc.Card`) rather than raw `html` constructs. Ensure text lineage diagnostic structures render cleanly via standard monospaced layout panels.

## 7. Avoid Hallucinations (Crucial)
- Never use `app.run_server`; only use `app.run`.
- Never use obsolete patterns like `app.validation_layout`. Modern Dash handles dynamic layouts smoothly via `suppress_callback_exceptions=True`.
- Never import `dash.dependencies` items individually. Always use the modern syntax: `from dash import Input, Output, State, callback, clientside_callback, no_update, ALL, MATCH`.
- Never write blocking `time.sleep` loops inside a callback in production contexts; use `dcc.Interval` or asynchronous background tasks.
- Never assign to callback `Input` values or mutate callback arguments in place.
- Never use `dash_table.DataTable`; use `dash.AgGrid()` instead.
- Never put secrets, API keys, or credentials in layout code or `dcc.Store`. Use environment variables and server-side logic only.

## 8. Specific Page Instructions: Pipeline Observability Maintenance
- When prompted to extend, rewrite, or debug pipeline status or lineage features, focus actions exclusively within `pages/pipeline_health.py` (main app) or `app_observability.py` (standalone).
- Verify that metadata parsing architectures correctly match dbt core terminologies (e.g., nodes, sources, exposures, seeds, dependencies).
- When altering data capture routines, ensure that the file mapping safely targets `analytics_layer/target/manifest.json`.
- Before closing out a tracking adjustment task, execute a verification validation call against `python app_observability.py` to rule out compilation crashes or structural callback errors.

## 9. Output Guidelines
- Do not apologize or include verbose introductory or concluding remarks.
- Provide clean, functional Python code blocks with clear inline comments for complex layout or callback logic.
- If a proposed solution requires installing a new pip package, explicitly state it at the top of your response.