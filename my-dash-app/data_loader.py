import functools
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from google.cloud import bigquery
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL
from utils.cache import cache

DEFAULT_DRIVER = "ODBC Driver 18 for SQL Server"
DEFAULT_CACHE_TIMEOUT = 3600

# Process-local hot copy of the merged dataset. This holds a shared, read-only
# frame for every user, never per-user state. Callbacks must not mutate it.
_DATASET_HOT_CACHE: dict = {"key": None, "value": None, "expires_at": 0.0}


@functools.lru_cache(maxsize=1)
def get_bigquery_client():
    """Helper function to initialize the BigQuery client from environment variables."""
    load_dotenv()
    key_file_path = os.environ.get("GCP_KEY_PATH")
    project_id = os.environ.get("GCP_PROJECT_ID", "quantum-echo-data-eng-prod")

    if key_file_path and os.path.exists(key_file_path):
        return bigquery.Client.from_service_account_json(
            key_file_path, project=project_id
        )
    return bigquery.Client(project=project_id)


@cache.memoize()
def load_and_prep_data(limit: int = 10000):
    client = get_bigquery_client()

    query_sales = """
        SELECT 
            product_key, 
            customer_key,
            order_date, 
            order_number,
            quantity,
            gross_sales_amount, 
            unit_price 
        FROM `quantum-echo-data-eng-prod.gold.fct_sales`
        WHERE order_date >= DATE '2010-01-01'
        LIMIT @limit
    """

    query_products = """
        SELECT 
            product_key,
            product_name, 
            category 
        FROM `quantum-echo-data-eng-prod.gold.dim_products`
    """

    query_customers = """
        SELECT 
            customer_key,
            first_name, 
            last_name,
            country
        FROM `quantum-echo-data-eng-prod.gold.dim_customers`
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("limit", "INT64", limit)]
    )

    df_sales = client.query(query_sales, job_config=job_config).to_dataframe()
    df_products = client.query(query_products).to_dataframe()
    df_customers = client.query(query_customers).to_dataframe()

    # Keep the schema intact even when a source returns no rows.
    df_sales = pd.DataFrame() if df_sales is None else df_sales
    df_products = pd.DataFrame() if df_products is None else df_products
    df_customers = pd.DataFrame() if df_customers is None else df_customers
    df_sales = df_sales.reindex(
        columns=[
            "product_key",
            "customer_key",
            "order_date",
            "order_number",
            "quantity",
            "gross_sales_amount",
            "unit_price",
        ]
    )
    df_products = df_products.reindex(
        columns=["product_key", "product_name", "category"]
    )
    df_customers = df_customers.reindex(
        columns=["customer_key", "first_name", "last_name", "country"]
    )

    df_sales["order_date"] = pd.to_datetime(df_sales["order_date"], errors="coerce")

    df_merged = df_sales.merge(df_products, on="product_key", how="left").merge(
        df_customers, on="customer_key", how="left"
    )

    df_merged["order_date"] = pd.to_datetime(df_merged["order_date"], errors="coerce")
    df_merged = df_merged[df_merged["order_date"].dt.year >= 2010].copy()

    # BigQuery returns NUMERIC as object dtype holding Decimal values, which makes
    # every aggregation slow. Normalize the monetary columns to float64 once so the
    # chart and KPI aggregations use the vectorized numeric path.
    for money_column in ("gross_sales_amount", "unit_price"):
        df_merged[money_column] = pd.to_numeric(
            df_merged[money_column], errors="coerce"
        )

    min_data_date = None
    max_data_date = None
    if not df_merged.empty:
        min_data_date = df_merged["order_date"].min().strftime("%Y-%m-%d")
        max_data_date = df_merged["order_date"].max().strftime("%Y-%m-%d")

    unique_categories = sorted(df_merged["category"].dropna().unique())
    category_options = [{"label": "All Categories", "value": "ALL"}] + [
        {"label": str(cat).title(), "value": cat} for cat in unique_categories
    ]

    unique_countries = sorted(df_merged["country"].dropna().unique())
    country_options = [{"label": "All Countries", "value": "ALL"}] + [
        {"label": str(cntry).title(), "value": cntry} for cntry in unique_countries
    ]

    return df_merged, min_data_date, max_data_date, category_options, country_options


def _dataset_cache_ttl_seconds() -> float:
    """Resolve the dataset hot-cache TTL from the Flask-Caching configuration."""
    timeout = DEFAULT_CACHE_TIMEOUT
    config = getattr(cache, "config", None) or {}
    try:
        configured = config.get("CACHE_DEFAULT_TIMEOUT", DEFAULT_CACHE_TIMEOUT)
    except AttributeError:
        configured = DEFAULT_CACHE_TIMEOUT
    try:
        resolved = float(configured)
    except (TypeError, ValueError):
        resolved = 0.0
    return resolved if resolved > 0 else float(DEFAULT_CACHE_TIMEOUT)


def get_prepared_dataset(limit: int = 10000) -> pd.DataFrame:
    """Return the merged dataset, reusing one in-process copy per cache TTL.

    ``load_and_prep_data`` is memoized on disk, so each call unpickles a full
    DataFrame. A single filter change fans out into several independent Dash
    callbacks, each of which used to pay that deserialization cost. Keeping one
    process-local copy removes the repeated work.

    The returned frame is shared by every caller, so treat it as read-only: build
    derived frames with ``filter_dataframe`` or ``.copy()`` instead of mutating it.
    """
    key = (limit,)
    now = time.monotonic()
    if _DATASET_HOT_CACHE["key"] == key and now < _DATASET_HOT_CACHE["expires_at"]:
        return _DATASET_HOT_CACHE["value"]

    df_merged, _, _, _, _ = load_and_prep_data(limit=limit)
    _DATASET_HOT_CACHE["key"] = key
    _DATASET_HOT_CACHE["value"] = df_merged
    _DATASET_HOT_CACHE["expires_at"] = now + _dataset_cache_ttl_seconds()
    return df_merged


@cache.memoize(timeout=60)
def load_pipeline_health_summary():
    """Fetches high-level pipeline health summary KPIs from audit_metadata."""
    client = get_bigquery_client()
    query = """
        SELECT
            last_dbt_run, passed_tests, failed_tests, warning_tests,
            avg_model_duration_sec, total_models, total_columns,
            total_columns_with_tests, overall_column_coverage_pct, total_tests,
            models_fully_covered, models_well_covered, models_poorly_covered,
            overall_system_status
        FROM `quantum-echo-data-eng-prod.audit_metadata.v_latest_pipeline_health`
    """
    return client.query(query).to_dataframe()


@cache.memoize()
def load_model_coverage_details():
    """Fetches per-model test coverage details for drill-down."""
    client = get_bigquery_client()
    query = """
        SELECT
            model_name,
            schema,
            model_total_columns as total_columns,
            model_columns_with_tests as columns_with_tests,
            model_column_coverage_pct as column_coverage_pct,
            model_total_tests as total_tests
        FROM `quantum-echo-data-eng-prod.audit_metadata.dbt_test_coverage`
        WHERE DATE(calculated_at) = (
            SELECT MAX(DATE(calculated_at))
            FROM `quantum-echo-data-eng-prod.audit_metadata.dbt_test_coverage`
        )
        GROUP BY model_name, schema, model_total_columns, model_columns_with_tests, model_column_coverage_pct, model_total_tests
        ORDER BY model_column_coverage_pct ASC, model_name
    """
    return client.query(query).to_dataframe()


@cache.memoize()
def load_column_coverage_details():
    """Fetches column-level test coverage details."""
    client = get_bigquery_client()
    query = """
        SELECT
            model_name,
            schema,
            column_name,
            column_description,
            data_type,
            test_count,
            test_names,
            has_tests
        FROM `quantum-echo-data-eng-prod.audit_metadata.dbt_test_coverage`
        WHERE DATE(calculated_at) = (
            SELECT MAX(DATE(calculated_at))
            FROM `quantum-echo-data-eng-prod.audit_metadata.dbt_test_coverage`
        )
        ORDER BY model_name, has_tests ASC, column_name
    """
    return client.query(query).to_dataframe()


@cache.memoize()
def load_source_freshness():
    """Fetches source (bronze) table freshness from ingestion logs."""
    client = get_bigquery_client()
    query = """
        SELECT
            node_name as source_table,
            target_table,
            run_timestamp as last_loaded,
            TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), run_timestamp, HOUR) as hours_since_load,
            TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), run_timestamp, MINUTE) as minutes_since_load
        FROM `quantum-echo-data-eng-prod.audit_metadata.dbt_execution_logs`
        WHERE resource_type = 'sql_to_bigquery'
          AND status IN ('pass', 'success')
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY target_table, node_name
            ORDER BY run_timestamp DESC, execution_id DESC
        ) = 1
        ORDER BY run_timestamp DESC
    """
    return client.query(query).to_dataframe()


@cache.memoize()
def load_dbt_execution_logs(limit: int = 200):
    """Fetches detailed dbt test and model execution logs."""
    client = get_bigquery_client()
    query = """
        SELECT
            execution_id,
            run_timestamp,
            resource_type,
            node_name,
            target_table,
            column_name,
            status,
            execution_time_seconds,
            rows_affected,
            error_message
        FROM `quantum-echo-data-eng-prod.audit_metadata.dbt_execution_logs`
        ORDER BY run_timestamp DESC
        LIMIT @limit
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("limit", "INT64", limit)]
    )
    return client.query(query, job_config=job_config).to_dataframe()


