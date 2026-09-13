from typing import Any, cast
import json
import os
import uuid
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account

# Locate and load .env from root or parent paths automatically
load_dotenv(find_dotenv())

# Paths and BigQuery Configuration
DBT_RUN_RESULTS_PATH = "analytics_layer/target/run_results.json" 
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
KEY_PATH = os.getenv("GCP_KEY_PATH")

DATASET_ID = "audit_metadata"
TABLE_ID = "dbt_execution_logs"

def get_bigquery_client() -> bigquery.Client:
    """Helper to initialize authenticated BigQuery client."""
    if not PROJECT_ID:
        raise ValueError("❌ GCP_PROJECT_ID is missing from environment/env variables.")

    if KEY_PATH and os.path.exists(KEY_PATH):
        # Create explicit service account credentials object
        credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
        return bigquery.Client(credentials=credentials, project=PROJECT_ID)
    
    # Fallback to Google Application Default Credentials
    print("⚠️ KEY_PATH not found or not provided. Falling back to default environment credentials.")
    return bigquery.Client(project=PROJECT_ID)

def parse_and_upload_run_results():
    if not os.path.exists(DBT_RUN_RESULTS_PATH):
        print(f"❌ Error: {DBT_RUN_RESULTS_PATH} not found. Run 'dbt test' or 'dbt run' first.")
        return

    with open(DBT_RUN_RESULTS_PATH, "r") as f:
        data: dict[str, Any] = cast(dict[str, Any], json.load(f))

    # Initialize client ONCE using helper
    client = get_bigquery_client()

    metadata = data.get("metadata", {})
    invocation_id = metadata.get("invocation_id", str(uuid.uuid4()))
    generated_at_str = metadata.get("generated_at")
    
    # Format ISO timestamp
    run_timestamp = generated_at_str if generated_at_str else datetime.utcnow().isoformat()

    rows_to_insert = []
    
    for item in data.get("results", []):
        unique_id = item.get("unique_id", "")
        unique_id_parts = unique_id.split(".")
        resource_type = unique_id_parts[0] if len(unique_id_parts) > 0 else "unknown"
        node_name = unique_id_parts[-2] if len(unique_id_parts) > 1 else unique_id

        target_table = unique_id_parts[2] if len(unique_id_parts) > 2 else None
        column_name = None
        if resource_type == "test" and "_" in node_name:
            parts = node_name.split("_")
            if len(parts) >= 3:
                column_name = parts[-1]

        row = {
            "execution_id": invocation_id,
            "run_timestamp": run_timestamp,
            "resource_type": resource_type,
            "node_name": node_name,
            "target_table": target_table,
            "column_name": column_name,
            "status": item.get("status", "unknown"),
            "execution_time_seconds": round(float(item.get("execution_time", 0.0)), 2),
            "rows_affected": item.get("failures", 0) if item.get("failures") is not None else 0,
            "error_message": item.get("message")
        }
        rows_to_insert.append(row)

    if not rows_to_insert:
        print("⚠️ No execution results found in file.")
        return

    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

    # Stream rows into BigQuery using authenticated client
    errors = client.insert_rows_json(table_ref, rows_to_insert)
    
    if not errors:
        print(f"✅ Successfully ingested {len(rows_to_insert)} records into {table_ref}!")
    else:
        print(f"❌ Encountered errors while inserting rows: {errors}")

if __name__ == "__main__":
    parse_and_upload_run_results()