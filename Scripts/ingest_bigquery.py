import os
import re
import pandas as pd
import time
import uuid
from urllib.parse import quote_plus
from utils.audit_logger import log_execution_to_bigquery
from dotenv import load_dotenv
from sqlalchemy import create_engine, exc as sqla_exc
from google.cloud import bigquery
from google.oauth2 import service_account

# 1. Load environment variables from .env file
load_dotenv()

# 2. Retrieve variables from environment
SERVER = os.getenv('DB_SERVER', '127.0.0.1')
DATABASE = os.getenv('DB_DATABASE', 'Demo_Database')
USERNAME = os.getenv('DB_USERNAME', 'sa')
PASSWORD = os.getenv('DB_PASSWORD')
DRIVER = os.getenv('DB_DRIVER', 'ODBC Driver 18 for SQL Server')

encoded_password = quote_plus(PASSWORD) if PASSWORD else ""

GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID')
KEY_PATH = os.getenv('GCP_KEY_PATH')
TARGET_DATASET = os.getenv('TARGET_DATASET', 'bronze')

def _init_clients():
    """Create and return the BigQuery and SQL Server clients.

    Validates that database credentials are present before proceeding.
    Raises ``ValueError`` if credentials are missing — deferred from
    import time so the module (and its validation helper) remain
    importable in offline/CI environments without a ``.env`` file.
    """
    if not USERNAME or not PASSWORD:
        raise ValueError("Missing database credentials in .env file!")

    credentials = service_account.Credentials.from_service_account_file(KEY_PATH)

    bq_client = bigquery.Client(
        project=GCP_PROJECT_ID,
        credentials=credentials
    )

    sql_conn_str = (
        f"mssql+pyodbc://{USERNAME}:{encoded_password}@{SERVER}/{DATABASE}?"
        f"driver={DRIVER}&encrypt=TLS&TrustServerCertificate=no"
    )
    db_engine = create_engine(sql_conn_str, pool_pre_ping=True)

    return credentials, bq_client, db_engine


# 4. Tables to Ingest
TABLES_TO_INGEST = [
    'crm_cust_info',
    'crm_prd_info',
    'crm_sales_details',
    'erp_cust_az12',
    'erp_loc_a101',
    'erp_px_cat_g1v2'
]

# Strict allowlist for table names. Prevents SQL injection via identifier
# interpolation: only ASCII letters, digits, and underscores are permitted,
# and the first character must be a letter or underscore.
TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_table_name(table_name: str) -> str:
    """Validate *table_name* against the strict allowlist.

    Raises ``ValueError`` if the name contains characters that could be used
    for SQL injection (semicolons, quotes, whitespace, dots, etc.).
    """
    if not isinstance(table_name, str) or not TABLE_NAME_RE.fullmatch(table_name):
        raise ValueError(
            f"Invalid table name: {table_name!r}. "
            "Only letters, digits, and underscores are allowed, "
            "starting with a letter or underscore."
        )
    return table_name


def _build_query(table_name: str) -> str:
    """Return a parameterized SELECT for *table_name*.

    The table name is validated against the allowlist and then embedded as a
    properly quoted SQL Server identifier (using square brackets), which is
    safe because the allowlist guarantees the name contains no ``]``
    characters.  Values are never interpolated into the query string.
    """
    safe_name = _validate_table_name(table_name)
    # SQL Server identifier quoting: [table_name].  The allowlist guarantees
    # the name contains only [A-Za-z0-9_], so no bracket can appear inside.
    return f"SELECT * FROM bronze.[{safe_name}]"


def validate_tls_connection(db_engine):
    """Verify the database connection enforces TLS with certificate validation.

    Fails fast and loudly if the connection cannot be established under the
    strict encrypted=TLS / TrustServerCertificate=no policy.
    """
    try:
        with db_engine.connect() as conn:
            # Verify encryption is active on the physical link
            result = conn.exec_driver_sql(
                "SELECT SESSIONPROPERTY('Encrypted') AS IsEncrypted"
            ).fetchone()
            if not result or not result[0]:
                raise RuntimeError(
                    "SQL Server connection is NOT encrypted. "
                    "TLS enforcement failed."
                )
            print("✓ Database connection validated with TLS encryption.")
    except sqla_exc.OperationalError as exc:
        raise RuntimeError(
            f"Failed to establish a secure TLS-encrypted database connection: {exc}"
        ) from exc
    except Exception as exc:
        if "certificate" in str(exc).lower() or "ssl" in str(exc).lower():
            raise RuntimeError(
                f"TLS certificate validation failed: {exc}"
            ) from exc
        raise


def extract_and_load():
    execution_id = str(uuid.uuid4())  # Generate a unique execution ID for this run

    # Initialize clients (validates credentials and establishes connections)
    credentials, bq_client, db_engine = _init_clients()

    # Enforce secure TLS connections with certificate validation before ingestion
    validate_tls_connection(db_engine)

    for table_name in TABLES_TO_INGEST:
        print(f"\n--- Processing table: {table_name} ---")
        start_time = time.time()
        destination_table = f"{GCP_PROJECT_ID}.{TARGET_DATASET}.{table_name}"

        try:
            query = _build_query(table_name)
            print("Reading data from SQL Server...")
            with db_engine.connect() as conn:
                df = pd.read_sql(query, con=conn)
            print(f"Extracted {len(df)} rows.")

            job_config = bigquery.LoadJobConfig(
                write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
                autodetect=True
            )

            print(f"Loading into BigQuery: '{destination_table}'...")
            load_job = bq_client.load_table_from_dataframe(
                df, destination_table, job_config=job_config
            )

            load_job.result()
            duration = time.time() - start_time
            print(f"Successfully loaded {table_name} into BigQuery!")

            # Log success to BigQuery audit
            log_execution_to_bigquery(
                execution_id=execution_id,
                resource_type="sql_to_bigquery",
                node_name=table_name,
                target_table=destination_table,
                status="pass",
                duration_sec=duration,
                rows_affected=len(df)
            )

        except Exception as exc:
            duration = time.time() - start_time
            print(f"❌ Failed to process {table_name}: {exc}")

            # Log failure to BigQuery audit
            log_execution_to_bigquery(
                execution_id=execution_id,
                resource_type="sql_to_bigquery",
                node_name=table_name,
                target_table=destination_table,
                status="fail",
                duration_sec=duration,
                rows_affected=0,
                error_msg=str(exc)
            )

if __name__ == '__main__':
    extract_and_load()
