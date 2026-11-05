"""Fail when the shipped pipeline telemetry drifts from the dbt build.

The app reads `my-dash-app/data/pipeline_telemetry.json`, a committed artifact
produced by `Scripts/export_pipeline_telemetry.py`. If a model, a test or a
source changes and the artifact is not re-exported, the pipeline health views
would report a state the models no longer agree with. This compares the
committed artifact against a freshly exported one and exits non-zero on any
difference.

Run time fields (the dbt invocation timestamp, execution durations, the
generation timestamp) change on every build, so they are compared by shape
rather than by value.

Usage:
    python Scripts/verify_shipped_telemetry.py
    python Scripts/verify_shipped_telemetry.py \
        --built /tmp/pipeline_telemetry.json \
        --shipped my-dash-app/data/pipeline_telemetry.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_SHIPPED = REPO_ROOT / "my-dash-app" / "data" / "pipeline_telemetry.json"

# Summary fields that describe the pipeline state rather than the run clock.
STABLE_SUMMARY_FIELDS = [
    "passed_tests",
    "failed_tests",
    "warning_tests",
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


def _read_json(path: pathlib.Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _summary_differences(built: dict, shipped: dict) -> list[str]:
    differences: list[str] = []
    built_summary = built.get("summary", {})
    shipped_summary = shipped.get("summary", {})
    for field in STABLE_SUMMARY_FIELDS:
        built_value = built_summary.get(field)
        shipped_value = shipped_summary.get(field)
        if built_value != shipped_value:
            differences.append(
                f"summary.{field}: built={built_value!r} shipped={shipped_value!r}"
            )
    return differences


def _coverage_differences(built: dict, shipped: dict) -> list[str]:
    differences: list[str] = []
    for section in ("model_coverage", "column_coverage"):
        built_rows = sorted(
            built.get(section, []), key=lambda row: json.dumps(row, sort_keys=True)
        )
        shipped_rows = sorted(
            shipped.get(section, []), key=lambda row: json.dumps(row, sort_keys=True)
        )
        if built_rows == shipped_rows:
            continue
        built_keys = {json.dumps(row, sort_keys=True) for row in built_rows}
        shipped_keys = {json.dumps(row, sort_keys=True) for row in shipped_rows}
        for row in built_keys - shipped_keys:
            differences.append(f"{section} missing from the shipped artifact: {row}")
        for row in shipped_keys - built_keys:
            differences.append(f"{section} no longer produced by the build: {row}")
    return differences


def _execution_differences(built: dict, shipped: dict) -> list[str]:
    def signature(rows: list[dict[str, Any]]) -> set[tuple]:
        return {
            (
                row.get("resource_type"),
                row.get("node_name"),
                row.get("status"),
                row.get("target_table"),
                row.get("rows_affected"),
            )
            for row in rows
        }

    built_rows = signature(built.get("execution_logs", []))
    shipped_rows = signature(shipped.get("execution_logs", []))
    differences = [
        f"execution log missing from the shipped artifact: {row}"
        for row in sorted(built_rows - shipped_rows, key=str)
    ]
    differences += [
        f"execution log no longer produced by the build: {row}"
        for row in sorted(shipped_rows - built_rows, key=str)
    ]
    return differences


def _ingestion_differences(built: dict, shipped: dict) -> list[str]:
    differences: list[str] = []

    def by_table(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for row in rows:
            target = row.get("target_table")
            if not target:
                continue
            current = latest.get(target)
            if current is None or (row.get("run_timestamp") or "") > (
                current.get("run_timestamp") or ""
            ):
                latest[target] = row
        return latest

    built_tables = by_table(built.get("ingestion_logs", []))
    shipped_tables = by_table(shipped.get("ingestion_logs", []))

    for target, built_row in built_tables.items():
        shipped_row = shipped_tables.get(target)
        if shipped_row is None:
            differences.append(
                f"ingestion log missing from the shipped artifact: {target}"
            )
            continue
        for field in ("source_rows", "destination_rows", "status"):
            if built_row.get(field) != shipped_row.get(field):
                differences.append(
                    f"ingestion {target}.{field}: built={built_row.get(field)!r} "
                    f"shipped={shipped_row.get(field)!r}"
                )

    for target in shipped_tables:
        if target not in built_tables:
            differences.append(
                f"ingestion log no longer produced by the build: {target}"
            )
    return differences


def _freshness_differences(built: dict, shipped: dict) -> list[str]:
    built_tables = {
        row.get("target_table") for row in built.get("source_freshness", [])
    }
    shipped_tables = {
        row.get("target_table") for row in shipped.get("source_freshness", [])
    }
    differences = [
        f"source freshness missing from the shipped artifact: {target}"
        for target in sorted(built_tables - shipped_tables)
    ]
    differences += [
        f"source freshness no longer produced by the build: {target}"
        for target in sorted(shipped_tables - built_tables)
    ]
    return differences


def compare(built_path: pathlib.Path, shipped_path: pathlib.Path) -> list[str]:
    differences: list[str] = []

    for label, path in (("built", built_path), ("shipped", shipped_path)):
        if not path.exists():
            differences.append(f"{label} telemetry missing: {path}")
    if differences:
        return differences

    built = _read_json(built_path)
    shipped = _read_json(shipped_path)

    differences += _summary_differences(built, shipped)
    differences += _coverage_differences(built, shipped)
    differences += _execution_differences(built, shipped)
    differences += _ingestion_differences(built, shipped)
    differences += _freshness_differences(built, shipped)
    return differences


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--built", type=pathlib.Path, required=True)
    parser.add_argument("--shipped", type=pathlib.Path, default=DEFAULT_SHIPPED)
    args = parser.parse_args(argv)

    differences = compare(
        args.built.expanduser().resolve(), args.shipped.expanduser().resolve()
    )

    if differences:
        print("Shipped pipeline telemetry is out of date:")
        for difference in differences:
            print(f"  - {difference}")
        print("Re-run Scripts/export_pipeline_telemetry.py and commit the result.")
        return 1

    print("Shipped pipeline telemetry matches the dbt build.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
