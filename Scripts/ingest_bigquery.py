"""Extract SQL Server bronze tables into BigQuery with runtime configuration."""

import logging
import os
import re
import sys
import time

import pandas as pd
from dotenv import load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url

from utils.audit_logger import AuditLogger
from utils.logging_config import sanitize_exception

logger = logging.getLogger(__name__)
TABLES = [
    "crm_cust_info",
    "crm_prd_info",
    "crm_sales_details",
    "erp_cust_az12",
    "erp_loc_a101",
    "erp_px_cat_g1v2",
]
# Compatibility for callers that used the previous constant name.
TABLES_TO_INGEST = TABLES
TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def get_bq_client():
    """Create a client at runtime, using a configured key or ADC."""
    project = os.getenv("TARGET_PROJECT") or os.getenv("GCP_PROJECT_ID")
    if not project:
        raise ValueError("Missing TARGET_PROJECT or GCP_PROJECT_ID")
    key_path = os.getenv("GCP_KEY_PATH")
    if key_path:
        credentials = service_account.Credentials.from_service_account_file(key_path)
        return bigquery.Client(project=project, credentials=credentials)
    return bigquery.Client(project=project)


def get_source_engine():
    """Create the SQL Server source engine without connecting at import."""
    connection_string = os.getenv("DB_CONNECTION_STRING")
    if connection_string:
        url = make_url(connection_string)
        if url.drivername != "mssql+pyodbc":
            raise ValueError("DB_CONNECTION_STRING must use mssql+pyodbc")
        if url.query.get("driver") != "ODBC Driver 18 for SQL Server":
            raise ValueError(
                "DB_CONNECTION_STRING must use ODBC Driver 18 for SQL Server"
            )
    else:
        values = {
            name: os.getenv(name)
            for name in ("DB_SERVER", "DB_DATABASE", "DB_USERNAME", "DB_PASSWORD")
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise ValueError("Missing database configuration: " + ", ".join(missing))
        url = URL.create(
            "mssql+pyodbc",
            username=values["DB_USERNAME"],
            password=values["DB_PASSWORD"],
            host=values["DB_SERVER"],
            port=int(os.getenv("DB_PORT", "1433")),
            database=values["DB_DATABASE"],
            query={"driver": "ODBC Driver 18 for SQL Server"},
        )
    return create_engine(url, pool_pre_ping=True)


def _validate_table_name(table_name: str) -> str:
    if not isinstance(table_name, str) or not TABLE_NAME_RE.fullmatch(table_name):
        raise ValueError(f"Invalid table name: {table_name!r}")
    return table_name


def _build_query(table_name: str) -> str:
    return f"SELECT * FROM [bronze].[{_validate_table_name(table_name)}]"


def validate_connection(db_engine):
    """Verify the SQL Server source responds before starting uploads."""
    with db_engine.connect() as conn:
        conn.exec_driver_sql("SELECT DB_NAME()").fetchone()


def extract_and_load(bq_client=None, db_engine=None, audit=None):
    """Load every table and raise if any failed; release owned engines."""
    own_engine = db_engine is None
    engine = db_engine
    try:
        bq_client = bq_client or get_bq_client()
        engine = engine if engine is not None else get_source_engine()
        audit = audit if audit is not None else AuditLogger()
        project = os.getenv("TARGET_PROJECT") or os.getenv("GCP_PROJECT_ID")
        if not project:
            raise ValueError("Missing TARGET_PROJECT or GCP_PROJECT_ID")
        dataset = os.getenv("TARGET_DATASET") or "bronze"
        validate_connection(engine)
        failures = []
        loaded_rows = 0
        for table_name in TABLES:
            start_time = time.monotonic()
            destination = f"{project}.{dataset}.{table_name}"
            params = {"table": table_name, "target_table": destination}
            audit.log_start("ingest_bigquery.table", params)
            try:
                with engine.connect() as conn:
                    frame = pd.read_sql(_build_query(table_name), con=conn)
                job_config = bigquery.LoadJobConfig(
                    write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
                    autodetect=True,
                )
                bq_client.load_table_from_dataframe(
                    frame, destination, job_config=job_config
                ).result()
                loaded_rows += len(frame)
                audit.log_success(
                    "ingest_bigquery.table",
                    {
                        **params,
                        "rows_affected": len(frame),
                        "duration_sec": time.monotonic() - start_time,
                    },
                )
            except Exception as exc:
                failures.append(table_name)
                audit.log_failure("ingest_bigquery.table", exc, params)
                logger.error(
                    "Failed to process %s: %s", table_name, sanitize_exception(exc)
                )
        if failures:
            raise RuntimeError(
                "BigQuery ingestion failed for tables: " + ", ".join(failures)
            )
        return {"tables_loaded": len(TABLES), "rows_affected": loaded_rows}
    finally:
        if own_engine and engine is not None:
            engine.dispose()


def main():
    """Load local configuration and run the ingestion with audit events."""
    load_dotenv()
    audit = AuditLogger()
    engine = None
    params = {"tables": TABLES.copy()}
    audit.log_start("ingest_bigquery", params)
    try:
        client = get_bq_client()
        engine = get_source_engine()
        stats = extract_and_load(client, engine, audit)
        audit.log_success("ingest_bigquery", stats)
        return 0
    except Exception as exc:
        audit.log_failure("ingest_bigquery", exc, params)
        logger.error("BigQuery ingestion failed: %s", sanitize_exception(exc))
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    from utils.logging_config import setup_logging

    setup_logging()
    sys.exit(main())
