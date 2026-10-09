#!/usr/bin/env bash
set -euo pipefail

# Resolve paths relative to this repository, regardless of the caller's cwd.
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${ROOT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
: "${SOURCE_FOLDER:?Set SOURCE_FOLDER to the directory containing source CSV files}"
: "${DB_CONNECTION_STRING:?Set DB_CONNECTION_STRING to a SQL Server mssql+pyodbc URL}"
: "${TARGET_PROJECT:=${GCP_PROJECT_ID:-}}"
: "${TARGET_PROJECT:?Set TARGET_PROJECT or GCP_PROJECT_ID for BigQuery}"
export TARGET_PROJECT
export TARGET_DATASET="${TARGET_DATASET:-bronze}"
export DBT_TARGET_DATASET="${DBT_TARGET_DATASET:-audit_metadata}"
DBT_PROJECT_DIR="${DBT_PROJECT_DIR:-${ROOT_DIR}/analytics_layer}"
if [[ "${DBT_PROJECT_DIR}" != /* ]]; then
    DBT_PROJECT_DIR="${ROOT_DIR}/${DBT_PROJECT_DIR}"
fi
if [[ "${SOURCE_FOLDER}" != /* ]]; then
    SOURCE_FOLDER="${ROOT_DIR}/${SOURCE_FOLDER}"
fi
export SOURCE_FOLDER
export DBT_ARTIFACTS_PATH="${DBT_ARTIFACTS_PATH:-${DBT_PROJECT_DIR}/target/run_results.json}"

run() {
    if [[ "${PIPELINE_DRY_RUN:-0}" == "1" ]]; then
        printf 'DRY RUN:'
        printf ' %q' "$@"
        printf '\n'
    else
        "$@"
    fi
}

cd -- "${ROOT_DIR}"
run uv run Scripts/ingest_bronze.py
run uv run Scripts/ingest_bigquery.py
cd -- "${DBT_PROJECT_DIR}"
run uv run dbt run
run uv run dbt test
cd -- "${ROOT_DIR}"
run uv run Scripts/ingest_dbt_artifacts.py
printf 'Pipeline stages completed.\n'