# BigQuery Cost & Query Monitoring
@cache.memoize(timeout=3600)
def load_bigquery_cost_metrics(days_back: int = 30) -> pd.DataFrame:
    client = get_bigquery_client()
    query = f"""
        SELECT
            DATE(creation_time) AS execution_date,
            user_email,
            job_type,
            COUNT(1) AS total_queries,
            SUM(total_bytes_billed) AS total_bytes_billed,
            SUM(total_bytes_processed) AS total_bytes_processed,
            ROUND(SUM(total_slot_ms) / 1000 / 60, 2) AS total_slot_minutes,
            ROUND(AVG(total_slot_ms) / 1000, 2) AS avg_slot_seconds,
            ROUND(AVG(TIMESTAMP_DIFF(end_time, start_time, SECOND)), 2) AS avg_duration_seconds
        FROM `region-us-central1`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
        WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days_back} DAY)
          AND state = 'DONE'
        GROUP BY 1, 2, 3
        ORDER BY execution_date DESC
    """
    return client.query(query).to_dataframe()


@cache.memoize(timeout=1800)
def load_expensive_queries(limit: int = 25) -> pd.DataFrame:
    client = get_bigquery_client()
    query = f"""
        SELECT
            creation_time,
            user_email,
            query,
            total_bytes_billed,
            ROUND(total_bytes_processed / 1024 / 1024 / 1024, 2) AS gb_processed,
            ROUND(total_slot_ms / 1000, 2) as slot_seconds,
            TIMESTAMP_DIFF(end_time, start_time, SECOND) AS duration_seconds
        FROM `region-us-central1`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
        WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
          AND state = 'DONE'
          AND job_type = 'QUERY'
        ORDER BY total_bytes_billed DESC
        LIMIT {limit}
    """
    return client.query(query).to_dataframe()


