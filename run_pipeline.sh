#!/usr/bin/env bash
set -euo pipefail

# Resolve paths relative to this repository, regardless of the caller's cwd.
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Parse dotenv with Python rather than sourcing configuration as shell code.
# Re-exec with the loaded environment before applying defaults or validation.
if [[ -f "${ROOT_DIR}/.env" && "${1:-}" != "--environment-loaded" ]]; then
    if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
        PYTHON_RUN=("${ROOT_DIR}/.venv/bin/python")
    else
        PYTHON_RUN=(uv run --directory "${ROOT_DIR}" python)
    fi
    exec "${PYTHON_RUN[@]}" -c '
import os, sys
from dotenv import load_dotenv
load_dotenv(sys.argv[1], override=False)
os.execvpe("bash", ["bash", sys.argv[2], "--environment-loaded", *sys.argv[3:]], os.environ)
' "${ROOT_DIR}/.env" "${ROOT_DIR}/run_pipeline.sh" "$@"
fi
if [[ "${1:-}" == "--environment-loaded" ]]; then
    shift
fi
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
