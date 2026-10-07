#!/usr/bin/env python3
"""
Load test coverage data to BigQuery.
"""

import json
import os
from datetime import UTC
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import bigquery

from utils.helpers import get_bq_project_id, resolve_bq_table, validate_bq_write_target
from utils.logging_config import get_logger, sanitize_exception

logger = get_logger(__name__)


def get_bigquery_client():
    load_dotenv()
    project_id = get_bq_project_id()
    key_file_path = os.environ.get("GCP_KEY_PATH")

    if key_file_path and os.path.exists(key_file_path):
        return bigquery.Client.from_service_account_json(
            key_file_path, project=project_id
        )
    return bigquery.Client(project=project_id)


def create_coverage_table(client: bigquery.Client):
    """Create the test_coverage table if it doesn't exist."""
    table_id = resolve_bq_table("dbt_test_coverage")

    schema = [
        bigquery.SchemaField("model_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("schema", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("database", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("column_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("column_description", "STRING"),
        bigquery.SchemaField("data_type", "STRING"),
        bigquery.SchemaField("test_count", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("test_names", "STRING"),
        bigquery.SchemaField("has_tests", "BOOLEAN", mode="REQUIRED"),
        bigquery.SchemaField("model_total_columns", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("model_columns_with_tests", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("model_column_coverage_pct", "FLOAT64", mode="REQUIRED"),
        bigquery.SchemaField("model_total_tests", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("calculated_at", "TIMESTAMP", mode="REQUIRED"),
    ]

    table = bigquery.Table(table_id, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY, field="calculated_at"
    )
    table.clustering_fields = ["model_name", "schema"]

    try:
        table = client.create_table(table, exists_ok=True)
        logger.info("Created/verified table %s", table_id)
    except Exception as e:
        logger.error("Error creating table: %s", sanitize_exception(e))
        raise


def load_coverage_data(client: bigquery.Client):
    """Load coverage data from JSON to BigQuery."""
    json_path = Path(__file__).parent.parent / "target" / "test_coverage.json"

    if not json_path.exists():
        logger.error("Coverage JSON not found at %s", json_path)
        logger.error("Run calculate_coverage.py first")
        return

    with open(json_path) as f:
        rows = json.load(f)

    if not rows:
        logger.warning("No coverage data to load")
        return

    table_id = resolve_bq_table("dbt_test_coverage")
    validate_bq_write_target(table_id)

    # Delete existing data for today's partition (re-run safe)
    from datetime import datetime

    today = datetime.now(UTC).date().isoformat()
    delete_query = f"""
        DELETE FROM `{table_id}`
        WHERE DATE(calculated_at) = '{today}'
    """
    client.query(delete_query).result()
    logger.info("Cleared existing data for %s", today)

    # Load new data
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )

    # Convert to newline-delimited JSON
    import io

    json_lines = "\n".join(json.dumps(row) for row in rows)
    json_file = io.BytesIO(json_lines.encode("utf-8"))

    job = client.load_table_from_file(json_file, table_id, job_config=job_config)
    job.result()

    logger.info("Loaded %d rows to %s", len(rows), table_id)


def main():
    logger.info("Connecting to BigQuery...")
    client = get_bigquery_client()

    logger.info("Creating coverage table...")
    create_coverage_table(client)

    logger.info("Loading coverage data...")
    load_coverage_data(client)

    logger.info("Done!")


if __name__ == "__main__":
    main()