def load_env(env_file: Path | None = None) -> None:
    """Best-effort .env loader."""
    candidate = env_file or (Path.cwd() / ".env")
    if not candidate.exists():
        return
    for raw in candidate.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def build_engine() -> Engine:
    server = require_env("DB_SERVER")
    database = require_env("DB_DATABASE")
    username = require_env("DB_USERNAME")
    password = require_env("DB_PASSWORD")
    driver = os.environ.get("DB_DRIVER", DEFAULT_DRIVER)

    host = server.split(",")[0].split(":")[0]
    port = 1433

    odbc_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={host},{port};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        f"Encrypt=no;"
        f"TrustServerCertificate=yes;"
    )

    connection_url = URL.create("mssql+pyodbc", query={"odbc_connect": odbc_str})

    return create_engine(connection_url, pool_pre_ping=True, fast_executemany=True)


def verify_connection(engine: Engine) -> None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT DB_NAME() AS db, SUSER_SNAME() AS usr")
        ).fetchone()
    print(f"Connected to '{row.db}' as '{row.usr}'")


@cache.memoize()
def load_table_ingestion_logs(
    days_back: int = 30, limit: int = 200, latest_only: bool = False
) -> pd.DataFrame:
    """Bound audit history; independently retain each table's latest parity snapshot."""
    if not isinstance(days_back, int) or not 1 <= days_back <= 365:
        raise ValueError("days_back must be between 1 and 365")
    if not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    try:
        client = get_bigquery_client()
        query = """
            SELECT 
                CAST(log_id AS STRING) AS log_id,
                run_timestamp,
                resource_type,
                table_name,
                target_table,
                source_rows,
                destination_rows,
                destination_rows AS rows_inserted,
                duration_seconds,
                status,
                error_message
            FROM `quantum-echo-data-eng-prod.audit_metadata.table_ingestion_logs`
        """
        if latest_only:
            # No time cutoff here: a stale table must remain visible in the chart.
            query += """
                QUALIFY ROW_NUMBER() OVER (
                    PARTITION BY resource_type, table_name, target_table
                    ORDER BY run_timestamp DESC, log_id DESC
                ) = 1
                ORDER BY run_timestamp DESC, log_id DESC
            """
            job_config = bigquery.QueryJobConfig()
        else:
            query += """
                WHERE run_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days_back DAY)
                ORDER BY run_timestamp DESC, log_id DESC
                LIMIT @limit
            """
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("days_back", "INT64", days_back),
                    bigquery.ScalarQueryParameter("limit", "INT64", limit),
                ]
            )
        df = client.query(query, job_config=job_config).to_dataframe()

        if not df.empty and "run_timestamp" in df.columns:
            df["run_timestamp"] = pd.to_datetime(df["run_timestamp"])

        return df
    except Exception as e:
        print(f"Warning: Could not load table ingestion logs from BigQuery: {e}")
        return pd.DataFrame(
            columns=[
                "log_id",
                "run_timestamp",
                "resource_type",
                "table_name",
                "target_table",
                "source_rows",
                "destination_rows",
                "rows_inserted",
                "duration_seconds",
                "status",
                "error_message",
            ]
        )
