"""BigQuery audit metadata logger.

Streams pipeline execution logs into ``audit_metadata.dbt_execution_logs``.
Uses structured logging with redaction to avoid leaking sensitive metadata
in container logs or CI output.
"""

import os
import json
import logging
import sys
from collections.abc import Mapping
from datetime import UTC, datetime

from dotenv import find_dotenv, load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account

from utils.helpers import (
    resolve_bq_table,
    validate_bq_write_target,
)
from utils.logging_config import get_logger, sanitize_exception

logger = logging.getLogger(__name__)


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
    load_dotenv(find_dotenv())
    project_id = os.getenv("GCP_PROJECT_ID")

    if not project_id:
        logger.warning("Skipped audit logging: GCP_PROJECT_ID is not set.")
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
            logger.error(
                "Metadata log insertion errors: %s", sanitize_exception(str(errors))
            )

    except Exception as e:
        logger.error(
            "Failed to stream audit metadata to BigQuery: %s", sanitize_exception(e)
        )


class AuditLogger:
    """Write redacted JSON events without opening cloud clients or files.

    The legacy BigQuery telemetry function remains available to existing callers.
    Pipeline lifecycle events use this local JSON-lines stream exclusively.
    """

    def __init__(self, stream=None):
        self.stream = stream if stream is not None else sys.stderr

    def _redact(self, value):
        if isinstance(value, Mapping):
            return {
                str(key): (
                    "[REDACTED]"
                    if any(
                        part in str(key).lower()
                        for part in (
                            "password",
                            "secret",
                            "token",
                            "credential",
                            "connection_string",
                            "api_key",
                        )
                    )
                    else self._redact(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self._redact(item) for item in value]
        if isinstance(value, str):
            return sanitize_exception(value)
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return sanitize_exception(value)

    def _log(self, script, event, details):
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "script": self._redact(script),
            "event": event,
            "details": self._redact(details),
        }
        self.stream.write(json.dumps(record, allow_nan=False) + "\n")
        self.stream.flush()

    def log_start(self, script, params):
        self._log(script, "start", params)

    def log_success(self, script, stats):
        self._log(script, "success", stats)

    def log_failure(self, script, error, params):
        self._log(script, "failure", {"error": str(error), "params": params})
