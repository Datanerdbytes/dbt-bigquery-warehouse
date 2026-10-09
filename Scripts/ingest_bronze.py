"""
Flat-staging ingestion pipeline for SQL Server.

Walks a source folder, picks up every CSV, and loads it into the flat tables
in the `public` schema. Table name is derived from the CSV filename
(strip prefix), and the prefix is inferred from the parent folder name
(`source_crm` -> crm, `source_erp` -> erp). Unknown folders fall back to
the folder slug as-is.

Connection configuration (loaded from .env or the shell):
    DB_CONNECTION_STRING  SQLAlchemy mssql+pyodbc URL; alternatively use DB_* below.
    DB_DRIVER        e.g. ODBC Driver 18 for SQL Server
    DB_SERVER        e.g. localhost
    DB_DATABASE      e.g. Demo_Database
    DB_USERNAME      e.g. sa
    DB_PASSWORD      the secret
    DB_PORT          e.g. 1433 (optional, defaults to 1433)
    GCP_PROJECT_ID   e.g. your-gcp-project-id (required for BigQuery logging)

Usage:
    python Scripts/ingest_bronze.py <source_folder>

If <source_folder> is omitted, SOURCE_FOLDER from the environment is used.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from google.cloud import bigquery
from sqlalchemy import MetaData, Table, create_engine, text
from sqlalchemy.engine import URL, Engine, make_url

# pyrefly: ignore [missing-import]
from utils.logging_config import get_logger, sanitize_exception

logger = get_logger(__name__)

# ----- Configuration --------------------------------------------------------

CHUNKSIZE = 10_000

# Folders under the source root that should be skipped.
SKIP_FOLDERS = {".DS_Store", "__pycache__"}

# Folders whose name maps to a short prefix used in the flat table name
# (e.g. source_crm/cust_info.csv -> crm_cust_info).
SCHEMA_PREFIX_MAP = {
    "source_crm": "crm",
    "source_erp": "erp",
}


# ----- Helpers --------------------------------------------------------------


def load_env(env_file: Path | None = None) -> None:
    """Best-effort .env loader. Dependency-free."""
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
    connection_string = os.environ.get("DB_CONNECTION_STRING")
    if connection_string:
        connection_url = make_url(connection_string)
        if connection_url.drivername != "mssql+pyodbc":
            raise ValueError("DB_CONNECTION_STRING must use mssql+pyodbc")
        connection_url = connection_url.update_query_dict(
            {"driver": "ODBC Driver 18 for SQL Server", "TrustServerCertificate": "yes"}
        )
        return create_engine(connection_url, pool_pre_ping=True)
    driver = os.environ.get("DB_DRIVER", "ODBC Driver 18 for SQL Server")
    server = require_env("DB_SERVER")
    database = require_env("DB_DATABASE")
    username = require_env("DB_USERNAME")
    password = require_env("DB_PASSWORD")
    port = int(os.environ.get("DB_PORT", 1433))

    # Build SQL Server connection URL
    connection_url = URL.create(
        "mssql+pyodbc",
        username=username,
        password=password,
        host=server,
        port=port,
        database=database,
        query={"driver": driver, "TrustServerCertificate": "yes"},
    )

    return create_engine(connection_url, pool_pre_ping=True)


def get_engine() -> Engine:
    """Return the configured SQL Server engine (legacy build_engine is retained)."""
    return build_engine()


def insert_rows(engine: Engine, table, rows, batch_size: int = CHUNKSIZE):
    """Insert all batches atomically; never replay a potentially committed append.

    A SQLAlchemy Table or a schema-qualified table name is accepted. Failed
    statements roll back the entire attempt before retrying. A commit failure
    has an unknown outcome and is reported without retrying.
    """
    from sqlalchemy.exc import OperationalError

    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    records = list(rows)
    if not records:
        return 0, []
    target = table
    if isinstance(table, str):
        schema, separator, name = table.rpartition(".")
        target = Table(
            name if separator else table,
            MetaData(),
            schema=schema if separator else None,
            autoload_with=engine,
        )
    for attempt in range(3):
        statements_complete = False
        try:
            with engine.begin() as conn:
                for offset in range(0, len(records), batch_size):
                    conn.execute(target.insert(), records[offset : offset + batch_size])
                statements_complete = True
            return len(records), []
        except OperationalError as exc:
            if statements_complete or attempt == 2:
                return 0, [sanitize_exception(exc)]
            time.sleep(2.0 * (2**attempt))
    raise AssertionError("unreachable")


def verify_connection(engine: Engine) -> None:
    """Validate connection to the SQL Server database."""
    from sqlalchemy.exc import OperationalError

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT DB_NAME() AS db, SYSTEM_USER AS usr")).fetchone()
    except OperationalError as exc:
        raise RuntimeError(
            f"Failed to establish a connection to SQL Server: {exc}"
        ) from exc

    logger.info("Connected to SQL Server database successfully")


def _get_bigquery_client(project_id: str) -> bigquery.Client:
    """Create BigQuery client with retry logic for initialization/connection.

    Retries on GoogleAPICallError with exponential backoff (max 3 attempts, 2s base).
    """
    from google.api_core.exceptions import GoogleAPICallError

    max_retries = 3
    base_delay = 2.0

    for attempt in range(max_retries):
        try:
            return bigquery.Client(project=project_id)
        except GoogleAPICallError as exc:
            if attempt == max_retries - 1:
                logger.error(
                    "BigQuery client initialization failed after %d attempts: %s",
                    max_retries,
                    exc,
                )
                raise RuntimeError(
                    f"Failed to initialize BigQuery client after {max_retries} attempts"
                ) from exc
            delay = base_delay * (2**attempt)
            logger.warning(
                "BigQuery client initialization attempt %d/%d failed: %s. Retrying in %.1fs...",
                attempt + 1,
                max_retries,
                exc,
                delay,
            )
            time.sleep(delay)

    # Should not reach here, but satisfy type checker
    raise RuntimeError(
        f"Failed to initialize BigQuery client after {max_retries} attempts"
    )


def log_table_ingestion_to_bigquery(
    run_timestamp: datetime,
    resource_type: str,
    table_name: str,
    target_table: str,
    source_rows: int,
    destination_rows: int,
    duration_seconds: float,
    status: str,
    error_message: str | None = None,
) -> None:
    """Record table ingestion metrics directly into BigQuery audit metadata."""
    project_id = require_env("GCP_PROJECT_ID")
    client = _get_bigquery_client(project_id)
    table_id = f"{project_id}.audit_metadata.table_ingestion_logs"

    log_record = [
        {
            "log_id": str(uuid.uuid4()),
            "run_timestamp": run_timestamp.isoformat(),
            "resource_type": resource_type,
            "table_name": table_name,
            "target_table": target_table,
            "source_rows": source_rows,
            "destination_rows": destination_rows,
            "duration_seconds": duration_seconds,
            "status": status,
            "error_message": error_message or "",
        }
    ]

    df_log = pd.DataFrame(log_record)

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND
    )

    # Retry on BigQuery errors with exponential backoff (max 3 attempts, 2s base)
    from google.api_core.exceptions import GoogleAPICallError

    max_retries = 3
    base_delay = 2.0

    for attempt in range(max_retries):
        try:
            job = client.load_table_from_dataframe(
                df_log, table_id, job_config=job_config
            )
            job.result()
            return
        except GoogleAPICallError as exc:
            if attempt == max_retries - 1:
                logger.error(
                    "BigQuery logging failed after %d attempts: %s", max_retries, exc
                )
                raise
            delay = base_delay * (2**attempt)
            logger.warning(
                "BigQuery logging attempt %d/%d failed: %s. Retrying in %.1fs...",
                attempt + 1,
                max_retries,
                exc,
                delay,
            )
            time.sleep(delay)


def schema_prefix_for(folder_name: str) -> str:
    """Return the flat table prefix for a given source folder name."""
    return SCHEMA_PREFIX_MAP.get(folder_name, folder_name)


def discover_csvs(source_root: Path) -> Iterable[tuple[Path, str]]:
    """Yield (csv_path, target_table) pairs discovered under source_root."""
    if not source_root.is_dir():
        raise FileNotFoundError(f"Source folder not found: {source_root}")

    for folder in sorted(source_root.iterdir()):
        if not folder.is_dir() or folder.name in SKIP_FOLDERS:
            continue
        prefix = schema_prefix_for(folder.name)
        for csv_path in sorted(folder.glob("*.csv")):
            table = f"{prefix}_{csv_path.stem}".lower()
            yield csv_path, table


def ingest_csv(engine: Engine, csv_path: Path, schema: str, table: str) -> int:
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip().str.lower()

    # Re-runnable: TRUNCATE the target table first so re-running doesn't duplicate rows.
    # Retry on OperationalError with exponential backoff (max 3 attempts, 2s base)
    from sqlalchemy.exc import OperationalError

    max_retries = 3
    base_delay = 2.0

    for attempt in range(max_retries):
        try:
            with engine.begin() as conn:
                preparer = engine.dialect.identifier_preparer
                target = f"{preparer.quote_schema(schema)}.{preparer.quote(table)}"
                conn.execute(text(f"TRUNCATE TABLE {target}"))
                df.to_sql(
                    name=table,
                    con=conn,
                    schema=schema,
                    if_exists="append",
                    index=False,
                    chunksize=CHUNKSIZE,
                )
            return len(df)
        except OperationalError as exc:
            if attempt == max_retries - 1:
                raise RuntimeError(
                    f"Failed to ingest {table} after {max_retries} attempts"
                ) from exc
            delay = base_delay * (2**attempt)
            logger.warning(
                "Attempt %d/%d failed for %s: %s. Retrying in %.1fs...",
                attempt + 1,
                max_retries,
                table,
                sanitize_exception(exc),
                delay,
            )
            time.sleep(delay)

    # Should not reach here, but satisfy type checker
    raise RuntimeError(f"Failed to ingest {table} after {max_retries} attempts")


def main(argv: list[str] | None = None) -> int:
    # Lazy import also keeps environment/credential access out of module import.
    from utils.audit_logger import AuditLogger

    load_env()
    argv = sys.argv if argv is None else argv
    source = argv[1] if len(argv) > 1 else os.environ.get("SOURCE_FOLDER")
    audit = AuditLogger()
    script = "ingest_bronze"
    params = {"source_folder": source}
    audit.log_start(script, params)
    engine = None
    try:
        if not source:
            raise ValueError("Usage: python ingest_bronze.py <source_folder>")
        source_root = Path(source)
        engine = get_engine()
        verify_connection(engine)
        pairs = list(discover_csvs(source_root))
        failures = []
        total_rows = 0
        for csv_path, table in pairs:
            started = time.monotonic()
            timestamp = datetime.now(UTC)
            try:
                rows = ingest_csv(engine, csv_path, "public", table)
                total_rows += rows
            except Exception as exc:
                failures.append(sanitize_exception(exc))
                rows = 0
                error = sanitize_exception(exc)
            else:
                error = None
            # Telemetry must not convert a completed load into a failed load.
            try:
                log_table_ingestion_to_bigquery(
                    timestamp,
                    "csv_ingestion",
                    csv_path.name,
                    f"public.{table}",
                    rows,
                    rows,
                    time.monotonic() - started,
                    "fail" if error else "success",
                    error,
                )
            except Exception as exc:
                logger.warning("Table audit unavailable: %s", sanitize_exception(exc))
        if failures:
            audit.log_failure(script, "; ".join(failures), params)
            return 1
        audit.log_success(script, {"tables": len(pairs), "rows": total_rows})
        return 0
    except Exception as exc:
        logger.error("Bronze ingestion failed: %s", sanitize_exception(exc))
        audit.log_failure(script, sanitize_exception(exc), params)
        return 2 if not source else 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
