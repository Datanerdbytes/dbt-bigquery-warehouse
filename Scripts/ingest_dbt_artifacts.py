"""Upload dbt run-result telemetry; importing this module performs no I/O."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account

from utils.audit_logger import AuditLogger

DBT_RUN_RESULTS_PATH = "analytics_layer/target/run_results.json"
DATASET_ID = "audit_metadata"
TABLE_ID = "dbt_execution_logs"


def get_bq_client(project_id: str | None = None) -> bigquery.Client:
    """Create a client at execution time, using explicit credentials or ADC."""
    project_id = (
        project_id or os.getenv("TARGET_PROJECT") or os.getenv("GCP_PROJECT_ID")
    )
    if not project_id:
        raise ValueError("TARGET_PROJECT or GCP_PROJECT_ID must be configured.")
    key_path = os.getenv("GCP_KEY_PATH")
    if key_path:
        credentials = service_account.Credentials.from_service_account_file(key_path)
        return bigquery.Client(credentials=credentials, project=project_id)
    return bigquery.Client(project=project_id)


def get_bigquery_client() -> bigquery.Client:
    """Compatibility wrapper for existing callers."""
    return get_bq_client()


def load_run_results(path: str | Path) -> dict[str, Any]:
    """Read a run-results artifact without creating clients or uploading data."""
    with open(path, encoding="utf-8") as artifact:
        data = json.load(artifact)
    if not isinstance(data, dict):
        raise ValueError("run_results.json must contain a JSON object.")
    return data


def transform_run_results(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten results into the existing dbt_execution_logs table schema."""
    metadata = data.get("metadata", {})
    generated_at = metadata.get("generated_at")
    if generated_at:
        timestamp = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
    else:
        timestamp = datetime.now(UTC)
    rows = []
    for item in data.get("results", []):
        unique_id = item.get("unique_id", "")
        parts = unique_id.split(".")
        resource_type = parts[0] if unique_id else "unknown"
        # Models/seeds/snapshots have three components; tests add a hash suffix.
        node_name = parts[2] if len(parts) > 2 else unique_id
        column_name = None
        if resource_type == "test" and "_" in node_name:
            node_parts = node_name.split("_")
            if len(node_parts) >= 3:
                column_name = node_parts[-1]
        rows.append(
            {
                "execution_id": metadata.get("invocation_id", "unknown"),
                "run_timestamp": timestamp.isoformat(),
                "resource_type": resource_type,
                "node_name": node_name,
                "target_table": parts[2] if len(parts) > 2 else None,
                "column_name": column_name,
                "status": item.get("status", "unknown"),
                "execution_time_seconds": round(
                    float(item.get("execution_time", 0.0)), 2
                ),
                "rows_affected": item.get("failures") or 0,
                "error_message": item.get("message"),
            }
        )
    return rows


def main() -> int:
    """Load runtime configuration, upload rows, and report a failing exit code."""
    load_dotenv(find_dotenv())
    audit = AuditLogger()
    script = "ingest_dbt_artifacts"
    project = os.getenv("TARGET_PROJECT") or os.getenv("GCP_PROJECT_ID")
    dataset = (
        os.getenv("DBT_TARGET_DATASET") or os.getenv("TARGET_DATASET") or DATASET_ID
    )
    path = os.getenv("DBT_ARTIFACTS_PATH") or DBT_RUN_RESULTS_PATH
    params = {
        "artifact_path": path,
        "target_project": project,
        "target_dataset": dataset,
    }
    audit.log_start(script, params)
    try:
        if not project:
            raise ValueError("TARGET_PROJECT or GCP_PROJECT_ID must be configured.")
        rows = transform_run_results(load_run_results(path))
        if rows:
            client = get_bq_client(project)
            errors = client.insert_rows_json(f"{project}.{dataset}.{TABLE_ID}", rows)
            if errors:
                raise RuntimeError(f"BigQuery rejected dbt telemetry rows: {errors}")
        audit.log_success(script, {"rows_inserted": len(rows)})
        return 0
    except Exception as error:
        audit.log_failure(script, error, params)
        return 1


def parse_and_upload_run_results() -> int:
    """Compatibility entry point for existing callers."""
    return main()


if __name__ == "__main__":
    raise SystemExit(main())
