import os
import threading
import time
from pathlib import Path

import duckdb
import pandas as pd

# pyrefly: ignore [missing-import]
from pipeline_telemetry import (
    column_coverage_frame,
    execution_logs_frame,
    ingestion_logs_frame,
    model_coverage_frame,
    source_freshness_frame,
    summary_frame,
)

# pyrefly: ignore [missing-import]
from utils.cache import cache

DEFAULT_CACHE_TIMEOUT = 3600
DEFAULT_GOLD_DB = Path(__file__).resolve().parent / "data" / "analytics.duckdb"

# The merged dataset keeps a fixed shape so every consumer sees the same
# columns whether or not the database holds rows.
MERGED_COLUMNS = [
    "product_key",
    "customer_key",
    "order_date",
    "order_number",
    "quantity",
    "gross_sales_amount",
    "unit_price",
    "product_name",
    "category",
    "cost",
    "first_name",
    "last_name",
    "country",
]

MERGED_QUERY = """
    SELECT
        f.product_key,
        f.customer_key,
        f.order_date,
        f.order_number,
        f.quantity,
        f.gross_sales_amount,
        f.unit_price,
        p.product_name,
        p.category,
        p.cost,
        c.first_name,
        c.last_name,
        c.country
    FROM gold.fct_sales AS f
    LEFT JOIN gold.dim_products AS p ON f.product_key = p.product_key
    LEFT JOIN gold.dim_customers AS c ON f.customer_key = c.customer_key
    WHERE TRY_CAST(f.order_date AS DATE) >= DATE '2010-01-01'
    ORDER BY f.sales_item_key
"""

# Process-local hot copy of the merged dataset. This holds a shared, read-only
# frame for every user, never per-user state. Callbacks must not mutate it.
_DATASET_HOT_CACHE: dict = {"key": None, "value": None, "expires_at": 0.0}
_DATASET_HOT_CACHE_LOCK = threading.Lock()


def gold_database_path() -> Path:
    """Resolve the bundled gold database, honouring the deployment override."""
    override = os.environ.get("GOLD_DATABASE_PATH")
    if override:
        return Path(override).expanduser()
    return DEFAULT_GOLD_DB


@cache.memoize()
def load_and_prep_data(limit: int | None = None):
    """Read the gold tables from the bundled DuckDB database.

    The warehouse that used to serve these models is gone. The same dbt models
    now build into a single DuckDB file that ships with the app, so the read
    path is a local file instead of a query.
    """
    db_path = gold_database_path()
    if not db_path.exists():
        raise FileNotFoundError(
            f"Gold database not found at {db_path}. Build it with "
            "Scripts/export_gold_duckdb.py."
        )

    query = MERGED_QUERY
    if limit is not None:
        query += f" LIMIT {int(limit)}"

    connection = duckdb.connect(str(db_path), read_only=True)
    try:
        df_merged = connection.execute(query).df()
    finally:
        connection.close()

    # Keep the schema intact even when the database holds no rows.
    df_merged = df_merged.reindex(columns=MERGED_COLUMNS)
    df_merged["order_date"] = pd.to_datetime(
        df_merged["order_date"], errors="coerce"
    ).dt.tz_localize(None)

    # DuckDB returns DECIMAL as float64 already, but the cast keeps the
    # contract explicit: every aggregation downstream uses the vectorized
    # numeric path instead of an object dtype holding Decimal values.
    for money_column in ("gross_sales_amount", "unit_price", "cost"):
        df_merged[money_column] = pd.to_numeric(
            df_merged[money_column], errors="coerce"
        ).astype("float64")

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


def get_prepared_dataset(limit: int | None = None) -> pd.DataFrame:
    """Return the merged dataset, reusing one in-process copy per cache TTL.

    The dataset is read once from the bundled DuckDB file and then held in
    process memory, so a single filter change does not fan out into repeated
    reads across several independent Dash callbacks.

    The returned frame is shared by every caller, so treat it as read-only: build
    derived frames with ``filter_dataframe`` or ``.copy()`` instead of mutating it.
    Cache checks and population share a lock so concurrent misses load once and
    readers cannot observe a partially updated entry.
    """
    key = (limit,)
    with _DATASET_HOT_CACHE_LOCK:
        now = time.monotonic()
        if _DATASET_HOT_CACHE["key"] == key and now < _DATASET_HOT_CACHE["expires_at"]:
            return _DATASET_HOT_CACHE["value"]

        df_merged, _, _, _, _ = load_and_prep_data(limit=limit)
        _DATASET_HOT_CACHE["key"] = key
        _DATASET_HOT_CACHE["value"] = df_merged
        _DATASET_HOT_CACHE["expires_at"] = (
            time.monotonic() + _dataset_cache_ttl_seconds()
        )
        return df_merged


@cache.memoize(timeout=60)
def load_pipeline_health_summary():
    """Return the high-level pipeline health summary KPIs."""
    return summary_frame()


@cache.memoize()
def load_model_coverage_details():
    """Return per-model test coverage details for drill-down."""
    return model_coverage_frame()


@cache.memoize()
def load_column_coverage_details():
    """Return column-level test coverage details."""
    return column_coverage_frame()


@cache.memoize()
def load_source_freshness():
    """Return the age of the newest load of every source table."""
    return source_freshness_frame()


@cache.memoize()
def load_dbt_execution_logs(limit: int = 200):
    """Return the recorded model and test executions."""
    return execution_logs_frame(limit=limit)


@cache.memoize()
def load_table_ingestion_logs(
    days_back: int = 30, limit: int = 200, latest_only: bool = False
) -> pd.DataFrame:
    """Bound the load history; independently retain each table's latest snapshot."""
    if not isinstance(days_back, int) or not 1 <= days_back <= 365:
        raise ValueError("days_back must be between 1 and 365")
    if not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    return ingestion_logs_frame(
        days_back=days_back, limit=limit, latest_only=latest_only
    )
