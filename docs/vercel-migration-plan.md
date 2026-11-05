# Redeploy Plan: Cloud Run + BigQuery → Vercel

**Status:** Phases 1–2 and 5 complete — the dbt transformation layer is rebuilt on DuckDB, the shippable gold database is built and verified, the app reads that database plus a shipped telemetry artifact instead of BigQuery, and the application is packaged for Vercel. Phases 3, 4 and 6 not started.
**Date:** 2026-11-05 (Phase 1 delivered 2026-11-06, Phase 2 delivered 2026-11-06, Phase 5 delivered 2026-11-06)
**Scope:** Rebuild the data transformation layer without BigQuery, replace the dead auth provider, and package the Dash app for Vercel.

---

## 0. Phase 1 delivery summary (2026-11-06)

The transformation layer is rebuilt and the clean analytics database exists. What changed in the repo:

| Deliverable | Location | State |
|---|---|---|
| Adapter-portable macro layer | `analytics_layer/macros/portable.sql` | 9 dispatch macros, `bigquery__`/`duckdb__` branches |
| 9 models ported | `analytics_layer/models/` | All 10 models build on DuckDB |
| DuckDB profile | `analytics_layer/profiles.yml` | `duckdb` target (default) + retained `bigquery` target |
| Bronze loader | `Scripts/load_bronze_duckdb.py` | CSV → bronze tables, types mirror the old SQL Server DDL |
| Gold export | `Scripts/export_gold_duckdb.py` | Gold-only `my-dash-app/data/analytics.duckdb` (4.47 MB) |
| Drift gate | `Scripts/verify_shipped_gold.py` | Fails CI when the shipped artifact diverges from the build |
| Artifact regression tests | `tests/test_gold_dataset.py` | 6 offline tests over the shipped database |
| Source CSVs | `data/raw/source_crm/`, `data/raw/source_erp/` | 6 files, 98,395 rows, now in the repo |
| Offline lint support | `sqlfluff_macros/portable.sql` | Lets SQLFluff render the macros without a warehouse |
| CI | `.github/workflows/ci_pipeline.yml` | BigQuery job → offline DuckDB build; Cloud Run deploy job removed |

**Verified state of the gate:**

```
dbt build           132 results: 10 models, 122 tests
                    105 pass | 17 warn | 0 error
                    (the 17 warnings are the intentional severity: warn source checks)
cross-check         26/26 checks match the independent pandas reference
shipped artifact    gold.fct_sales 60,398 | dim_products 295
                    dim_customers 18,484 | product_360 130  →  4.47 MB
test suite          258 tests, 0 failures (offline, no warehouse client)
pyrefly             0 errors
sqlfluff            0 parse violations across all 10 models
```

**Decisions taken while building (they narrow Phase 0):**

1. **The port is a macro layer, not raw substitution.** The plan assumed zero macros; in practice the models now call `qe_safe_cast(...)`, `qe_parse_date(...)`, `qe_date_diff(...)` and friends, which dispatch to a BigQuery or DuckDB branch. The BigQuery target in `profiles.yml` still compiles, so the original warehouse path is defined and reviewable rather than deleted.
2. **The shipped artifact is a DuckDB file, not Parquet** (4.47 MB vs 2.40 MB, but it keeps SQL available at runtime and is the engine that built it).
3. **The full 60,398 fact rows are shipped**, not the old arbitrary 10,000-row sample.
4. **`product_360` is kept** and exported alongside the three tables the app reads; the 15 analyses remain as offline SQL.
5. **`dbt_expectations` was dropped** from `packages.yml` — it was declared but never referenced.

**Still open for you:** auth option A/B/C (§3.2), and whether `pipeline_health` is repurposed or removed (§3.3).

### Rebuilding the database from scratch

```bash
# 1. Load the raw CSVs into DuckDB bronze tables
uv run python -B Scripts/load_bronze_duckdb.py --fresh

# 2. Run the dbt models and their tests
cd analytics_layer && ../.venv/bin/dbt build --profiles-dir . && cd ..

# 3. Export the gold-only artifact the app ships with
uv run python -B Scripts/export_gold_duckdb.py

# 4. Confirm the shipped artifact matches the build (this is also the CI gate)
uv run python -B Scripts/verify_shipped_gold.py

# 5. Run the offline test suite
uv run python -B -m unittest discover -s tests -v
```

Step 4 is the one that matters: if a model changes and the artifact is not re-exported, it fails instead of letting the app serve stale numbers.

---

## 0.1 Phase 2 delivery summary (2026-11-06)

The app no longer talks to a warehouse. It reads two committed artifacts from the bundle, and the warehouse-only code paths are gone.

| Deliverable | Location | State |
|---|---|---|
| DuckDB data loader | `my-dash-app/data_loader.py` | `duckdb.connect(read_only=True)` over the shipped gold file; same merge, same `order_date >= 2010` filter, same `float64` normalization |
| Telemetry export | `Scripts/export_pipeline_telemetry.py` | Folds `run_results.json` + `manifest.json` + the bronze load manifest into one JSON |
| Telemetry reader | `my-dash-app/pipeline_telemetry.py` | Returns the frames the callbacks expect; degrades to empty frames when the artifact is absent |
| Shipped telemetry | `my-dash-app/data/pipeline_telemetry.json` | 132 execution logs, 10 model coverage rows, 44 column coverage rows, 6 ingestion logs, 6 freshness rows |
| Telemetry drift gate | `Scripts/verify_shipped_telemetry.py` | Fails CI when the shipped telemetry diverges from the dbt build |
| In-memory cache | `utils/cache.py` | `SimpleCache` instead of `FileSystemCache`; no writable path needed on Vercel |
| Cost monitoring removed | `my-dash-app/pages/pipeline_health.py` | The "BigQuery Costs" tab and its callback are gone — there is no warehouse to bill |
| Ingestion chart relabelled | `my-dash-app/pages/pipeline_health.py` | "CSV (Source)" vs "DuckDB Bronze (Destination)" |
| Offline guard | `tests/test_dashboard_regressions.py` | The `bigquery.Client` patch became a socket-level network ban |
| Artifact regression tests | `tests/test_pipeline_telemetry.py` | 16 offline tests over the export rules and the shipped artifact |
| CI | `.github/workflows/ci_pipeline.yml` | Added the telemetry export + drift gate after the dbt build |

**Verified state of the gate:**

```
dbt build           132 results: 10 models, 122 tests (unchanged)
gold artifact       gold.fct_sales 60,398 | dim_products 295
                    dim_customers 18,484 | product_360 130  →  4.47 MB
telemetry artifact  coverage 97.73% | 105 pass | 0 failed | 17 warnings
                    132 execution logs | 6 ingestion logs | 6 freshness rows
test suite          275 tests, 0 failures (offline, no network)
pyrefly             0 errors
ruff                check + format clean
```

**The running app was exercised against both artifacts, not just the tests.** Every
callback on all three pages was driven through the real Dash HTTP endpoint
(`/_dash-update-component`) with the shipped files in place:

```
/dashboard          KPIs: $29.35M revenue | 27,657 orders | 60,404 units
                    | 18,482 customers
                    sales trend: 2 traces, monthly from 2010-12-31
                    regional sales: United States, Australia, United Kingdom
                    top products: 10 rows (Mountain-200 Black- 46, $1.37M, 620 units)
/customers          KPIs: 18,482 active customers | $1,588 avg spend
                    | 1.50 avg frequency | 37.1% repeat rate
                    RFM segment + spend distribution charts render
/pipeline-health    KPI: 105 passed | 0 failed | 17 warnings | 97.7% coverage
                    execution grid: 132 rows (the dbt run)
                    model coverage: 10 models, 1 chart trace
                    column coverage: 44 columns, 2 chart traces
                    table ingestion: 6 rows, CSV vs DuckDB bronze chart
```

The mutations carry a valid `Origin` header because the auth guard rejects
cross-origin writes; without it the guard answers `403 origin_rejected` before
any callback runs. That rejection is the auth rule working, not a data defect.

**Decisions taken while building (they narrow Phase 4):**

1. **The `audit_metadata` warehouse tables are replaced by local equivalents, not deleted.** Coverage comes from `manifest.json`, execution history from `run_results.json`, and ingestion parity from the bronze load manifest — the same three facts the warehouse tables carried.
2. **Telemetry is one committed JSON file, read at runtime.** The dbt `target/` directory is not deployed, so the facts are baked into an artifact that CI keeps honest.
3. **The BigQuery Costs tab is removed, not emptied.** There is no warehouse, so there is no cost data and no honest way to present an empty chart as a monitoring view.
4. **The ingestion history ages out, and that is left visible.** The shipped snapshot records a load from the day it was built; the freshness KPI and the "latest snapshot" chart still show it as stale rather than faking a fresh timestamp.

