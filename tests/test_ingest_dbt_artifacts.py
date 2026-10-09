"""Offline dbt telemetry regressions; clients and credentials are always mocked."""

import importlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from Scripts import ingest_dbt_artifacts as ingest


class DbtArtifactTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ, {"TARGET_PROJECT": "offline-project"}, clear=True
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_import_has_no_io(self):
        with (
            patch("dotenv.load_dotenv", side_effect=AssertionError("dotenv I/O")),
            patch("dotenv.find_dotenv", side_effect=AssertionError("dotenv search")),
            patch("google.cloud.bigquery.Client", side_effect=AssertionError("client")),
            patch(
                "google.oauth2.service_account.Credentials.from_service_account_file",
                side_effect=AssertionError("credentials"),
            ),
            patch("builtins.open", side_effect=AssertionError("file I/O")),
        ):
            importlib.reload(ingest)

    def test_transform_schema_and_names(self):
        data = {
            "metadata": {
                "invocation_id": "invocation",
                "generated_at": "2026-10-09T00:00:00Z",
            },
            "results": [
                {
                    "unique_id": "model.project.orders",
                    "status": "success",
                    "execution_time": 1.239,
                    "failures": None,
                },
                {
                    "unique_id": "test.project.not_null_orders_id.hash",
                    "status": "fail",
                    "failures": 2,
                    "message": "failed",
                },
            ],
        }
        rows = ingest.transform_run_results(data)
        self.assertEqual(
            set(rows[0]),
            {
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
            },
        )
        self.assertEqual(rows[0]["node_name"], "orders")
        self.assertEqual(rows[0]["execution_time_seconds"], 1.24)
        self.assertEqual(rows[0]["rows_affected"], 0)
        self.assertEqual(rows[1]["column_name"], "id")
        self.assertEqual(rows[1]["status"], "fail")
        self.assertEqual(
            datetime.fromisoformat(rows[0]["run_timestamp"]).tzinfo, timezone.utc
        )

    def test_timestamp_fallback_is_aware(self):
        rows = ingest.transform_run_results(
            {"results": [{"unique_id": "model.p.orders"}]}
        )
        self.assertEqual(
            datetime.fromisoformat(rows[0]["run_timestamp"]).tzinfo, timezone.utc
        )

    def test_load_results_and_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run_results.json"
            path.write_text('{"results": []}', encoding="utf-8")
            self.assertEqual(ingest.load_run_results(path), {"results": []})
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                ingest.load_run_results(path)
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                ingest.load_run_results(path)

    def run_main(self, data=None, errors=None, exception=None):
        with (
            patch.object(ingest, "load_dotenv"),
            patch.object(ingest, "find_dotenv", return_value=""),
            patch.object(ingest, "AuditLogger") as audit,
            patch.object(
                ingest,
                "load_run_results",
                return_value=data or {"results": []},
                side_effect=exception,
            ) as load,
            patch.object(ingest, "get_bq_client") as client,
        ):
            client.return_value.insert_rows_json.return_value = errors or []
            result = ingest.main()
            return result, audit.return_value, client, load

    def test_main_upload_configuration_and_audit(self):
        os.environ.update(
            DBT_ARTIFACTS_PATH="fixture.json",
            TARGET_DATASET="bronze",
            DBT_TARGET_DATASET="audit_custom",
        )
        result, audit, client, load = self.run_main(
            {"results": [{"unique_id": "model.p.orders"}]}
        )
        self.assertEqual(result, 0)
        load.assert_called_once_with("fixture.json")
        client.assert_called_once_with("offline-project")
        self.assertEqual(
            client.return_value.insert_rows_json.call_args.args[0],
            "offline-project.audit_custom.dbt_execution_logs",
        )
        audit.log_start.assert_called_once()
        audit.log_success.assert_called_once_with(
            "ingest_dbt_artifacts", {"rows_inserted": 1}
        )
        audit.log_failure.assert_not_called()

    def test_default_and_explicit_datasets(self):
        for dataset in (None, "explicit_audit"):
            with self.subTest(dataset=dataset):
                if dataset:
                    os.environ["TARGET_DATASET"] = dataset
                result, _, client, _ = self.run_main(
                    {"results": [{"unique_id": "model.p.orders"}]}
                )
                self.assertEqual(result, 0)
                self.assertEqual(
                    client.return_value.insert_rows_json.call_args.args[0],
                    f"offline-project.{dataset or 'audit_metadata'}.dbt_execution_logs",
                )

    def test_empty_results_avoid_client(self):
        result, audit, client, _ = self.run_main()
        self.assertEqual(result, 0)
        client.assert_not_called()
        audit.log_success.assert_called_once_with(
            "ingest_dbt_artifacts", {"rows_inserted": 0}
        )

    def test_missing_file_and_insert_errors_fail(self):
        for exception, errors in (
            (FileNotFoundError("missing"), None),
            (None, [{"index": 0, "errors": [{"reason": "invalid"}]}]),
        ):
            with self.subTest(exception=exception):
                result, audit, _, _ = self.run_main(
                    {"results": [{"unique_id": "model.p.orders"}]}, errors, exception
                )
                self.assertEqual(result, 1)
                audit.log_failure.assert_called_once()
                audit.log_success.assert_not_called()

    def test_missing_project_fails_before_client(self):
        os.environ.clear()
        result, audit, client, _ = self.run_main()
        self.assertEqual(result, 1)
        client.assert_not_called()
        audit.log_failure.assert_called_once()

    def test_credentials_created_only_in_factory(self):
        os.environ["GCP_KEY_PATH"] = "offline-key.json"
        with (
            patch.object(
                ingest.service_account.Credentials, "from_service_account_file"
            ) as credentials,
            patch.object(ingest.bigquery, "Client") as client,
        ):
            ingest.get_bq_client()
            credentials.assert_called_once_with("offline-key.json")
            client.assert_called_once_with(
                credentials=credentials.return_value, project="offline-project"
            )


if __name__ == "__main__":
    unittest.main()
