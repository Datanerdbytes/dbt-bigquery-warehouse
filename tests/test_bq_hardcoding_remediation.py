import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics_layer.scripts.load_coverage_to_bq import (
    load_coverage_data,
)
from utils.audit_logger import log_execution_to_bigquery
from utils.helpers import (
    get_bq_dataset_name,
    get_bq_project_id,
    is_test_environment,
    resolve_bq_table,
    validate_bq_write_target,
)


def test_get_bq_project_id_returns_mock_project_in_test_env(monkeypatch):
    monkeypatch.setenv("NODE_ENV", "test")
    monkeypatch.delenv("BQ_PROJECT_ID", raising=False)
    assert get_bq_project_id() == "local_bq_project"


def test_get_bq_dataset_name_returns_mock_dataset_in_test_env(monkeypatch):
    monkeypatch.setenv("NODE_ENV", "test")
    monkeypatch.delenv("BQ_DATASET_NAME", raising=False)
    assert get_bq_dataset_name() == "sandbox_audit"


def test_is_test_environment_true(monkeypatch):
    monkeypatch.setenv("NODE_ENV", "test")
    assert is_test_environment() is True


def test_is_test_environment_false(monkeypatch):
    monkeypatch.delenv("NODE_ENV", raising=False)
    assert is_test_environment() is False


def test_resolve_bq_table_uses_env_vars(monkeypatch):
    monkeypatch.setenv("BQ_PROJECT_ID", "my-project")
    monkeypatch.setenv("BQ_DATASET_NAME", "my_dataset")
    monkeypatch.delenv("NODE_ENV", raising=False)
    assert resolve_bq_table("my_table") == "my-project.my_dataset.my_table"


def test_resolve_bq_table_ignores_explicit_overrides_in_test_env(monkeypatch):
    monkeypatch.setenv("NODE_ENV", "test")
    monkeypatch.setenv("BQ_PROJECT_ID", "quantum-echo-data-eng-prod")
    monkeypatch.setenv("BQ_DATASET_NAME", "audit_metadata")
    assert (
        resolve_bq_table("dbt_test_coverage")
        == "local_bq_project.sandbox_audit.dbt_test_coverage"
    )


def test_validate_bq_write_target_allows_matching_prefix():
    validate_bq_write_target("local_bq_project.sandbox_audit.dbt_test_coverage")


def test_validate_bq_write_target_blocks_mismatch():
    with pytest.raises(RuntimeError) as exc_info:
        validate_bq_write_target(
            "quantum-echo-data-eng-prod.audit_metadata.dbt_test_coverage"
        )
    assert "Refusing BigQuery write" in str(exc_info.value)


def test_load_coverage_does_not_call_production_in_test_env(monkeypatch, tmp_path):
    monkeypatch.setenv("NODE_ENV", "test")
    monkeypatch.setenv("GCP_KEY_PATH", "")

    coverage_json = tmp_path / "test_coverage.json"
    coverage_json.write_text(json.dumps([{"model_name": "test_model"}]))

    target_dir = ROOT / "analytics_layer" / "target"
    target_dir.mkdir(exist_ok=True)
    coverage_json_target = target_dir / "test_coverage.json"
    coverage_json_target.write_text(json.dumps([{"model_name": "test_model"}]))

    mock_client = MagicMock()
    mock_client.load_table_from_file.return_value.result.return_value = None
    mock_client.query.return_value.result.return_value = None

    with patch(
        "analytics_layer.scripts.load_coverage_to_bq.get_bigquery_client",
        return_value=mock_client,
    ):
        load_coverage_data(mock_client)

    called_table_ids = [
        call.args[1] for call in mock_client.load_table_from_file.call_args_list
    ]
    assert all("quantum-echo-data-eng-prod" not in tid for tid in called_table_ids)
    assert all("audit_metadata" not in tid for tid in called_table_ids)


def test_audit_logger_uses_mock_dataset_in_test_env(monkeypatch):
    monkeypatch.setenv("NODE_ENV", "test")
    monkeypatch.setenv("GCP_PROJECT_ID", "local_bq_project")
    monkeypatch.setenv("GCP_KEY_PATH", "")

    mock_client = MagicMock()
    mock_client.insert_rows_json.return_value = []

    with patch("utils.audit_logger.bigquery.Client", return_value=mock_client):
        log_execution_to_bigquery(
            execution_id="exec-1",
            resource_type="test",
            node_name="test_node",
            target_table="test_table",
            status="pass",
            duration_sec=1.0,
            rows_affected=10,
        )

    table_ref = mock_client.insert_rows_json.call_args[0][0]
    assert "local_bq_project.sandbox_audit.dbt_execution_logs" == table_ref
