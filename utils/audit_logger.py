import os
from datetime import UTC, datetime

from dotenv import find_dotenv, load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account

from utils.helpers import (
    resolve_bq_table,
    validate_bq_write_target,
)

# Ensure environment variables are available
load_dotenv(find_dotenv())


def log_execution_to_bigquery(
    execution_id: str,
    resource_type: str,  # e.g., 'csv_ingestion', 'sql_to_bigquery', 'test', 'model'
    node_name: str,  # e.g., 'cust_info.csv' or 'crm_cust_info'
    target_table: str,  # e.g., 'bronze.crm_cust_info'
    status: str,  # 'pass' or 'fail'
    duration_sec: float,
    rows_affected: int,
    error_msg: str | None = None,
):
    """Streams pipeline execution logs into BigQuery audit_metadata.dbt_execution_logs."""
    project_id = os.getenv("GCP_PROJECT_ID")

    if not project_id:
        print("⚠️ Skipped audit logging: GCP_PROJECT_ID is not set.")
        return

    try:
        # Initialize BigQuery client
        key_path = os.getenv("GCP_KEY_PATH")
        if key_path and os.path.exists(key_path):
            credentials = service_account.Credentials.from_service_account_file(
                key_path
            )
            client = bigquery.Client(project=project_id, credentials=credentials)
        else:
            client = bigquery.Client(project=project_id)

        table_ref = resolve_bq_table("dbt_execution_logs")
        validate_bq_write_target(table_ref)

        row = [
            {
                "execution_id": execution_id,
                "run_timestamp": datetime.now(UTC).isoformat(),
                "resource_type": resource_type,
                "node_name": node_name,
                "target_table": target_table,
                "column_name": None,
                "status": status,
                "execution_time_seconds": round(duration_sec, 2),
                "rows_affected": rows_affected,
                "error_message": error_msg,
            }
        ]

        errors = client.insert_rows_json(table_ref, row)
        if errors:
            print(f"⚠️ Metadata log insertion errors: {errors}")

    except Exception as e:
        print(f"⚠️ Failed to stream audit metadata to BigQuery: {e}")
