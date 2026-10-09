"""Offline regressions for SQL Server to BigQuery ingestion."""

import importlib
import os
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from Scripts import ingest_bigquery as ingestion


class BigQueryIngestionTests(unittest.TestCase):
    def test_import_does_not_load_environment_or_create_clients(self):
        with (
            patch("dotenv.load_dotenv", side_effect=AssertionError("dotenv I/O")),
            patch(
                "utils.logging_config.get_logger",
                side_effect=AssertionError("logging I/O"),
            ),
            patch(
                "google.cloud.bigquery.Client", side_effect=AssertionError("cloud I/O")
            ),
            patch(
                "google.oauth2.service_account.Credentials.from_service_account_file",
                side_effect=AssertionError("credential I/O"),
            ),
            patch(
                "sqlalchemy.create_engine", side_effect=AssertionError("database I/O")
            ),
        ):
            importlib.reload(ingestion)

    def test_client_uses_runtime_project_and_adc(self):
        with (
            patch.dict(os.environ, {"TARGET_PROJECT": "offline-project"}, clear=True),
            patch.object(ingestion.bigquery, "Client") as client,
        ):
            self.assertIs(ingestion.get_bq_client(), client.return_value)
            client.assert_called_once_with(project="offline-project")

    def test_client_uses_explicit_service_account(self):
        with (
            patch.dict(
                os.environ,
                {"GCP_PROJECT_ID": "offline-project", "GCP_KEY_PATH": "/offline/key"},
                clear=True,
            ),
            patch.object(
                ingestion.service_account.Credentials, "from_service_account_file"
            ) as credentials,
            patch.object(ingestion.bigquery, "Client") as client,
        ):
            ingestion.get_bq_client()
            credentials.assert_called_once_with("/offline/key")
            client.assert_called_once_with(
                project="offline-project", credentials=credentials.return_value
            )

    def test_engine_uses_odbc18_and_preserves_special_password(self):
        values = {
            "DB_SERVER": "localhost",
            "DB_DATABASE": "offline",
            "DB_USERNAME": "sa",
            "DB_PASSWORD": "p@ss:/?#",
        }
        with (
            patch.dict(os.environ, values, clear=True),
            patch.object(ingestion, "create_engine") as create,
        ):
            ingestion.get_source_engine()
        url = create.call_args.args[0]
        self.assertEqual(url.drivername, "mssql+pyodbc")
        self.assertEqual(url.password, values["DB_PASSWORD"])
        self.assertEqual(url.port, 1433)
        self.assertEqual(url.query["driver"], "ODBC Driver 18 for SQL Server")

    def test_engine_accepts_explicit_sql_server_url(self):
        value = "mssql+pyodbc://sa:placeholder@localhost/offline?driver=ODBC+Driver+18+for+SQL+Server"
        with (
            patch.dict(os.environ, {"DB_CONNECTION_STRING": value}, clear=True),
            patch.object(ingestion, "create_engine") as create,
        ):
            ingestion.get_source_engine()
        self.assertEqual(
            str(create.call_args.args[0]).split("?")[1],
            "driver=ODBC+Driver+18+for+SQL+Server",
        )

    def test_engine_rejects_incompatible_driver_before_creation(self):
        with (
            patch.dict(
                os.environ, {"DB_CONNECTION_STRING": "sqlite:///offline.db"}, clear=True
            ),
            patch.object(ingestion, "create_engine") as create,
        ):
            with self.assertRaises(ValueError):
                ingestion.get_source_engine()
            create.assert_not_called()

    def run_main(self, frames=None, failure=None, connection_failure=None):
        client, engine, audit = MagicMock(), MagicMock(), MagicMock()
        if failure:
            client.load_table_from_dataframe.side_effect = failure
        with (
            patch.dict(
                os.environ,
                {"TARGET_PROJECT": "offline-project", "TARGET_DATASET": "bronze"},
                clear=True,
            ),
            patch.object(ingestion, "load_dotenv"),
            patch.object(ingestion, "get_bq_client", return_value=client),
            patch.object(ingestion, "get_source_engine", return_value=engine),
            patch.object(ingestion, "AuditLogger", return_value=audit),
            patch.object(
                ingestion, "validate_connection", side_effect=connection_failure
            ),
            patch.object(ingestion, "TABLES", ["crm_cust_info", "erp_loc_a101"]),
            patch.object(
                ingestion.pd,
                "read_sql",
                side_effect=frames
                or [pd.DataFrame({"id": [1, 2]}), pd.DataFrame({"id": [3]})],
            ) as read,
        ):
            code = ingestion.main()
        return code, client, engine, audit, read

    def test_main_extracts_each_bronze_table_and_waits_for_upload(self):
        code, client, engine, audit, read = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(
            [call.args[0] for call in read.call_args_list],
            [
                "SELECT * FROM [bronze].[crm_cust_info]",
                "SELECT * FROM [bronze].[erp_loc_a101]",
            ],
        )
        self.assertEqual(
            [call.args[1] for call in client.load_table_from_dataframe.call_args_list],
            [
                "offline-project.bronze.crm_cust_info",
                "offline-project.bronze.erp_loc_a101",
            ],
        )
        self.assertEqual(
            client.load_table_from_dataframe.return_value.result.call_count, 2
        )
        config = client.load_table_from_dataframe.call_args.kwargs["job_config"]
        self.assertEqual(config.write_disposition, "WRITE_TRUNCATE")
        audit.log_start.assert_any_call(
            "ingest_bigquery", {"tables": ["crm_cust_info", "erp_loc_a101"]}
        )
        audit.log_success.assert_any_call(
            "ingest_bigquery", {"tables_loaded": 2, "rows_affected": 3}
        )
        audit.log_failure.assert_not_called()
        engine.dispose.assert_called_once_with()

    def test_failure_continues_remaining_tables_but_returns_nonzero(self):
        code, client, engine, audit, read = self.run_main(
            failure=[RuntimeError("offline failure"), MagicMock()]
        )
        self.assertEqual(code, 1)
        self.assertEqual(read.call_count, 2)
        self.assertEqual(client.load_table_from_dataframe.call_count, 2)
        self.assertEqual(audit.log_failure.call_count, 2)
        self.assertEqual(audit.log_failure.call_args.args[0], "ingest_bigquery")
        engine.dispose.assert_called_once_with()

    def test_validation_failure_disposes_engine_and_logs_failure(self):
        code, client, engine, audit, read = self.run_main(
            connection_failure=RuntimeError("offline connection failure")
        )
        self.assertEqual(code, 1)
        client.load_table_from_dataframe.assert_not_called()
        read.assert_not_called()
        audit.log_failure.assert_called_once()
        engine.dispose.assert_called_once_with()

    def test_factory_failure_logs_run_failure(self):
        with (
            patch.object(ingestion, "load_dotenv"),
            patch.object(ingestion, "AuditLogger") as audit,
            patch.object(
                ingestion, "get_bq_client", side_effect=ValueError("missing config")
            ),
            patch.object(ingestion, "get_source_engine") as engine,
        ):
            self.assertEqual(ingestion.main(), 1)
            audit.return_value.log_start.assert_called_once()
            audit.return_value.log_failure.assert_called_once()
            engine.assert_not_called()

    def test_async_upload_failure_is_not_reported_as_success(self):
        failed_job = MagicMock()
        failed_job.result.side_effect = RuntimeError("offline upload failed")
        code, _, engine, audit, _ = self.run_main(failure=[failed_job, MagicMock()])
        self.assertEqual(code, 1)
        self.assertEqual(audit.log_failure.call_count, 2)
        engine.dispose.assert_called_once_with()

    def test_direct_extract_disposes_its_owned_engine_on_validation_failure(self):
        engine = MagicMock()
        with (
            patch.dict(os.environ, {"TARGET_PROJECT": "offline-project"}, clear=True),
            patch.object(ingestion, "get_bq_client", return_value=MagicMock()),
            patch.object(ingestion, "get_source_engine", return_value=engine),
            patch.object(ingestion, "AuditLogger"),
            patch.object(
                ingestion,
                "validate_connection",
                side_effect=RuntimeError("offline failure"),
            ),
        ):
            with self.assertRaises(RuntimeError):
                ingestion.extract_and_load()
        engine.dispose.assert_called_once_with()

    def test_unsafe_identifier_is_rejected(self):
        with self.assertRaises(ValueError):
            ingestion._build_query("crm; DROP TABLE bronze.crm")


if __name__ == "__main__":
    unittest.main()
