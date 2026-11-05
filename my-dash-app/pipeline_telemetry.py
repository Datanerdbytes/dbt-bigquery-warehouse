"""Read the pipeline telemetry artifact that ships with the app.

The BigQuery warehouse that hosted the ``audit_metadata`` tables is gone. The
dbt build still produces the same facts locally, and
``Scripts/export_pipeline_telemetry.py`` folds them into a single JSON file
that is bundled with the application. This module is the read side of that
artifact: it returns the frames the dashboard callbacks expect and degrades to
empty frames when the artifact is missing or unreadable, so a page load never
fails because telemetry is unavailable.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_TELEMETRY_PATH = (
    Path(__file__).resolve().parent / "data" / "pipeline_telemetry.json"
)

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

_TELEMETRY_CACHE: dict[str, Any] = {}


def telemetry_path() -> Path:
    """Resolve the telemetry artifact path, honouring the deployment override."""
    override = os.environ.get("PIPELINE_TELEMETRY_PATH")
    if override:
        return Path(override).expanduser()
    return DEFAULT_TELEMETRY_PATH


def load_telemetry() -> dict[str, Any]:
    """Return the parsed telemetry artifact, or an empty mapping when absent."""
    path = telemetry_path()
    cached = _TELEMETRY_CACHE.get("path")
    if cached == path and "data" in _TELEMETRY_CACHE:
        return _TELEMETRY_CACHE["data"]

    data: dict[str, Any] = {}
    try:
        with open(path, encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, json.JSONDecodeError):
        data = {}

    _TELEMETRY_CACHE["path"] = path
    _TELEMETRY_CACHE["data"] = data
    return data


def _section(name: str) -> list[dict[str, Any]]:
    section = load_telemetry().get(name)
    return section if isinstance(section, list) else []


def _frame(rows: list[dict[str, Any]], columns: list[str]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows).reindex(columns=columns)


def summary_frame() -> pd.DataFrame:
    """Return the single-row pipeline health summary."""
    summary = load_telemetry().get("summary")
    if not isinstance(summary, dict) or not summary:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)
    row = {column: summary.get(column) for column in SUMMARY_COLUMNS}
    return pd.DataFrame([row], columns=SUMMARY_COLUMNS)


def execution_logs_frame(limit: int = 200) -> pd.DataFrame:
    """Return the recorded model and test executions, newest first."""
    frame = _frame(_section("execution_logs"), EXECUTION_LOG_COLUMNS)
    if frame.empty:
        return frame
    if limit is not None and limit > 0:
        frame = frame.head(limit)
    return frame


def model_coverage_frame() -> pd.DataFrame:
    """Return per-model test coverage, least covered first."""
    return _frame(_section("model_coverage"), MODEL_COVERAGE_COLUMNS)


def column_coverage_frame() -> pd.DataFrame:
    """Return per-column test coverage."""
    return _frame(_section("column_coverage"), COLUMN_COVERAGE_COLUMNS)


def source_freshness_frame() -> pd.DataFrame:
    """Return the newest load of every source table with its age."""
    frame = _frame(_section("source_freshness"), SOURCE_FRESHNESS_COLUMNS)
    if frame.empty:
        return frame

    loaded = pd.to_datetime(frame["last_loaded"], errors="coerce", utc=True)
    age = pd.Timestamp.now(tz="UTC") - loaded
    frame["hours_since_load"] = (age.dt.total_seconds() // 3600).astype("Int64")
    frame["minutes_since_load"] = (age.dt.total_seconds() // 60).astype("Int64")
    return frame.reindex(columns=SOURCE_FRESHNESS_COLUMNS)


def ingestion_logs_frame(
    days_back: int = 30, limit: int = 200, latest_only: bool = False
) -> pd.DataFrame:
    """Return the recorded source-to-bronze loads.

    ``latest_only`` keeps the newest load of every table regardless of age, so
    a stale table stays visible; otherwise the history is bounded to
    ``days_back`` and ``limit``.
    """
    frame = _frame(_section("ingestion_logs"), INGESTION_COLUMNS)
    if frame.empty:
        return frame

    frame["run_timestamp"] = pd.to_datetime(
        frame["run_timestamp"], errors="coerce", utc=True
    )
    frame = frame.sort_values("run_timestamp", ascending=False)

    if latest_only:
        frame = frame.drop_duplicates(
            subset=["resource_type", "table_name", "target_table"], keep="first"
        )
    else:
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days_back)
        frame = frame[frame["run_timestamp"] >= cutoff]
        if limit is not None and limit > 0:
            frame = frame.head(limit)

    return frame.reset_index(drop=True)