**Still open for you:** auth option A/B/C (§3.2), and whether `pipeline_health` is repurposed or removed (§3.3).

---

## 1. Investigation results

### 1.1 Status of every external dependency

| Dependency | Status | Evidence |
|---|---|---|
| BigQuery project `quantum-echo-data-eng-prod` | **Dead** | GCP trial ended; `gcp-key.json` still present locally but the project is unreachable |
| Supabase project `gqzxjsjxdezucscxvinr` | **Dead** | `nslookup` → `NXDOMAIN` while `supabase.co` itself resolves and general internet works → the project was deleted, not a DNS/network problem |
| SQL Server source (`Demo_Database`) | **Not running** | Nothing listening on TCP 1433; no Docker daemon available |
| dbt models / macros / analyses | **Intact** | 6 staging + 4 mart models, 4 custom macros, 15 analyses in [analytics_layer/](file:///Users/roelsomido/demo-database/analytics_layer) |
| Raw source CSVs | **Intact** | `/Users/roelsomido/Source` — 98,395 rows across 6 files, ~5.2 MB |
| Dash app + business logic | **Intact** | 3 pages, 9 components, ~1,573 lines of Python business logic, ~743 lines of auth JS |

**The single most important finding: the raw source data still exists locally.** Every transformation you built is reproducible from those 6 CSVs. Nothing about the business logic needs to be re-derived from scratch — it needs to be re-*targeted* at a different SQL engine.

### 1.2 The dbt transformation inventory

Only **3 of the 4 mart models are actually consumed by the running app**. This is the single biggest scope reduction available.

**Consumed by the Dash app** (must be rebuilt):

| Model | Business logic it encodes |
|---|---|
| `stg_crm_cust_info` | Dedup by `cst_id` keeping latest `cst_create_date`; trim names; `S`/`M` → Single/Married; `F`/`M` → Female/Male |
| `stg_crm_prd_info` | `cat_id` = first 5 chars of `prd_key` with `-`→`_`; `prd_key` = substring from char 7; `prd_line` code map (M/R/S/T → Mountain/Road/Standard/Touring); `prd_end_dt` derived via `LEAD()` window − 1 day (the CSV's own `prd_end_dt` column is **ignored**) |
| `stg_crm_sales_details` | Date parsing from `%Y%m%d` ints with `1900-01-01` fallback; price repair (`ABS`, derive from sales/quantity when null/zero); `GREATEST()` to enforce ship/due ≥ order; sales re-derivation when ≤ 0 |
| `stg_erp_cust_az12` | Strip `NAS` prefix from `cid`; dual-format birthdate parse (`%Y-%m-%d` then `%Y%m%d`); future birthdates → NULL; gender code map |
| `stg_erp_loc_a101` | Strip hyphens from `cid`; `DE`→Germany, `US`/`USA`→United States, empty→NULL |
| `stg_erp_px_cat_g1v2` | `CO_PD` → `CO_PE` remap |
| `dim_customers` | Surrogate key on `cst_id`; CRM ⋈ ERP customer ⋈ ERP location; `COALESCE(crm_gender, erp_gender)` |
| `dim_products` | Surrogate key on `prd_id`; CRM ⋈ ERP category; **filters `prd_end_dt IS NULL`** → only currently-active products |
| `fct_sales` | Surrogate key on (order, product); LEFT JOINs to both dims; `quantity`, `unit_price`, `gross_sales_amount` as measures |

**Not consumed by the app** (can be dropped, archived, or kept as offline SQL):
`product_360` (mart), plus all 15 analyses including `rpt_customer_360.sql`, `cummulative_sales.sql`, `customer_segment.sql`, `metric_audit.sql`, `test_referential_integrity.sql`. These feed nothing in `my-dash-app/` — the Customer 360 page computes RFM in Python instead.

### 1.3 The business-logic inventory (lives in Python, not SQL)

This is the part that must survive the migration untouched, and it is **entirely backend-agnostic** — it operates on a pandas DataFrame with a fixed column contract.

| Location | Logic |
|---|---|
| [utils/helpers.py](file:///Users/roelsomido/demo-database/utils/helpers.py) | `filter_dataframe` (date range + exact-string category/country), `calculate_pop_badge` (prior equal-length window), `create_trend_badge`, `format_compact_number` |
| [pages/overview.py](file:///Users/roelsomido/demo-database/my-dash-app/pages/overview.py) | Revenue/orders/units/customers KPIs, 9 tooltip metrics (AOV, daily averages, revenue-per-customer), category donut, top-10 products, revenue-by-country bar, product detail modal + CSV export |
| [pages/customer_360.py](file:///Users/roelsomido/demo-database/my-dash-app/pages/customer_360.py) | Per-customer spend/orders/units, repeat rate, **RFM segmentation** (Champions / Loyal / Hibernating-Lost / Promising), spend histogram, top-10 high-value customers, monthly active customers |
| [components/kpi_sparklines.py](file:///Users/roelsomido/demo-database/my-dash-app/components/kpi_sparklines.py) | Weekly↔monthly auto-bucketing at the 60-day boundary, partial-period labelling, 4 sparkline series per page |
| [components/sales_trend.py](file:///Users/roelsomido/demo-database/my-dash-app/components/sales_trend.py) | Revenue + **gross margin** `(revenue − qty×cost)/revenue`, suppressed where cost is missing/invalid |
| [components/revenue_chart.py](file:///Users/roelsomido/demo-database/my-dash-app/components/revenue_chart.py) | ISO-3 country mapping via `pycountry` + alias table, choropleth, unknown-revenue bucket |
| [my-dash-app/app.py](file:///Users/roelsomido/demo-database/my-dash-app/app.py) | Export modal + CSV report — **duplicates the Customer 360 KPI and RFM blocks verbatim** |

### 1.4 The `pipeline_health` page is ~75% dead weight

[pages/pipeline_health.py](file:///Users/roelsomido/demo-database/my-dash-app/pages/pipeline_health.py) is a meta-dashboard *about the dbt pipeline itself*. Without BigQuery:

- **No data source at all:** Execution Logs, Model Coverage, Column Coverage tabs; 8 of 12 KPI cards (passed/failed/warning tests, total tests, avg duration, coverage % buckets).
- **BigQuery-only:** the "BigQuery Costs" tab (`INFORMATION_SCHEMA.JOBS_BY_PROJECT`, slot-seconds, bytes billed).
- **Survivable with relabelling:** source freshness, latest load, and the ingestion row-parity chart — but they read `audit_metadata.dbt_execution_logs` / `table_ingestion_logs`, which no longer exist.
- The **header health bell** in [components/header.py](file:///Users/roelsomido/demo-database/my-dash-app/components/header.py) depends entirely on this summary and its copy literally says "dbt".

Also dead: [my-dash-app/app_observability.py](file:///Users/roelsomido/demo-database/my-dash-app/app_observability.py) parses `analytics_layer/target/manifest.json` and registers a `/observability` page — but it sits outside `pages/`, so Dash never imports it. That route **does not exist** in the running app today. `app_observability.py` is dead code.

### 1.5 Verification: the rebuild was proven locally

I re-implemented all 6 staging models + `dim_customers` + `dim_products` + `fct_sales` in pandas and ran them against the real CSVs, then fed the result through the app's *own* `filter_dataframe`, `calculate_pop_badge`, `aggregate_sales_trend`, RFM classifier, and `aggregate_countries`.

```
bronze            crm_cust_info 18,494 | crm_prd_info 397 | crm_sales_details 60,398
                  erp_cust_az12 18,484 | erp_loc_a101 18,484 | erp_px_cat_g1v2 37
staging           6 models reproduced, 0 row loss
marts             dim_customers 18,484 | dim_products 295 (102 superseded excluded) | fct_sales 60,398
joins             unmatched customer_key: 0 | unmatched product_key: 0
merged app frame  60,379 rows | 2010-12-29 → 2014-01-28 | 3 categories | 6 countries
total revenue     $29,350,874 across 27,657 orders / 18,482 customers
margin            computed every month, 0 missing-cost periods
RFM               Champions 142 | Loyal 1,183 | Promising 3,607 | Hibernating 13,550
country map       USA 9.16M | AUS 9.06M | GBR 3.39M | DEU 2.89M | FRA 2.64M | CAN 1.98M | unknown 226,820
```

The transformation is fully recoverable. The reference implementation is at `~/qoder_bq_rebuild_backup/rebuild_dbt_models.py` with output Parquet in `~/qoder_bq_rebuild_backup/gold/`. (Everything in this scratch tree was copied out of `/tmp` to `~/qoder_bq_rebuild_backup/` because `/tmp` is not durable across reboots.)

**A second, independent verification now exists.** The real dbt models were ported to dbt-duckdb (see §3.1) and built against the same CSVs loaded into DuckDB bronze tables:

```
dbt build        PASS=115  WARN=17  ERROR=0  SKIP=0  TOTAL=132
                 (132 results = 10 models + 122 tests; the 17 warnings are the
                  intentional severity: warn source checks)
cross-check      26/26 checks match the pandas reference:
                 row counts | revenue $29,355,866 | units 60,423 | orders 27,659
                 customers 18,484 | products 130 | date range | per-product revenue top 10
                 country / marital-status / category cardinalities | null counts
                 app-shaped merged frame + its datetime64 / float64 dtype contract
```

Two independent implementations of the same SQL — one written from the BigQuery models by hand in pandas, one a mechanical function-substitution port running inside dbt — agree on every number. That is strong evidence the port is faithful and the business logic is fully recoverable.

---

## 2. Critical findings that change the plan

### 2.1 The live app was only ever showing a 10,000-row sample

[data_loader.py:53-56](file:///Users/roelsomido/demo-database/my-dash-app/data_loader.py#L53) queries `fct_sales` with `LIMIT @limit` (default 10,000) and **no `ORDER BY`**. BigQuery returned an arbitrary 10,000 of 60,398 rows — about **$14.4M of the $29.35M total revenue**.

**Every KPI on the live dashboard was computed on that sample.** Serving the full fact table now will change every number on every page. This is a decision, not a bug fix: either replicate the truncation (misleading) or serve the full data and accept the numbers change.

### 2.2 The data is a static 2010–2014 snapshot — there is no live source anymore

The original chain was `CSVs → SQL Server → BigQuery → dbt → gold → Dash`. With SQL Server and BigQuery both gone, and the CSVs being a fixed historical extract, **there is nothing to refresh**. The entire ELT machinery reduces to a one-time build step.

This is why the recommended architecture below collapses the pipeline instead of replacing it wholesale.

### 2.3 `data_loader.py` is the only BigQuery-coupled file in the app

All BigQuery access is confined to [my-dash-app/data_loader.py](file:///Users/roelsomido/demo-database/my-dash-app/data_loader.py). Pages and components are pure pandas/Plotly. `utils/audit_logger.py` and `utils/helpers.py` carry BigQuery helpers used only by the ingest scripts, not the app.

**That means the data-backend swap touches one file.** The Python business logic needs zero changes.

### 2.4 The DataFrame column contract is strict

The merged frame must expose exactly these columns with these dtypes, or the app breaks silently:

| Column | Contract | Enforced at |
|---|---|---|
| `order_date` | `datetime64`, **timezone-naive** | `helpers.py:63` compares against `pd.to_datetime(start_date)` (naive) — a tz-aware frame raises `TypeError` |
| `gross_sales_amount`, `unit_price`, `cost` | `float64` | `sales_trend.py:17` calls `np.isfinite()` → raises `TypeError` on object/Decimal dtype |
| `category`, `country` | exact strings, no title-casing | `helpers.py:66-69` uses `==` against raw dropdown values |
| `customer_key`, `product_key`, `order_number` | non-null hashables | join keys + RFM grouping |
| `product_name`, `first_name`, `last_name` | nullable strings | `.fillna("")` applied downstream |

`unit_price` is loaded but never used — safe to drop.

### 2.5 `dim_products` silently drops 102 products' sales

`WHERE prd_end_dt IS NULL` keeps only the newest version of each `prd_key`. Sales against superseded products get a NULL `product_key` and vanish from the category donut, country bar, and top-10 products. **This is business logic, not a data-quality artifact** — it must be preserved deliberately or consciously dropped.

### 2.6 Vercel will auto-detect the wrong entrypoint

The repo root contains [app.py](file:///Users/roelsomido/demo-database/app.py) — a 1-line Cloud Run placeholder. Vercel looks for `app.py`/`server.py`/`wsgi.py` at the project root and would load that file. The real entrypoint lives in `my-dash-app/`, and **`my-dash-app` contains a hyphen, so it is not an importable Python package.** Both must be resolved via `tool.vercel.entrypoint` in `pyproject.toml` (which points at a `module:variable` path) pointing to a new importable module.

### 2.7 FileSystemCache will break on Vercel — ✅ resolved in Phase 2

[utils/cache.py](file:///Users/roelsomido/demo-database/utils/cache.py) used `FileSystemCache` with `CACHE_DIR="cache-directory"`. Vercel's bundle filesystem is read-only except `/tmp`. **Resolved:** the cache is now `SimpleCache`, which lives inside the worker process and needs no writable path at all. The `Dockerfile` no longer creates a cache directory either.

---

## 3. Target architecture

### 3.1 Recommendation: dbt-duckdb builds a local snapshot; the app reads it from the bundle

```
data/raw/source_{crm,erp}/*.csv   (now in the repo)
        │  (build step, run locally or in CI)
        ▼
Scripts/load_bronze_duckdb.py  →  bronze.* tables in analytics_layer/build/analytics.duckdb
        │
        ▼
dbt-duckdb  ── analytics_layer/models (SQL unchanged except function substitution)
        │
        ▼
Scripts/export_gold_duckdb.py  →  my-dash-app/data/analytics.duckdb  (4.47 MB)
Scripts/export_pipeline_telemetry.py  →  my-dash-app/data/pipeline_telemetry.json  (81 KB)
        │  (both bundled into the Vercel deployment)
        ▼
   data_loader.get_prepared_dataset()  → pandas DataFrame
   pipeline_telemetry.*_frame()        → telemetry DataFrames
        ▼
   Dash app  →  Vercel Python function
```

**Why this over the alternatives:**

| Option | Verdict |
|---|---|
| **dbt-duckdb → Parquet** ✅ | Keeps every SQL model and every dbt test intact. No database to provision, no connection pooling, no credentials in the Vercel env. The dataset is static, so a snapshot loses nothing. Builds in seconds. |
| dbt-postgres → Neon/Supabase Postgres | More moving parts (pooler, TLS, credentials) for a dataset that never changes. Worth revisiting only if you want live refresh. `psycopg2-binary` is already a dependency, so the port is cheap. |
| Pure-Python/pandas transform (the PoC I wrote) | Works and is proven, but throws away dbt's declarative DAG and data tests — the thing that makes this a portfolio piece. Keep it as a *validation fixture*, not the production path. |
| Static CSV/JSON in the bundle | No type fidelity (`Decimal`, dates), no dbt. Strictly worse than Parquet. |

**dbt-duckdb portability work** — the models used a handful of BigQuery-only constructs. The port is a **dialect-portable macro layer**: each construct became a `qe_*` macro with a `bigquery__` branch and a `duckdb__` branch, resolved by dbt's `adapter.dispatch`. The BigQuery target in [analytics_layer/profiles.yml](file:///Users/roelsomido/demo-database/analytics_layer/profiles.yml) still compiles the original warehouse SQL, so the warehouse path stays defined instead of being deleted.

| BigQuery construct | Macro | DuckDB branch | BigQuery branch |
|---|---|---|---|
| `SAFE_CAST(x AS int64)` | `qe_safe_cast(x, type)` | `TRY_CAST(x AS BIGINT)` | `SAFE_CAST(x AS int64)` |
| `PARSE_DATE(fmt, x)` | `qe_parse_date(fmt, x)` | `CAST(strptime(x, fmt) AS DATE)` | `PARSE_DATE(fmt, x)` |
| `SAFE.PARSE_DATE(fmt, x)` | `qe_safe_parse_date(fmt, x)` | `CAST(TRY_STRPTIME(x, fmt) AS DATE)` | `SAFE.PARSE_DATE(fmt, x)` |
| `current_timestamp()` | `qe_current_timestamp()` | `current_timestamp` (bare — DuckDB rejects the parens) | `current_timestamp()` |
| `current_date()` | `qe_current_date()` | `current_date` | `current_date()` |
| `DATE_DIFF(a, b, unit)` | `qe_date_diff(a, b, unit)` | `date_diff('unit', b, a)` — argument order is reversed | `DATE_DIFF(a, b, unit)` |
| `DATE_SUB(d, INTERVAL 1 DAY)` | `qe_date_sub_day(d)` | `(d - INTERVAL 1 DAY)` | `DATE_SUB(d, INTERVAL 1 DAY)` |
| `SAFE_DIVIDE(a, b)` | `qe_safe_divide(a, b)` | `CASE WHEN b = 0 THEN NULL ELSE a / b END` | `SAFE_DIVIDE(a, b)` |
| `dbt.type_string()` | `qe_string_type()` | `VARCHAR` | `STRING` |
| `int64` / `decimal` type names | — | `BIGINT` / `DECIMAL(38, 9)` — valid on both engines | unchanged |

Three details that were not obvious and are now pinned by tests:

- **DuckDB's `fdiv(a, 0)` returns `inf`, not `NULL`.** `SAFE_DIVIDE` must be an explicit `CASE`; the obvious one-word swap is wrong.
- **BigQuery `DATE_DIFF` counts unit boundaries crossed**, and DuckDB's `date_diff` matches it exactly — verified against all 7 documented BigQuery examples, including the `2011-12-18 → 2011-12-19` case that returns 0.
- **`DECIMAL(38, 9)`** was chosen over `DECIMAL(18, 2)` because it is BigQuery's `NUMERIC` equivalent and every source price has at most 2 decimals — both spellings produce identical values, but the BigQuery-faithful one keeps the two engines byte-comparable.

Everything else ports as-is: `LEAD() OVER`, `GREATEST()`, `row_number()`, `trim`, `substring`, `replace`, plus `dbt_utils.generate_surrogate_key` and `dbt_utils.safe_divide` (both cross-database in dbt_utils 1.x) and the 4 custom macros in [analytics_layer/macros/](file:///Users/roelsomido/demo-database/analytics_layer/macros) (plain portable SQL).

One source-YAML test expression also needed an edit: `safe_cast(bdate as date) <= current_date()` → `{{ qe_safe_cast('bdate', 'date') }} <= {{ qe_current_date() }}`.

Also: `dbt_expectations` was declared in [packages.yml](file:///Users/roelsomido/demo-database/analytics_layer/packages.yml) but **never used** in any model, test, or analysis — dropped.

**SQLFluff compatibility:** SQLFluff's offline Jinja templater cannot resolve dbt macros, and `dbt.type_*` helpers are unavailable there. The models therefore use portable type literals instead of `dbt.type_*`, and [sqlfluff_macros/portable.sql](file:///Users/roelsomido/demo-database/sqlfluff_macros/portable.sql) renders the BigQuery branch of each macro at lint time (loaded via `load_macros_from_path` in [.sqlfluff](file:///Users/roelsomido/demo-database/.sqlfluff)). The models lint clean with zero parse violations and no warehouse access.

**Verified port result:** the full 10 models build clean on DuckDB — `PASS=115 WARN=17 ERROR=0 SKIP=0 TOTAL=132`. The 17 warnings are the intentional `severity: warn` source-quality checks, already warn-level in the original project. Output was then checked against an independent pandas re-implementation of the same SQL: **26/26 checks match** (row counts, revenue $29,355,866, units 60,423, orders 27,659, customers 18,484, products 130, date range, per-product revenue top 10, country/status/category cardinalities, null counts, and the app-shaped merged frame with its `datetime64`/`float64` dtype contract).

The BigQuery path was checked separately: compiling HEAD's models and the ported models with `--target bigquery` and diffing the SQL shows only casing, the added no-op `CAST(bdate AS string)`, the removed `@datacloud.settings` comments, and one formatting change — no semantic difference.

### 3.2 Auth: three options, one decision needed

The Supabase project is deleted, which kills ~1,573 lines of Python and ~743 lines of JS:

| File | Coupling |
|---|---|
| [my-dash-app/auth.py](file:///Users/roelsomido/demo-database/my-dash-app/auth.py) (345) | Verifies access tokens via `GET {SUPABASE_URL}/auth/v1/user`; decodes JWT `exp`; `g.auth_user`; `/auth/config` + `/auth/session` endpoints; CSP nonce; `Cache-Control: private, no-store` |
| [my-dash-app/password_auth.py](file:///Users/roelsomido/demo-database/my-dash-app/password_auth.py) (175) | Calls Supabase RPC `qe_password_attempt` for lockout leases; password sign-in endpoint |
| [my-dash-app/user_admin.py](file:///Users/roelsomido/demo-database/my-dash-app/user_admin.py) (310) | Supabase Admin API: list users, suspend, delete; `qe_role` / `qe_owner` / `qe_suspended` in `app_metadata` |
| [my-dash-app/auth_frontend/](file:///Users/roelsomido/demo-database/my-dash-app/auth_frontend) (743) | `@supabase/supabase-js` — OAuth PKCE (Google/GitHub), email/password signup, session refresh, cross-tab sign-out |

The three Supabase SQL migrations in [supabase/migrations/](file:///Users/roelsomido/demo-database/supabase/migrations) (password lockout, account-deletion guard, administrator-access guard) are also gone with the project.

| Option | Effort | Risk | Note |
|---|---|---|---|
| **A. New free Supabase project** | Lowest — reuse the code, re-apply the 3 migrations | **Free tier pauses after 7 days of inactivity** → a portfolio demo link goes dark. OAuth providers need re-enabling in the console per provider | Only pick this if you actively keep the project warm |
| **B. Self-hosted auth in the app** (recommended) | Medium — new users table + Flask session + password hashing; OAuth PKCE dropped, JS shrinks sharply | No external dependency, no pause, demo never goes dark | The app already has `password_auth.py` lockout logic and a `supabase/` folder with the guard SQL to port to plain SQL |
| **C. Drop auth, public demo** | Lowest | Anyone can see the dashboard; but it removes the admin/role feature set entirely | Reasonable for a read-only portfolio demo |

**Recommendation: A** (a new free Supabase project), because the evidence in §3.4 shows the coupling is *only* in environment variables and three replayable SQL migrations — there is nothing in the codebase to rewrite. The free tier's 7-day idle pause is the one real drawback; it is solvable with a scheduled keep-wake (a Vercel cron that pings the project) and is a smaller price than rewriting the auth stack. Choose **B** (self-hosted) only if you want the app to have zero external dependency. **C** is the cheapest if the demo does not need auth at all.

### 3.3 `pipeline_health`: repurpose or remove

Two viable paths:

- **Repurpose** → rename to *Data Pipeline Health* and report on the **new** pipeline: source CSV row counts, dbt model row counts and test results from the build's `run_results.json`, and Parquet file freshness. Keeps the page, keeps the header bell, and is *more* impressive (it shows the new pipeline's health, not a dead warehouse's). ~1 day of work.
- **Remove** → delete the page, the header bell, and `app_observability.py`. ~2 hours.

Recommendation: **repurpose**, using the build's `run_results.json` as the telemetry source (the parsing logic in `app_observability.py` already does exactly this — it just needs a different file to read).


### 3.4 Where the data actually lives: a file in the bundle, not a hosted database

The source is a **static 2010–2014 snapshot** (98,395 rows across 6 CSVs). Nothing writes to it anymore — BigQuery is deleted and SQL Server is gone. A hosted database would be paying monthly for a dataset that never changes.

**Measured, on the real artifacts:**

| Storage option | Size | Cold read (full 60,379-row merge) | Runtime dependency | Verdict |
|---|---|---|---|---|
| **DuckDB file, gold only** (4 tables: `fct_sales`, `dim_products`, `dim_customers`, `product_360`) | **4.47 MB** (built in Phase 1) | 83 ms connect + 563 ms query | `duckdb` wheel (~20 MB) | ✅ **Chosen in Phase 1** — keeps SQL at runtime, same engine that built it |
| DuckDB file, bronze + gold | 10.50 MB | same | `duckdb` | Fine, but ships 6.5 MB of source data the app never reads |
| Parquet gold tables | 2.40 MB | 97 ms read + 28 ms merge | `pyarrow` only (already a dependency) | ✅ Strong alternative — smallest, no SQL engine in prod |
| Hosted Postgres (Neon/Supabase) | n/a | network round-trip + pooler | `psycopg2` + credentials in Vercel env | ❌ Wrong shape for static data; only needed for *auth*, see below |
| Static CSV/JSON | ~9 MB | parse cost | none | ❌ Loses date/`Decimal` type fidelity, no dbt |

Both recommended options fit in the deployment bundle with room to spare (Vercel's limit is 500 MB uncompressed). Neither is blocked by `.gitignore` — no `*.duckdb` or `*.parquet` pattern is ignored today.

**The read-only-filesystem constraint is satisfied.** Vercel mounts the bundle read-only, so the DuckDB file was tested the way Vercel will actually run it: the file and its directory were `chmod a-w`, then opened with `duckdb.connect(path, read_only=True)`. It opened and served the full merge correctly. The in-memory frame is 12.7 MB — comfortably inside a 512 MB function.

**The one thing that cannot be a bundled file** is auth state, because it needs writes (signups, password-attempt lockout counters, `qe_role` / `qe_suspended` flags, deletion guards). Where that goes:

| Auth state option | Where it lives | Effort | Note |
|---|---|---|---|
| **New free Supabase project** | Supabase's own Postgres | ~1 hour | **Zero code change.** Every Supabase reference is env-driven (`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`) — no project ref is hardcoded anywhere in the repo. The three RPC functions are not hardcoded either: they live as SQL in [supabase/migrations/](file:///Users/roelsomido/demo-database/supabase/migrations) and can be replayed on a new project. |
| Self-hosted auth in the app | A new Postgres on Neon + rewritten auth | ~2 days | Drops the 7-day Supabase pause problem and the OAuth PKCE providers, but rewrites ~1,573 lines of Python and ~743 lines of JS. |
| Drop auth | Nowhere | ~2 hours | Read-only public demo; removes `/admin/users`, roles, and the security story. |

The old Supabase project is confirmed gone: `gqzxjsjxdezucscxvinr.supabase.co` does not resolve, while `supabase.co` itself resolves normally — so this is a deleted project, not a local DNS fault.

**Recommendation:** ship the **gold-only DuckDB file (4.01 MB)** as the analytics store, and give auth its own free Supabase project with the three migrations replayed. That is the whole storage story: one file in the bundle for the analytics, one hosted Postgres for the users. If you would rather not pay Supabase's 7-day idle pause, self-hosting auth on Neon Postgres is the fallback, and it is the only piece of this project that genuinely needs a database server.

### 3.5 Does the bundle file fit on the Vercel Hobby plan? Yes — with room to spare

The bundle file is the smallest part of the Hobby budget. Measured against the current limits:

| Hobby limit | Limit | This project | Headroom |
|---|---|---|---|
| Bundle size (uncompressed, Python runtime) | 500 MB | 4.01 MB DuckDB (or 2.40 MB Parquet) | ~99% free |
| Maximum memory | 2 GB / 1 vCPU | ~13 MB frame + Python/pandas/plotly/duckdb | fits easily |
| Maximum duration | 300s (default = max) | ~1–3 s cold start, 0.09 s per dashboard request | 100×+ |
| Active CPU | 4 hrs/month (14,400 CPU-s) | ~2 s per cold start, ~0.1 s per request | see below |
| Provisioned memory | 360 GB-hrs/month | accrues only while a request is in flight — instances pause when idle | ample |
| Function invocations | 1,000,000/month | Dash fires one invocation per callback, so ~8–10 per page view | ample |
| Deployments per day | 100 | a handful | fine |
| Runtime log retention | 1 hour | — | minor, mostly affects debugging |

**The binding constraint is Active CPU, not the bundle.** Measured on this machine: importing dash + pandas + plotly + dash_bootstrap_components costs ~0.5 s CPU, the DuckDB cold read costs ~0.65 s, and one full dashboard interaction (filter + monthly revenue trend + KPI badge + country aggregation) over all 60,379 rows costs **0.086 s**. So the Hobby allowance covers roughly **6,700 cold-start page loads** or **~90,000 warm requests** per month. Both are far beyond a portfolio demo — but it does mean a cold-start-heavy app on Hobby is fine while a high-traffic one would need Pro.

**DuckDB was tested under Vercel's exact filesystem conditions**, not just assumed: working directory `chmod a-w`, `HOME` pointed at a read-only directory, `TMPDIR` writable. `duckdb.connect(path, read_only=True)` opened and served the full 60,379-row merge in 81 ms + 582 ms with the correct $29,350,874 revenue.

**Three Hobby-specific things to know:**

1. **Non-commercial use only.** The fair-use guidelines restrict Hobby to personal, non-commercial use. A portfolio demo qualifies. If the dashboard is ever monetized or used inside a business, Hobby is not permitted and Pro ($20/month) is required.
2. **Exceeding a limit pauses the account**, and the pause lasts until the 30-day cycle resets — so a traffic spike is not just a bill, it takes the demo offline. For a demo this is unlikely, but it argues for the in-process dataset cache rather than re-querying per request.
3. **The Supabase free tier's 7-day idle pause is a separate limit and is the more likely cause of a "dead demo link."** Vercel Hobby has no such behavior; the pause is entirely on the auth side. A Vercel cron that pings the app weekly resolves it for the cost of one invocation per week.

### 3.6 The other free-tier option: Databricks Free Edition

Databricks Free Edition *can* host this app — Dash is an explicitly supported framework for [Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/) — but it is a worse host for this particular app than Vercel Hobby. The reasons are specific and verifiable, not vague:

| Concern | Vercel Hobby | Databricks Free Edition |
|---|---|---|
| Public access | Anonymous HTTP URL | **Not anonymous.** "Initial user requests to a Databricks app initiate OAuth authentication with the control plane to validate the session and authorize access to the app." A visitor needs a Databricks account *and* workspace `CAN USE` access. |
| App uptime | Always on | Apps run up to 24 h after start/update/redeploy, then **stop automatically — and a stopped app is not accessible**. Someone must restart it. Restart cold start is "typically a few minutes." |
| Outbound internet | Open | **Restricted to a limited set of trusted domains, and the allowlist cannot be extended** (network policies are Enterprise-tier only, and Free Edition has no account console) |
| Consequence for auth | Supabase works, zero code change | Every `urlopen` to `*.supabase.co` in `auth.py` / `password_auth.py` / `user_admin.py` fails → the whole auth stack must be rewritten to Databricks email-OTP / Google / Microsoft sign-in, and the `app_metadata.qe_role` admin model has no home |
| Analytics runtime | 4 MB file, 0.65 s cold read | 2X-Small SQL warehouse, cold-start latency per query |
| Idle-account risk | none | "Databricks may delete Free Edition accounts that are inactive for a prolonged period"; exceeding quota shuts compute down for the rest of the day |
| Commercial use | Not allowed | Not allowed |

**The public-access row is the decisive one.** A Vercel URL is a link you can paste anywhere. A Databricks Apps URL (`https://<app-name>-<workspace-id>.<region>.databricksapps.com`, immutable after creation) prompts an OAuth handshake with the Databricks control plane and only serves users who authenticate as Databricks users with `CAN USE` on the app. On a Free Edition account that means every visitor needs their own Databricks account *and* an invitation into your workspace. That is not a portfolio link — it is a private team tool.

**Deployment mechanics, if you did go this route.** `app.yaml` is optional and supports exactly two keys, `command` and `env`. There is **no implicit `app` variable convention** — by default Databricks runs `python <first .py file in the app directory>`, so the app must start its own server. The official Flask shape is `command: [gunicorn, app:app, -w, 4]`, and the app must listen on `0.0.0.0` on the port given by `DATABRICKS_APP_PORT`. That means this repo needs the same importable root-level shim the Vercel path needs (`my-dash-app` has a hyphen and is not importable as a package — see risk #7).

Other constraints worth knowing before choosing it:

- **Per-file size cap of 10 MB** in the app directory. The 4.01 MB DuckDB file and the 2.40 MB of Parquet both fit comfortably; anything larger would fail the deployment outright.
- **The local filesystem is ephemeral** — "data is lost when the app restarts" — and Databricks' own best practice is "use in-memory caching for expensive operations." That independently confirms the `FileSystemCache` → in-memory change already planned in Phase 2.
- **Reverse proxy in front of the app**, so "your app can't depend on the origin of requests." The app's exact-`Origin` matching and `AUTH_APP_ORIGIN` would need to point at the `databricksapps.com` hostname instead of a custom domain.
- **SIGTERM must be handled within 15 seconds**, and horizontal scaling (1–5 instances) uses best-effort sticky sessions — so the in-process dataset cache would exist once per instance (5 × 13 MB, harmless).
- **Dash background callbacks are impractical** — they need a Celery + Redis backend that Apps and Free Edition do not provide. This app is unaffected: it has no `background=True` callbacks, only one 60-second `dcc.Interval` for the header health indicator.
- Preinstalled versions are older than this repo's (`dash` 2.18.1, `plotly` 5.24.1 vs. the repo's 4.4.1 and 7.0.0), but `requirements.txt` or `pyproject.toml` + `uv.lock` pins them correctly.

**Where the data would live on Databricks.** Unity Catalog Delta tables in the Free Edition metastore, built by `dbt-databricks` (currently 1.13.0, requiring `dbt-core>=1.11.2,<1.12.7` — the repo's installed `dbt-core 1.12.4` already satisfies that). The adapter defaults to Delta with `merge` for incremental models and runs expensive queries on Photon. Free Edition is serverless-only, so dbt *Python* models would not be feasible there (they need an all-purpose cluster), but every model in this repo is SQL, and SQL models can target the 2X-Small serverless warehouse.

The port is the same shape as the DuckDB one — 39 function-level substitutions across the 9 models, and **no `QUALIFY`, `UNNEST`, `STRUCT` or `ARRAY` constructs** anywhere, so the SQL is unusually portable. Spark SQL is actually a closer dialect match than DuckDB was:

| BigQuery construct | Count | Databricks SQL replacement |
|---|---|---|
| `current_timestamp()` | 6 | `current_timestamp()` — unchanged |
| `CAST(x AS STRING)` | 6 | `CAST(x AS STRING)` — unchanged |
| `PARSE_DATE('%Y%m%d', x)` | 5 | `to_date(x, 'yyyyMMdd')` |
| `SAFE_CAST(x AS int64)` | 4 | `try_cast(x AS BIGINT)` |
| `CAST(x AS int64)` | 4 | `CAST(x AS BIGINT)` |
| `SAFE_DIVIDE(a, b)` | 3 | `try_divide(a, b)` |
| `DATE_DIFF(end, start, unit)` | 3 | `date_diff(unit, start, end)` — argument order reverses |
| `CAST(x AS DATE)` | 3 | `CAST(x AS DATE)` — unchanged |
| `CAST(x AS DECIMAL)` | 2 | `CAST(x AS DECIMAL(18,2))` |
| `DATE_SUB(d, INTERVAL 1 DAY)` | 1 | `date_sub(d, 1)` |
| `current_date()` | 1 | `current_date()` — unchanged |
| `CAST(x AS TIMESTAMP)` | 1 | `CAST(x AS TIMESTAMP)` — unchanged |

**Verdict: use Databricks as the *build* environment if you want the credential, not as the *host*.** Running `dbt-databricks` against a Free Edition SQL warehouse and exporting the gold tables to Parquet is a genuinely stronger portfolio story than a local DuckDB build — real warehouse, real Unity Catalog, real jobs — and the Dash app still deploys to Vercel where it stays up, where the URL is anonymous, and where the Supabase auth keeps working unchanged. The one thing to check before committing to that path is how the source CSVs get into the workspace and where the exported Parquet lands, since outbound egress is restricted.

Two things remain unconfirmed in the Databricks documentation and would need a live workspace to settle: whether an incoming request restarts a stopped app automatically (the docs say a stopped app "is not accessible," and there is no GA idle-timeout setting — stop/start is manual or scripted), and the exact HTTP response a stopped app's URL returns.


### 3.7 Runtime bundle size, for planning the deployment

Measured installed sizes of the app's dependencies: `dash` 35.7 MB, `plotly` 36.4 MB, `pandas` 37.1 MB, `numpy` 19.6 MB, `pyarrow` 120.7 MB, `sqlalchemy` 8.6 MB, `flask` 0.3 MB — about **261 MB**, against a 500 MB Python bundle limit.

`pyarrow` is only an *optional extra* for pandas 3 (verified: pandas 3.1.1 imports and works without it, and the app's `datetime64` / `float64` / `str` dtype contract holds). So the **DuckDB route can drop `pyarrow` from the runtime bundle** and add the `duckdb` wheel (49.3 MB), taking the runtime footprint from ~261 MB to roughly **189 MB** — a ~72 MB saving, and more headroom than the Parquet route.

---

## 4. Work plan

### Phase 0 — Decisions (need your input)
1. **Analytics storage:** the gold-only DuckDB file or Parquet tables? — ✅ **decided in Phase 1: DuckDB file** (`my-dash-app/data/analytics.duckdb`, 4.47 MB). Same engine that built it, SQL available at runtime; both are verified working.
2. **Data scope:** serve all 60,398 fact rows, or replicate the old 10,000-row truncation? — ✅ **decided in Phase 1: all rows are shipped.** The old sample was arbitrary and understated revenue by ~50%.
3. **Auth:** option A (new Supabase project), B (self-hosted), or C (public demo)? — ❗ **still open** (recommend A — zero code change, migrations replayable; see §3.4)
4. **`pipeline_health`:** repurpose or remove? — ❗ **still open** (recommend repurpose)
5. **dbt scope:** keep `product_360` + the 15 analyses as offline SQL, or delete them? — ✅ **decided in Phase 1: keep.** `product_360` is built and exported with the other three gold tables; the 15 analyses remain as offline SQL.

### Phase 1 — Port the transformation (dbt-duckdb) — ✅ **COMPLETE (2026-11-06)**

1. ✅ Added `dbt-duckdb` + `duckdb` to `pyproject.toml` and `uv.lock` (2 packages, 34 new lock lines). `dbt-core 1.12.4` is compatible with `dbt-duckdb 1.11.1`, so no core pin change was needed.
2. ✅ Added `analytics_layer/macros/portable.sql` — the 9 `qe_*` dispatch macros, each with a `bigquery__` and a `duckdb__` branch. An unsupported adapter raises a compiler error instead of emitting wrong SQL.
3. ✅ Applied the macros across all 9 models and removed every `dbt.type_*` call (replaced with portable literals + `qe_string_type()`).
4. ✅ Edited the source test expressions in `_sources.yml` and repointed the source at the DuckDB bronze schema (`database:`/`schema:` instead of the BigQuery-only `project:`/`dataset:`).
5. ✅ Added `analytics_layer/profiles.yml` with a `duckdb` target (default) and the retained `bigquery` target.
6. ✅ `dbt build` → `PASS=115 WARN=17 ERROR=0 SKIP=0 TOTAL=132`.
7. ✅ Exported the gold-only artifact to `my-dash-app/data/analytics.duckdb` (4.47 MB).
8. ✅ **Guard:** the pandas PoC stays as the reference; the 26-check cross-verification matches, and `tests/test_gold_dataset.py` locks the numbers as a permanent regression test.
9. ✅ Added `Scripts/verify_shipped_gold.py` as a CI drift gate, with its own unit tests.
10. ✅ Committed the source CSVs to `data/raw/` so the pipeline is reproducible from a clean clone.
11. ✅ Rewrote the CI dbt job for the offline DuckDB target and removed the dead Cloud Run deploy job.

### Phase 2 — Swap the data access layer — ✅ **COMPLETE (2026-11-06)**
1. ✅ [my-dash-app/data_loader.py](file:///Users/roelsomido/demo-database/my-dash-app/data_loader.py): `get_bigquery_client` and the 3 gold queries are replaced by a loader over the bundled gold store — `duckdb.connect("my-dash-app/data/analytics.duckdb", read_only=True)` against the artifact built in Phase 1. It reproduces the existing merge, the `order_date >= 2010` filter, and the float64 normalization.
2. ✅ The 6 `audit_metadata` loaders are repointed, not deleted: `load_pipeline_health_summary`, `load_model_coverage_details`, `load_column_coverage_details`, `load_source_freshness`, `load_dbt_execution_logs` and `load_table_ingestion_logs` now read the shipped telemetry artifact through `my-dash-app/pipeline_telemetry.py`.
3. ✅ The cache backend in [utils/cache.py](file:///Users/roelsomido/demo-database/utils/cache.py) moved from `FileSystemCache` to `SimpleCache` — Vercel's bundle filesystem is read-only, and an in-process cache needs no writable path.
4. ✅ [tests/test_dashboard_regressions.py](file:///Users/roelsomido/demo-database/tests/test_dashboard_regressions.py) now guards the network at the socket level instead of patching `google.cloud.bigquery.Client`.
5. ✅ The BigQuery Costs tab and its callback are removed from `pipeline_health`; the ingestion chart is relabelled "CSV (Source)" vs "DuckDB Bronze (Destination)".
6. ✅ `Scripts/export_pipeline_telemetry.py` + `Scripts/verify_shipped_telemetry.py` build and gate the shipped telemetry artifact; the gate runs in CI after the dbt build.

### Phase 3 — Auth (option A: new Supabase project)
1. Create a free Supabase project; set `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `AUTH_APP_ORIGIN` in the Vercel env. **No code change** — nothing in the repo hardcodes a project ref.
2. Replay the 3 SQL migrations from [supabase/migrations/](file:///Users/roelsomido/demo-database/supabase/migrations) (`qe_password_attempt`, `qe_account_deletion_guard_ready`, and the administrator-access guard).
3. Re-enable the Google and GitHub OAuth providers in the Supabase console, and set the app redirect URL to `https://<app-origin>/auth/callback`.
4. Promote the first account to `qe_owner` in `app_metadata`, then confirm `/admin/users` lists, suspends, and deletes correctly.
5. Add a keep-wake scheduled job (Vercel cron) so the free-tier project does not sit idle past 7 days.
5. Rewrite `user_admin.py` to query the local users table instead of the Admin API.
6. Rewrite `auth_frontend/main.js` to drop `@supabase/supabase-js` (keep the same DOM contract so the CSS and templates still work); rebuild the bundle with `npm run build:auth`.

### Phase 4 — `pipeline_health` (repurpose)
1. ✅ **Done in Phase 2:** the telemetry source is now the build's `run_results.json` + `manifest.json` + the bronze load manifest, baked into the shipped artifact by `Scripts/export_pipeline_telemetry.py`. The build manifest already records source row counts and destination row counts; freshness is derived from the load timestamp.
2. Rewrite the KPIs/tabs against that source.
3. Update the header bell copy (it currently says "dbt Test Failures").
4. Delete or repoint `app_observability.py`.

### Phase 5 — Vercel packaging
**Status: ✅ Done (2026-11-06).** The changes below are the ones that shipped; the original draft is kept in the notes at the end of the section.

1. `wsgi.py` at the repository root is the WSGI entrypoint. It puts `my-dash-app/` on `sys.path` and re-exports the Flask server as `app`, the name Vercel loads:
   ```python
   APP_DIR = Path(__file__).resolve().parent / "my-dash-app"
   if str(APP_DIR) not in sys.path:
       sys.path.insert(0, str(APP_DIR))

   from app import server  # noqa: E402

   app = server
   ```
   Importing the module as `app` (rather than `__main__`) keeps Dash's `get_root_path()` resolution on `my-dash-app/`, so `assets/`, `pages/` and `templates/` are found — verified by `tests/test_vercel_deployment.py`.
2. `vercel.json` configures the function. The key is the resolved entrypoint file:
   ```json
   {
     "$schema": "https://openapi.vercel.sh/vercel.json",
     "functions": {
       "wsgi.py": {
         "maxDuration": 300,
         "excludeFiles": "{...}"
       }
     }
   }
   ```
   `excludeFiles` is a project-root glob. It drops `analytics_layer/`, `node_modules/`, `.venv/`, `data/`, `tests/`, `Notebooks/` and `my-dash-app/auth_frontend/`, and keeps `my-dash-app/assets/`, `my-dash-app/data/`, `my-dash-app/templates/`, `my-dash-app/pages/`, `my-dash-app/components/`, `utils/` and `wsgi.py`.
3. `.vercelignore` controls the upload. `.gitignore` is not consulted, so without it a local `vercel deploy` would upload the 1.2 GB virtualenv, the dbt project and the local credentials. `.env`, `.env.*` and `gcp-key.json` are excluded explicitly.
4. **Runtime dependencies separated from the build tooling.** `[project.dependencies]` now holds only what the app imports at request time (dash, dash-ag-grid, dash-bootstrap-components, duckdb, flask, flask-caching, flask-limiter, numpy, pandas, plotly, python-dotenv, pycountry, werkzeug). dbt, dbt-bigquery, dbt-duckdb, the warehouse drivers, jupyterlab, sqlfluff, ruff, pyrefly and pre-commit moved to the `dev` group. Vercel exports the project without the default groups, so the dev group never reaches the function. Installed footprint: **1.2 GB → 255 MB** across 46 packages, inside the 500 MB limit.
   - `python-dotenv` and `flask` were previously only transitive; they are imported directly, so they are now declared.
   - `requirements.txt` was regenerated as the runtime-only export (`uv export --frozen --no-dev --no-emit-project --no-header`). `tests/test_vercel_deployment.py` fails when it drifts from the lock.
5. The root `app.py` placeholder was relocated to `deploy_trigger.py`. It was a reserved entrypoint name, and it would have shadowed `import app` for the entrypoint's own import. The Dockerfile keeps `gunicorn app:server` from `/app/my-dash-app`, so the container path is unaffected.
6. Environment variables: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` and `AUTH_APP_ORIGIN` (must equal the deployment origin exactly), plus the server-only `SUPABASE_SERVICE_ROLE_KEY` for `/admin/users`. The data artifacts need no configuration: both paths resolve relative to the package.
7. `utils/audit_logger.py` no longer imports the warehouse client at module scope. It is wrapped in `try`/`except ImportError` and the function skips the write when the client is absent. The deployed runtime does not ship `google-cloud-bigquery`, and the retired BigQuery telemetry path is the only reason that package was ever imported. `tests/test_vercel_deployment.py` now boots the app with every build-only package blocked, so this class of bug fails the suite instead of the deployment.

**Why the entrypoint is `wsgi.py` and not `api/index.py`:**
- Vercel's documented entrypoint names are `app.py`, `index.py`, `server.py`, `main.py`, `wsgi.py` and `asgi.py`, at the root or inside `src/`/`app/`. `wsgi.py` at the root is discovered with no configuration at all.
- A file inside `/api` is only a *file-based function*. With a Flask framework preset the framework handles every request and `/api/*.py` do not become routes, so the file would either be dead weight or conflict with the preset.
- `tool.vercel.entrypoint` takes a `module:variable` value that maps to a file path. The documented examples are all package-qualified (`my_package.api:app` → `./my_package/api.py`). A root-level module would need the undocumented single-segment form, so relying on the default detection is the lower-risk choice.
- `wsgi.py` cannot be confused with a directory convention, and no other root file matches an entrypoint name.

**Vercel constraints confirmed against current docs (2026-08):**
- Entry: `app.py`/`index.py`/`server.py`/`main.py`/`wsgi.py`/`asgi.py` at root, `src/`, or `app/`; or `tool.vercel.entrypoint` in `pyproject.toml` ✅
- WSGI variable must be named `app` ✅
- `pyproject.toml` + `uv.lock` supported; Vercel prefers `pyproject.toml` over `requirements.txt` and exports without the default groups ✅
- Python 3.12 / 3.13 / 3.14 — project requires ≥3.12 ✅
- Duration: Hobby max 300s, Pro max 800s (default 300s) — **ample** for Dash callbacks ✅
- Bundle limit: 500 MB uncompressed (Python) — use `excludeFiles` ✅
- **Cold start:** Dash + Plotly + pandas import is the dominant cost (~2–4s). Mitigate by keeping the bundle lean. Data loading stays inside the cached loader — AGENTS.md §4 forbids module-scope preloading — and the shipped DuckDB file is opened read-only on first use, then reused from the in-process cache.
- No WebSocket needed — Dash callbacks are ordinary HTTP POSTs ✅

**Sandbox verification (read-only filesystem and read-only `HOME`):**
The deployment tree was reproduced the way Vercel would build it: `rsync` with `.vercelignore` as the exclude list, a fresh virtualenv holding only `requirements.txt`, and `chmod -R a-w` on the tree with `HOME` pointing at a read-only directory.

| Check | Result |
|---|---|
| Upload tree size | 7.5 MB (no `analytics_layer/`, `data/`, `Scripts/`, `tests/`, `node_modules/`) |
| Credentials in the upload tree | none — `.env*` and `gcp-key.json` absent |
| Runtime virtualenv | 255 MB across 46 packages, inside the 500 MB limit |
| Boot | entrypoint imported, Flask app served |
| `GET /` | 200 landing page |
| `GET /login` | 200 |
| `GET /auth/config` | 200, public URL and anon key only |
| `GET /dashboard`, `/customers`, `/pipeline-health` | 302 to `/login` without a session |
| `GET /assets/auth.bundle.js` | 200 |
| Without Supabase configuration | 503 on `/auth/config` and `/dashboard` — the guard fails closed before any data loader runs |
| Shipped gold database | 60,379 rows, 29,350,874.0 revenue, `float64` money column |
| Shipped telemetry artifact | 132 execution-log rows, all sections present |
| Disk writes | none — DuckDB opens the gold file `read_only=True`, the Flask cache is in-process |

The first run of this sandbox failed on `ModuleNotFoundError: No module named 'google'`: `utils/__init__.py` imports the retired BigQuery audit helper, which imported the warehouse client at module scope. The static import check in the test suite had missed it because it resolved `utils.audit_logger` to the `utils` package instead of the module inside it. Both are fixed, and the suite now boots the app with every build-only package blocked.

#### Original draft (superseded)
1. Add `vercel.json` with `functions` keyed by `api/index.py`.
2. Create `api/index.py` exposing `app = server`.
3. Add `[tool.vercel] entrypoint = "api:app"` to `pyproject.toml`.
4. Resolve the `my-dash-app` hyphen problem with a thin importable shim module at the root.
5. Replace the Dockerfile `CMD` (gunicorn `app:server`) — Vercel ignores it, but keep the Dockerfile for the Cloud Run path if you want to retain that option.
6. Environment variables: `NEXT_PUBLIC_SUPABASE_*` plus whatever the new data store needs.
7. Confirm the entrypoint doesn't collide with the root `app.py` placeholder — rename or relocate it.

### Phase 6 — Verification gate
Per [AGENTS.md §13.9](file:///Users/roelsomido/demo-database/AGENTS.md), from the repository root:
```bash
.venv/bin/python -B -m unittest discover -s tests -v
npm run build:auth
npm run test:auth
```
Plus new coverage required by §11:
- ✅ A test asserting the shipped gold database matches the expected figures — `tests/test_gold_dataset.py` (done in Phase 1).
- ✅ A test asserting the merged frame honours the dtype contract (naive datetime, float64 money) — `tests/test_gold_dataset.py` (done in Phase 1).
- ✅ A test asserting the shipped telemetry artifact matches the export rules and the reader contract — `tests/test_pipeline_telemetry.py` (done in Phase 2).
- ✅ A test asserting the deployment contract: the entrypoint exposes the WSGI callable, the auth guard runs before any data is served, every reachable third-party import is a runtime dependency, the app still boots when every build-only package is blocked, the bundle exclusions keep the runtime files, and `requirements.txt` matches the locked export — `tests/test_vercel_deployment.py` (done in Phase 5).
- ❗ A test asserting the KPI values on a known fixture (locks the numbers from §1.5) — still to write.
- ❗ Auth tests for the new provider (unauthenticated access, lockout, admin guard, self-deletion block) — Phase 3.

---

## 5. Risks and traps

| # | Risk | Mitigation |
|---|---|---|
| 1 | KPI numbers change because the old `LIMIT 10000` sample is gone | Decide explicitly in Phase 0; lock the new numbers in a fixture test so the change is deliberate, not a surprise |
| 2 | tz-aware dates break `filter_dataframe` | Keep the merged frame timezone-naive; cast in the loader, never in the source |
| 3 | `Decimal`/object dtype breaks `np.isfinite` in the margin chart | Force `float64` at load, exactly as the current code does |
| 4 | Exact-string category/country filters silently return zero rows | Do **not** title-case stored values; keep display-only title-casing where it already is (`overview.py:490`, `:616`) |
| 5 | The 102 superseded products' sales vanish from category/country charts | Preserve `prd_end_dt IS NULL` deliberately, or make the choice explicit in Phase 0 |
| 6 | Root `app.py` placeholder gets auto-detected by Vercel | ✅ Resolved in Phase 5 — the placeholder moved to `deploy_trigger.py` and the entrypoint is `wsgi.py` |
| 7 | `my-dash-app` hyphen breaks module imports for the entrypoint | ✅ Resolved in Phase 5 — `wsgi.py` puts the directory on `sys.path` and imports the app module from there |
| 8 | FileSystemCache write fails on Vercel's read-only FS | ✅ Resolved in Phase 2 — the cache is `SimpleCache` (in-process) |
| 9 | Cold starts make the first interaction feel slow | Lean bundle, module-scope data preload, `excludeFiles` |
| 10 | KPI formulas are duplicated in 4 places (`overview.py`, `app.py` modal, `app.py` CSV, `kpi_sparklines.py`) | Extract into one shared module during Phase 2 — the migration is the right moment to fix the drift risk |
| 11 | `dbt-core 1.12.4` vs `dbt-duckdb 1.11.1` version mismatch | Pin `dbt-core` to the adapter's supported range |
| 12 | Free Supabase tier pauses → dead demo link | If option A is chosen, add a keep-wake cron; option B/C avoids this entirely |
| 13 | `analytics_layer/target/` is gitignored — `manifest.json` won't exist in the deployment | ✅ Resolved in Phase 2 — the telemetry facts are baked into the shipped `my-dash-app/data/pipeline_telemetry.json`, and CI keeps it in sync with the build |
| 14 | CI workflow (`ci_pipeline.yml`) is hard-wired to BigQuery (`GCP_SA_KEY`, `dbt-bigquery` profile) | ✅ Resolved in Phase 1 — the dbt job now builds against DuckDB from the versioned CSVs, and the Cloud Run deploy job (targeting the deleted project) is removed |
| 15 | Vercel Hobby allows **non-commercial use only** | Fine for a portfolio demo; Pro is mandatory if it is ever monetized or used in a business |
| 16 | Exceeding a Hobby quota **pauses the account** until the 30-day cycle resets | Cache the dataset in-process so a cold start does not re-query; keep the per-request CPU far below the 4 CPU-hr allowance |
| 17 | The bundled file is immutable at runtime | Acceptable — the data is a static 2010–2014 snapshot. Any data change requires a redeploy, which is the correct behavior for a snapshot |
| 18 | Databricks Apps are **not anonymously accessible** — a visitor needs a Databricks account and workspace `CAN USE` | Do not host the public demo on Databricks Apps; use it as the dbt build environment only (§3.6) |
| 19 | Databricks Apps cap each file at 10 MB in the app directory | The 4.01 MB DuckDB file and 2.40 MB of Parquet fit; a larger export would fail the deployment |

---

## 6. Effort estimate

| Phase | Effort | Notes |
|---|---|---|
| 0. Decisions | 15 min | Your input |
| 1. dbt → DuckDB port | 2–3 h | ✅ Done (2026-11-06) |
| 2. Data access swap | 3–4 h | ✅ Done (2026-11-06) — loader, telemetry, cache, tests |
| 3. Auth rebuild (option B) | 10–14 h | Largest single item; drops OAuth PKCE |
| 3. Auth (option A) | 2–3 h | New project + re-apply 3 migrations |
| 3. Auth (option C) | 1 h | Delete the guard |
| 4. `pipeline_health` repurpose | 2–3 h | Reduced — the telemetry source already exists; ~1 h to remove instead |
| 5. Vercel packaging | 3–4 h | ✅ Done (2026-11-06) — entrypoint, bundle config, dependency split, tests |
| 6. Verification | 2–3 h | New + existing tests |

**With option A/C auth: ~2–3 days. With option B auth: ~3–4 days.**

---

## 7. Assets inventory

| Asset | Location | Status |
|---|---|---|
| Raw source CSVs | `data/raw/source_crm/`, `data/raw/source_erp/` (copied from `/Users/roelsomido/Source`) | ✅ Intact — **now in the repo**, so the pipeline rebuilds from a clean clone |
| dbt models/macros/analyses | `analytics_layer/` | ✅ Intact |
| Reference pandas implementation | `~/qoder_bq_rebuild_backup/` (was `/tmp/qoder_bq_rebuild/`) | ✅ Validated — promote to `tests/fixtures/` if useful |
| Rebuilt gold tables (Parquet) | `~/qoder_bq_rebuild_backup/gold/` | ✅ Validated |
| dbt-duckdb port (working project) | `~/qoder_bq_rebuild_backup/duck_project/` | ✅ Ported into `analytics_layer/` |
| Deployable gold DuckDB file | `my-dash-app/data/analytics.duckdb` | ✅ 4.47 MB, verified readable read-only, CI-gated for drift |
| Deployable telemetry artifact | `my-dash-app/data/pipeline_telemetry.json` | ✅ 81 KB, CI-gated for drift |
| Dash business logic | `my-dash-app/pages/`, `components/`, `utils/helpers.py` | ✅ Intact, backend-agnostic |
| Auth code | `my-dash-app/auth*.py`, `auth_frontend/` | ⚠️ Intact but provider-dead |
| Supabase RPC migrations | `supabase/migrations/` | ✅ Intact — replay on the new project |
| BigQuery credentials | `gcp-key.json` | ❌ Dead — remove from the deployment |
| `.env` | repo root, gitignored | ⚠️ Contains dead GCP + Supabase values |
