import os
import re
import time
import uuid
from urllib.parse import quote_plus

import pandas as pd
from dotenv import load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account
from sqlalchemy import create_engine
from sqlalchemy import exc as sqla_exc

# pyrefly: ignore [missing-import]
from utils.audit_logger import log_execution_to_bigquery

# pyrefly: ignore [missing-import]
from utils.logging_config import get_logger, sanitize_exception

# 1. Load environment variables from .env file
load_dotenv()

logger = get_logger(__name__)

# 2. Retrieve variables from environment
SERVER = os.getenv("DB_SERVER", "127.0.0.1")
DATABASE = os.getenv("DB_DATABASE", "Demo_Database")
USERNAME = os.getenv("DB_USERNAME", "postgres")
PASSWORD = os.getenv("DB_PASSWORD", "")
PORT = os.getenv("DB_PORT", "5432")

encoded_password = quote_plus(PASSWORD) if PASSWORD else ""

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
KEY_PATH = os.getenv("GCP_KEY_PATH")
TARGET_DATASET = os.getenv("TARGET_DATASET", "bronze")


def _init_clients():
    """Create and return the BigQuery and PostgreSQL clients.

    Validates that database credentials are present before proceeding.
    Raises ``ValueError`` if credentials are missing.
    """
    if not USERNAME:
        raise ValueError("Missing database username in .env file!")

    credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
    bq_client = bigquery.Client(project=GCP_PROJECT_ID, credentials=credentials)

    # PostgreSQL connection URL using psycopg2
    sql_conn_str = f"postgresql+psycopg2://{USERNAME}:{encoded_password}@{SERVER}:{PORT}/{DATABASE}"
    db_engine = create_engine(sql_conn_str, pool_pre_ping=True)

    return credentials, bq_client, db_engine


# 4. Tables to Ingest (Flat Staging in public schema)
TABLES_TO_INGEST = [
    "crm_cust_info",
    "crm_prd_info",
    "crm_sales_details",
    "erp_cust_az12",
    "erp_loc_a101",
    "erp_px_cat_g1v2",
]

# Strict allowlist for table names. Prevents SQL injection via identifier
# interpolation: only ASCII letters, digits, and underscores are permitted,
# and the first character must be a letter or underscore.
TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_table_name(table_name: str) -> str:
    """Validate *table_name* against the strict allowlist."""
    if not isinstance(table_name, str) or not TABLE_NAME_RE.fullmatch(table_name):
        raise ValueError(
            f"Invalid table name: {table_name!r}. "
            "Only letters, digits, and underscores are allowed, "
            "starting with a letter or underscore."
        )
    return table_name


def _build_query(table_name: str) -> str:
    """Return a parameterized SELECT for *table_name* from the public schema."""
    safe_name = _validate_table_name(table_name)
    return f"SELECT * FROM public.{safe_name}"


def validate_connection(db_engine):
    """Verify the PostgreSQL database connection is responsive."""
    try:
        with db_engine.connect() as conn:
            conn.exec_driver_sql("SELECT current_database()").fetchone()
            logger.info("PostgreSQL database connection validated successfully.")
    except sqla_exc.OperationalError as exc:
        raise RuntimeError(
            f"Failed to establish a connection to PostgreSQL: {exc}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Database connection validation failed: {exc}") from exc


def extract_and_load():
    execution_id = str(uuid.uuid4())  # Generate a unique execution ID for this run

    # Initialize clients (validates credentials and establishes connections)
    credentials, bq_client, db_engine = _init_clients()

    # Verify connection before ingestion
    validate_connection(db_engine)

    for table_name in TABLES_TO_INGEST:
        logger.info("Processing table: %s", table_name)
        start_time = time.time()
        destination_table = f"{GCP_PROJECT_ID}.{TARGET_DATASET}.{table_name}"

        try:
            query = _build_query(table_name)
            logger.info("Reading data from PostgreSQL...")
            with db_engine.connect() as conn:
                df = pd.read_sql(query, con=conn)
            logger.info("Extracted %d rows.", len(df))

            job_config = bigquery.LoadJobConfig(
                write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
                autodetect=True,
            )

            logger.info("Loading into BigQuery: %s", destination_table)
            load_job = bq_client.load_table_from_dataframe(
                df, destination_table, job_config=job_config
            )

            load_job.result()
            duration = time.time() - start_time
            logger.info("Successfully loaded %s into BigQuery!", table_name)

            # Log success to BigQuery audit
            log_execution_to_bigquery(
                execution_id=execution_id,
                resource_type="sql_to_bigquery",
                node_name=table_name,
                target_table=destination_table,
                status="pass",
                duration_sec=duration,
                rows_affected=len(df),
            )

        except Exception as exc:
            duration = time.time() - start_time
            logger.error(
                "Failed to process %s: %s", table_name, sanitize_exception(exc)
            )

            # Log failure to BigQuery audit
            log_execution_to_bigquery(
                execution_id=execution_id,
                resource_type="sql_to_bigquery",
                node_name=table_name,
                target_table=destination_table,
                status="fail",
                duration_sec=duration,
                rows_affected=0,
                error_msg=str(exc),
            )


if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    from utils.logging_config import setup_logging

    setup_logging()
    extract_and_load()
