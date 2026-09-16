#!/usr/bin/env python3
"""
Load test coverage data to BigQuery.
"""

import os
import json
from pathlib import Path
from google.cloud import bigquery
from dotenv import load_dotenv


def get_bigquery_client():
    load_dotenv()
    key_file_path = os.environ.get("GCP_KEY_PATH")
    project_id = os.environ.get("GCP_PROJECT_ID", "quantum-echo-data-eng-prod")

    if key_file_path and os.path.exists(key_file_path):
        return bigquery.Client.from_service_account_json(key_file_path, project=project_id)
    return bigquery.Client(project=project_id)


def create_coverage_table(client: bigquery.Client):
    """Create the test_coverage table if it doesn't exist."""
    table_id = "quantum-echo-data-eng-prod.audit_metadata.dbt_test_coverage"

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
        type_=bigquery.TimePartitioningType.DAY,
        field="calculated_at"
    )
    table.clustering_fields = ["model_name", "schema"]

    try:
        table = client.create_table(table, exists_ok=True)
        print(f"Created/verified table {table_id}")
    except Exception as e:
        print(f"Error creating table: {e}")
        raise


def load_coverage_data(client: bigquery.Client):
    """Load coverage data from JSON to BigQuery."""
    json_path = Path(__file__).parent.parent / 'target' / 'test_coverage.json'

    if not json_path.exists():
        print(f"Coverage JSON not found at {json_path}")
        print("Run calculate_coverage.py first")
        return

    with open(json_path, 'r') as f:
        rows = json.load(f)

    if not rows:
        print("No coverage data to load")
        return

    table_id = "quantum-echo-data-eng-prod.audit_metadata.dbt_test_coverage"

    # Delete existing data for today's partition (re-run safe)
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date().isoformat()
    delete_query = f"""
        DELETE FROM `{table_id}`
        WHERE DATE(calculated_at) = '{today}'
    """
    client.query(delete_query).result()
    print(f"Cleared existing data for {today}")

    # Load new data
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )

    # Convert to newline-delimited JSON
    import io
    json_lines = '\n'.join(json.dumps(row) for row in rows)
    json_file = io.BytesIO(json_lines.encode('utf-8'))

    job = client.load_table_from_file(json_file, table_id, job_config=job_config)
    job.result()

    print(f"Loaded {len(rows)} rows to {table_id}")


def main():
    print("Connecting to BigQuery...")
    client = get_bigquery_client()

    print("Creating coverage table...")
    create_coverage_table(client)

    print("Loading coverage data...")
    load_coverage_data(client)

    print("Done!")


if __name__ == '__main__':
    main()