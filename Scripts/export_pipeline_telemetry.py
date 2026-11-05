"""Compose the pipeline telemetry artifact the dashboard ships with.

The BigQuery warehouse that hosted the ``audit_metadata`` tables is gone, but
the facts those tables carried are still produced locally by the dbt build:

    analytics_layer/target/run_results.json   execution status, duration, failures
    analytics_layer/target/manifest.json       model columns and attached tests
    analytics_layer/build/bronze_manifest.json CSV -> DuckDB row parity per table

This script folds those three sources into one JSON file that the app reads at
runtime, so the pipeline health views keep working without a warehouse.

Usage:
    python Scripts/export_pipeline_telemetry.py
    python Scripts/export_pipeline_telemetry.py --out my-dash-app/data/pipeline_telemetry.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from datetime import UTC, datetime
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "analytics_layer" / "scripts"))

# pyrefly: ignore [missing-import]
from calculate_coverage import calculate_coverage  # noqa: E402

DEFAULT_TARGET = REPO_ROOT / "analytics_layer" / "target"
DEFAULT_BRONZE_MANIFEST = (
    REPO_ROOT / "analytics_layer" / "build" / "bronze_manifest.json"
)
DEFAULT_OUT = REPO_ROOT / "my-dash-app" / "data" / "pipeline_telemetry.json"

INGESTION_RESOURCE_TYPE = "csv_to_duckdb"
MAX_INGESTION_HISTORY = 500

SUMMARY_COLUMNS = [
    "last_dbt_run",
    "passed_tests",
    "failed_tests",
    "warning_tests",
    "avg_model_duration_sec",
    "total_models",
    "total_columns",
    "total_columns_with_tests",
    "overall_column_coverage_pct",
    "total_tests",
    "models_fully_covered",
    "models_well_covered",
    "models_poorly_covered",
    "overall_system_status",
]

EXECUTION_LOG_COLUMNS = [
    "execution_id",
    "run_timestamp",
    "resource_type",
    "node_name",
    "target_table",
    "column_name",
    "status",
    "execution_time_seconds",
    "rows_affected",
    "error_message",
]

MODEL_COVERAGE_COLUMNS = [
    "model_name",
    "schema",
    "total_columns",
    "columns_with_tests",
    "column_coverage_pct",
    "total_tests",
]

COLUMN_COVERAGE_COLUMNS = [
    "model_name",
    "schema",
    "column_name",
    "column_description",
    "data_type",
    "test_count",
    "test_names",
    "has_tests",
]

SOURCE_FRESHNESS_COLUMNS = [
    "source_table",
    "target_table",
    "last_loaded",
    "hours_since_load",
    "minutes_since_load",
]

INGESTION_COLUMNS = [
    "log_id",
    "run_timestamp",
    "resource_type",
    "table_name",
    "target_table",
    "source_rows",
    "destination_rows",
    "rows_inserted",
    "duration_seconds",
    "status",
    "error_message",
]


def _read_json(path: pathlib.Path) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _node_name(unique_id: str) -> str:
    parts = unique_id.split(".")
    return parts[2] if len(parts) > 2 else unique_id


def _relation_name(node: dict) -> str | None:
    schema = node.get("schema")
    name = node.get("alias") or node.get("name")
    if not schema or not name:
        return None
    return f"{schema}.{name}"


def _source_relation(node: dict, sources: dict) -> str | None:
    """Resolve the bronze table a source-level test reads.

    Source tests have no ``attached_node``; the source is referenced from the
    compiled macro argument instead.
    """
    model = (node.get("test_metadata") or {}).get("kwargs", {}).get("model", "")
    match = re.search(r"source\('([^']+)',\s*'([^']+)'\)", model)
    if not match:
        return None
    source_name, table_name = match.group(1), match.group(2)
    for source in sources.values():
        if (
            source.get("source_name") == source_name
            and source.get("name") == table_name
        ):
            identifier = source.get("identifier") or source.get("name")
            if source.get("schema") and identifier:
                return f"{source['schema']}.{identifier}"
    return None


def _target_table(node: dict, nodes: dict, sources: dict) -> str | None:
    """Resolve the relation a model or test acted on."""
    if node.get("resource_type") == "model":
        return _relation_name(node)

    attached = node.get("attached_node")
    if attached:
        if attached in nodes:
            return _relation_name(nodes[attached])
        source = sources.get(attached)
        if source:
            identifier = source.get("identifier") or source.get("name")
            if source.get("schema") and identifier:
                return f"{source['schema']}.{identifier}"
        return None

    return _source_relation(node, sources)


def build_execution_logs(run_results: dict, manifest: dict) -> list[dict[str, Any]]:
    """Flatten run_results.json into the dbt_execution_logs row shape."""
    metadata = run_results.get("metadata", {})
    execution_id = metadata.get("invocation_id", "unknown")
    generated_at = metadata.get("generated_at")
    nodes = manifest.get("nodes", {})
    sources = manifest.get("sources", {})

    rows: list[dict[str, Any]] = []
    for item in run_results.get("results", []):
        unique_id = item.get("unique_id", "")
        resource_type = unique_id.split(".")[0] if unique_id else "unknown"
        node = nodes.get(unique_id, {})
        node_name = _node_name(unique_id)

        column_name = node.get("column_name")
        if column_name is None and resource_type == "test" and "_" in node_name:
            column_name = node_name.split("_")[-1]

        rows.append(
            {
                "execution_id": execution_id,
                "run_timestamp": generated_at,
                "resource_type": resource_type,
                "node_name": node_name,
                "target_table": _target_table(node, nodes, sources),
                "column_name": column_name,
                "status": item.get("status", "unknown"),
                "execution_time_seconds": round(
                    float(item.get("execution_time") or 0.0), 2
                ),
                "rows_affected": item.get("failures") or 0,
                "error_message": item.get("message"),
            }
        )

    rows.sort(
        key=lambda row: (row["run_timestamp"] or "", row["node_name"]), reverse=True
    )
    return rows


def build_coverage(manifest: dict) -> tuple[list[dict], list[dict]]:
    """Return per-model and per-column coverage rows from the dbt manifest."""
    coverage = calculate_coverage(manifest)

    model_rows = [
        {
            "model_name": model["model_name"],
            "schema": model["schema"],
            "total_columns": model["total_columns"],
            "columns_with_tests": model["columns_with_tests"],
            "column_coverage_pct": model["column_coverage_pct"],
            "total_tests": model["total_tests"],
        }
        for model in coverage
    ]
    model_rows.sort(key=lambda row: (row["column_coverage_pct"], row["model_name"]))

    column_rows = [
        {
            "model_name": model["model_name"],
            "schema": model["schema"],
            "column_name": column["column_name"],
            "column_description": column["column_description"],
            "data_type": column["data_type"],
            "test_count": column["test_count"],
            "test_names": ",".join(column["test_names"]),
            "has_tests": column["has_tests"],
        }
        for model in coverage
        for column in model["column_details"]
    ]
    column_rows.sort(
        key=lambda row: (row["model_name"], row["has_tests"], row["column_name"])
    )
    return model_rows, column_rows


def build_summary(run_results: dict, model_coverage: list[dict]) -> dict[str, Any]:
    """Reduce the run and the coverage into the pipeline health KPI row."""
    metadata = run_results.get("metadata", {})
    results = run_results.get("results", [])
    tests = [item for item in results if item.get("unique_id", "").startswith("test.")]

    passed = sum(1 for item in tests if item.get("status") == "pass")
    failed = sum(1 for item in tests if item.get("status") in ("fail", "error"))
    warned = sum(1 for item in tests if item.get("status") == "warn")

    durations = [float(item.get("execution_time") or 0.0) for item in results]
    avg_duration = round(sum(durations) / len(durations), 4) if durations else 0.0

    total_columns = sum(row["total_columns"] for row in model_coverage)
    total_tested = sum(row["columns_with_tests"] for row in model_coverage)
    overall_pct = (
        round((total_tested / total_columns) * 100, 2) if total_columns else 0.0
    )

    if failed:
        status = "CRITICAL"
    elif warned:
        status = "WARNING"
    else:
        status = "HEALTHY"

    return {
        "last_dbt_run": metadata.get("invocation_started_at")
        or metadata.get("generated_at"),
        "passed_tests": passed,
        "failed_tests": failed,
        "warning_tests": warned,
        "avg_model_duration_sec": avg_duration,
        "total_models": len(model_coverage),
        "total_columns": total_columns,
        "total_columns_with_tests": total_tested,
        "overall_column_coverage_pct": overall_pct,
        "total_tests": sum(row["total_tests"] for row in model_coverage),
        "models_fully_covered": sum(
            1 for row in model_coverage if row["column_coverage_pct"] >= 100
        ),
        "models_well_covered": sum(
            1 for row in model_coverage if row["column_coverage_pct"] >= 80
        ),
        "models_poorly_covered": sum(
            1 for row in model_coverage if row["column_coverage_pct"] < 50
        ),
        "overall_system_status": status,
    }


def build_ingestion_logs(bronze_manifest: dict) -> list[dict[str, Any]]:
    """Turn the bronze load manifest into table_ingestion_logs rows."""
    loaded_at = bronze_manifest.get("loaded_at")
    rows: list[dict[str, Any]] = []
    for table in bronze_manifest.get("tables", []):
        destination_rows = int(table.get("destination_rows") or 0)
        rows.append(
            {
                "log_id": f"{loaded_at}-{table.get('target_table')}",
                "run_timestamp": loaded_at,
                "resource_type": INGESTION_RESOURCE_TYPE,
                "table_name": table.get("source_file"),
                "target_table": table.get("target_table"),
                "source_rows": int(table.get("source_rows") or 0),
                "destination_rows": destination_rows,
                "rows_inserted": destination_rows,
                "duration_seconds": table.get("duration_seconds"),
                "status": table.get("status", "unknown"),
                "error_message": table.get("error_message"),
            }
        )
    return rows


def merge_ingestion_history(
    existing: list[dict], incoming: list[dict]
) -> list[dict[str, Any]]:
    """Keep the newest load of every table, newest first."""
    merged: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for row in existing + incoming:
        key = (row.get("run_timestamp"), row.get("target_table"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
    merged.sort(key=lambda row: row.get("run_timestamp") or "", reverse=True)
    return merged[:MAX_INGESTION_HISTORY]


def build_source_freshness(ingestion_logs: list[dict]) -> list[dict[str, Any]]:
    """Return the most recent successful load of every target table."""
    latest: dict[str, dict[str, Any]] = {}
    for row in ingestion_logs:
        if row.get("status") not in ("pass", "success"):
            continue
        target = row.get("target_table")
        if not target or target in latest:
            continue
        latest[target] = {
            "source_table": row.get("table_name"),
            "target_table": target,
            "last_loaded": row.get("run_timestamp"),
        }
    return sorted(
        latest.values(),
        key=lambda row: row.get("last_loaded") or "",
        reverse=True,
    )


def export_telemetry(
    target_dir: pathlib.Path,
    bronze_manifest_path: pathlib.Path,
    out_path: pathlib.Path,
) -> dict[str, Any]:
    run_results = _read_json(target_dir / "run_results.json")
    manifest = _read_json(target_dir / "manifest.json")
    bronze_manifest = _read_json(bronze_manifest_path)

    model_coverage, column_coverage = build_coverage(manifest)
    execution_logs = build_execution_logs(run_results, manifest)
    summary = build_summary(run_results, model_coverage)

    existing_logs: list[dict] = []
    if out_path.exists():
        try:
            existing = _read_json(out_path)
            existing_logs = existing.get("ingestion_logs", [])
        except (json.JSONDecodeError, OSError):
            existing_logs = []

    ingestion_logs = merge_ingestion_history(
        existing_logs, build_ingestion_logs(bronze_manifest)
    )

    telemetry = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dbt": {
            "dbt_version": run_results.get("metadata", {}).get("dbt_version"),
            "invocation_id": run_results.get("metadata", {}).get("invocation_id"),
            "invocation_started_at": run_results.get("metadata", {}).get(
                "invocation_started_at"
            ),
            "generated_at": run_results.get("metadata", {}).get("generated_at"),
            "elapsed_time": run_results.get("elapsed_time"),
        },
        "summary": summary,
        "execution_logs": execution_logs,
        "model_coverage": model_coverage,
        "column_coverage": column_coverage,
        "source_freshness": build_source_freshness(ingestion_logs),
        "ingestion_logs": ingestion_logs,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(telemetry, indent=2) + "\n")
    return telemetry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=pathlib.Path, default=DEFAULT_TARGET)
    parser.add_argument(
        "--bronze-manifest", type=pathlib.Path, default=DEFAULT_BRONZE_MANIFEST
    )
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    target_dir = args.target.expanduser().resolve()
    bronze_manifest_path = args.bronze_manifest.expanduser().resolve()
    out_path = args.out.expanduser().resolve()

    telemetry = export_telemetry(target_dir, bronze_manifest_path, out_path)
    summary = telemetry["summary"]
    print(f"Wrote {out_path}")
    print(
        f"  models={summary['total_models']} "
        f"columns={summary['total_columns']} "
        f"coverage={summary['overall_column_coverage_pct']}% "
        f"passed={summary['passed_tests']} "
        f"failed={summary['failed_tests']} "
        f"warnings={summary['warning_tests']} "
        f"status={summary['overall_system_status']}"
    )
    print(
        f"  execution_logs={len(telemetry['execution_logs'])} "
        f"ingestion_logs={len(telemetry['ingestion_logs'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
