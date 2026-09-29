Replace `AGENTS.md` with this integrated version:

````markdown
# Agent Context & Rules

## 1. Project Overview
- **Project Name:** Data Analytics Dashboard
- **Core Purpose:** An interactive multi-page dashboard to visualize live data tables from Google BigQuery and provide an analytics layer pipeline monitoring console.
- **Target Audience:** Internal business analysts, data engineers, and stakeholders.

## 2. Tech Stack & Environment
- **Language:** Python 3.[X]
- **Core Framework:** Plotly Dash
- **Underlying Engine:** Flask, including Flask-Caching
- **Data Engine:** Google BigQuery via Application Default Credentials (ADC), plus dbt artifact telemetry
- **Data Libraries:** `google-cloud-bigquery`, `pandas`, `pandas-gbq`, `pyarrow`, `json`
- **Caching Framework:** Flask-Caching with FileSystemCache or Redis
- **Styling:** Dash component libraries and modular CSS
- **Code Formatters:** `black` for Python and Prettier for CSS

## 3. Architecture & File Structure
- Use Dash Pages with `dash.page_registry` and `dash.register_page(__name__)`, unless the Snapshot Engine is used. With Snapshot Engine, use callback routing instead of Dash Pages.
- Keep Dash page modules in a `pages/` directory.
- `utils/data_loader.py` initializes the BigQuery client securely with ADC. Cache expensive data-fetching operations server-side.
- Pipeline observability telemetry is derived from `analytics_layer/target/manifest.json`. Transform raw contents into a memory-efficient flat schema.
- The app entry point must expose the Flask server: `server = app.server`.

Expected project structure:

```text
demo-database/
├── .venv/
├── Scripts/
│   ├── ingest_bronze.py
│   ├── ingest_bigquery.py
│   ├── ingest_dbt_artifacts.py
│   └── ddl_create_bronze_*.sql
├── analytics_layer/
│   ├── models/
│   │   ├── staging/
│   │   └── marts/
│   └── target/
├── my-dash-app/
│   ├── assets/
│   ├── components/
│   ├── pages/
│   ├── utils/
│   ├── app.py
│   ├── app_observability.py
│   ├── data_loader.py
│   └── requirements.txt
├── AGENTS.md
├── CLAUDE.md
└── Notebooks/
```

## 4. General Architecture
- Never use global variables to store user-specific state. Keep mutable client state in `dcc.Store` or URL parameters.
- Use descriptive, globally unique component IDs, such as `"sales-filter-dropdown"`.
- Load data inside callbacks, not at import time. Avoid module-level data reads or database queries; startup-loaded data will not refresh until the process restarts.
- Use a layout function such as `def serve_layout(): ...` when the layout must be rebuilt on each page load.
- Filter, aggregate, and paginate data in Python or SQL before sending it to graphs or `AgGrid`. Send only the rows or points needed for the current view.
- Pin minimum or exact versions of Dash, Plotly, and component libraries in `requirements.txt`.
- Use explicit BigQuery column names, logical filters, and date/time boundaries where applicable. Include a `LIMIT` during structural testing to control scan costs.

## 5. Callbacks, Data, and Performance
- Do not pass massive datasets through `dcc.Store`. Use it only for lightweight state such as IDs, UI toggles, or query filters, with a maximum of 5 MB.
- For large datasets, expensive queries, heavy computations, or API requests, use Flask-Caching and `@cache.memoize()`. Include relevant query parameters in cache keys.
- Ensure every callback `Input`, `Output`, and `State` ID exists in the layout when the callback fires. For dynamic or multi-page layouts, set `suppress_callback_exceptions=True`.
- Use `prevent_initial_call=True` for callbacks that should not run on page load, such as button-triggered actions.
- Return `dash.no_update` when an output should remain unchanged. Use `raise PreventUpdate` when the entire callback should be skipped.
- Keep callbacks focused: prefer one callback per user interaction and split large callbacks into smaller, composable ones.
- Wrap potentially slow components in `dcc.Loading` to show a loading indicator.
- Use background callbacks for work that takes more than a few seconds, with `background=True` and a configured manager such as `manager=background_callback_manager`.
- Return output types appropriate to the component: strings or component lists for `children`, dictionaries for figures, and lists of dictionaries for `AgGrid` `rowData` and `columnDefs`.
- Avoid blocking `time.sleep` loops in callbacks. Use `dcc.Interval` for asynchronous polling or an external task queue for long-running work.

## 6. Layout and Styling
- Put core layout styles, grids, and structural overrides in CSS files under `assets/`.
- Use a shared `theme.py` or `theme.js` for color, spacing, and font constants.
- Use inline Python style dictionaries only for dynamic, runtime-computed styling. Avoid static inline style blocks.
- Format Python with `black` and CSS with Prettier.

## 7. Charts and Components
- Prefer `plotly.express`; use `plotly.graph_objects` when fine-grained control is needed.
- Prefer component libraries in this order: Dash Design Kit when available, Dash Core Components with Dash HTML Components, Dash Mantine Components, then Dash Bootstrap Components when required. Minimize the number of libraries used.
- Do not use `dash_table.DataTable`; use `dash.AgGrid`.
- When creating `dag.AgGrid`, set these properties:

```python
dashGridOptions={
    "theme": "themeBalham",
    "animateRows": True,
    "pagination": True,
    "paginationPageSize": 10,
}
columnSize="responsiveSizeToFit"
defaultColDef={"filter": True, "sortable": True}
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
````
