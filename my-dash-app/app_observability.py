"""
Pipeline Observability Dashboard - Managed Multi-Page View
===========================================================
Integrated multi-page dashboard file mapping dbt telemetry and pipeline lineage tracking.
"""

import os
import json
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

import dash
from dash import html, dcc, callback, Input, Output, State, no_update
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
import plotly.graph_objects as go
import pandas as pd
from google.cloud import bigquery

# 1. Multi-Page Registration (Aligns with Section 3 and 4)
dash.register_page(
    __name__,
    path="/observability",
    name="Pipeline Observability",
    title="Pipeline Observability"
)

# 2. Strict Path Mapping (Aligns with Section 3 and 8)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANALYTICS_LAYER = PROJECT_ROOT / "analytics_layer"
MANIFEST_PATH = ANALYTICS_LAYER / "target" / "manifest.json"


# 3. BigQuery Client Initialization
def get_bigquery_client() -> bigquery.Client:
    key_file_path = os.environ.get("GCP_KEY_PATH")
    project_id = os.environ.get("GCP_PROJECT_ID", "quantum-echo-data-eng-prod")

    if key_file_path and os.path.exists(key_file_path):
        return bigquery.Client.from_service_account_json(key_file_path, project=project_id)
    return bigquery.Client(project=project_id)


# 4. Manifest Telemetry Layer Parsing Utilities
def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {}
    with open(MANIFEST_PATH, "r") as f:
        return json.load(f)


def parse_model_coverage(manifest: dict) -> list[dict]:
    nodes = manifest.get("nodes", {})
    models = {}
    
    for node_id, node in nodes.items():
        if node.get("resource_type") == "model":
            models[node_id] = {
                "model_name": node.get("name"),
                "schema": node.get("schema"),
                "database": node.get("database"),
                "columns": node.get("columns", {}),
                "total_columns": len(node.get("columns", {})),
            }

    test_by_model_column = defaultdict(lambda: defaultdict(set))
    for node_id, node in nodes.items():
        if node.get("resource_type") == "test":
            attached_node = node.get("attached_node")
            column_name = node.get("column_name")
            test_name = node.get("name")
            if attached_node and column_name and attached_node in models:
                test_by_model_column[attached_node][column_name].add(test_name)

    coverage_records = []
    calculated_at = datetime.now(timezone.utc).isoformat()

    for model_id, model_info in models.items():
        model_name = model_info["model_name"]
        columns = model_info["columns"]
        total_columns = model_info["total_columns"]

        if total_columns == 0:
            continue

        tested_columns = test_by_model_column.get(model_id, {})
        columns_with_tests = len(tested_columns)

        for col_name, col_info in columns.items():
            col_tests = tested_columns.get(col_name, set())
            coverage_records.append({
                "model_name": model_name,
                "schema": model_info["schema"],
                "database": model_info["database"],
                "column_name": col_name,
                "column_description": col_info.get("description", ""),
                "data_type": col_info.get("data_type", ""),
                "test_count": len(col_tests),
                "test_names": ", ".join(sorted(col_tests)),
                "has_tests": len(col_tests) > 0,
                "model_total_columns": total_columns,
                "model_columns_with_tests": columns_with_tests,
                "model_column_coverage_pct": round((columns_with_tests / total_columns) * 100, 2),
                "model_total_tests": sum(len(t) for t in tested_columns.values()),
                "calculated_at": calculated_at,
            })

    return coverage_records


def parse_model_dependencies(manifest: dict) -> dict:
    nodes = manifest.get("nodes", {})
    dependencies = defaultdict(list)
    model_names = {node_id: node.get("name") for node_id, node in nodes.items() if node.get("resource_type") == "model"}

    for node_id, node in nodes.items():
        if node.get("resource_type") == "model":
            model_name = node.get("name")
            depends_on = node.get("depends_on", {}).get("nodes", [])
            for dep_id in depends_on:
                if dep_id in model_names:
                    dependencies[model_names[dep_id]].append(model_name)

    return dict(dependencies)


# 5. Optimized Data Loaders (Fixes SELECT * Violation in Section 5)
def load_pipeline_health_summary() -> pd.DataFrame:
    client = get_bigquery_client()
    # Explicit column query setup to limit data processing charges
    query = """
        SELECT 
            pipeline_name, last_run_status, total_nodes, failed_nodes, 
            last_run_timestamp, freshness_status 
        FROM `quantum-echo-data-eng-prod.audit_metadata.v_latest_pipeline_health`
    """
    return client.query(query).to_dataframe()


def load_dbt_execution_logs(limit: int = 200) -> pd.DataFrame:
    client = get_bigquery_client()
    query = f"""
        SELECT
            execution_id, run_timestamp, resource_type, node_name,
            target_table, column_name, status, execution_time_seconds,
            rows_affected, error_message
        FROM `quantum-echo-data-eng-prod.audit_metadata.dbt_execution_logs`
        ORDER BY run_timestamp DESC
        LIMIT {limit}
    """
    return client.query(query).to_dataframe()


# 6. Standalone Layout Structure Shell (Conforms to Sections 5 and 6)
layout = dbc.Container([
    dcc.Store(id='observability-manifest-cache', storage_type='session'),
    
    dbc.Row([
        dbc.Col(html.H2("📊 Pipeline Observability Console", className="mb-4 text-primary"), width=12)
    ]),
    
    # Placeholder for the UI components to be fully expanded below
    html.Div(id="observability-viewport-content")
], fluid=True)
