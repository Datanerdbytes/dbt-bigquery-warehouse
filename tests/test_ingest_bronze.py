"""Offline regressions for SQL Server bronze loading and lifecycle audit."""

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlalchemy import Column, Integer, MetaData, Table
from sqlalchemy.exc import OperationalError

from Scripts import ingest_bronze as bronze


class BronzeTests(unittest.TestCase):
    def test_import_does_not_read_env_connect_or_create_cloud_client(self):
        with (
            mock.patch.object(Path, "read_text", side_effect=AssertionError("read")),
            mock.patch(
                "sqlalchemy.create_engine", side_effect=AssertionError("engine")
            ),
            mock.patch(
                "google.cloud.bigquery.Client", side_effect=AssertionError("client")
            ),
        ):
            importlib.reload(bronze)

    def test_connection_string_enforces_sql_server_odbc18(self):
        with (
            mock.patch.dict(
                os.environ,
                {"DB_CONNECTION_STRING": "mssql+pyodbc://user:pass@localhost/db"},
                clear=True,
            ),
            mock.patch.object(bronze, "create_engine") as create,
        ):
            bronze.get_engine()
        url = create.call_args.args[0]
        self.assertEqual(url.drivername, "mssql+pyodbc")
        self.assertEqual(url.query["driver"], "ODBC Driver 18 for SQL Server")

    def test_legacy_env_defaults_driver_and_port(self):
        env = {
            "DB_SERVER": "localhost",
            "DB_DATABASE": "test",
            "DB_USERNAME": "test",
            "DB_PASSWORD": "test",
        }
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(bronze, "create_engine") as create,
        ):
            bronze.build_engine()
        self.assertEqual(create.call_args.args[0].port, 1433)
        self.assertEqual(
            create.call_args.args[0].query["driver"], "ODBC Driver 18 for SQL Server"
        )

    def test_verify_connection_uses_sql_server(self):
        engine = mock.MagicMock()
        bronze.verify_connection(engine)
        query = str(
            engine.connect.return_value.__enter__.return_value.execute.call_args.args[0]
        )
        self.assertIn("DB_NAME()", query)
        self.assertIn("SYSTEM_USER", query)

    def test_csv_retry_replaces_atomically(self):
        engine = mock.MagicMock()
        conn = engine.begin.return_value.__enter__.return_value
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.csv"
            path.write_text("ID\n1\n2\n")
            with (
                mock.patch.object(
                    bronze.pd.DataFrame,
                    "to_sql",
                    side_effect=[OperationalError("sql", None, "failed"), None],
                ) as write,
                mock.patch.object(bronze.time, "sleep") as sleep,
            ):
                self.assertEqual(bronze.ingest_csv(engine, path, "public", "test"), 2)
            self.assertEqual(conn.execute.call_count, 2)
            self.assertIs(write.call_args.kwargs["con"], conn)
            sleep.assert_called_once_with(2.0)
            self.assertEqual(
                engine.begin.return_value.__exit__.call_args_list[0].args[0],
                OperationalError,
            )

    def test_insert_rows_rolls_back_all_batches_before_retry(self):
        engine = mock.MagicMock()
        conn = engine.begin.return_value.__enter__.return_value
        conn.execute.side_effect = [
            None,
            OperationalError("sql", None, "failed"),
            None,
            None,
        ]
        table = Table("test", MetaData(), Column("id", Integer))
        rows = [{"id": 1}, {"id": 2}]
        with mock.patch.object(bronze.time, "sleep") as sleep:
            self.assertEqual(bronze.insert_rows(engine, table, rows, 1), (2, []))
        self.assertEqual(conn.execute.call_count, 4)
        self.assertEqual(
            conn.execute.call_args_list[0].args[1],
            conn.execute.call_args_list[2].args[1],
        )
        sleep.assert_called_once_with(2.0)

    def test_insert_rows_exhaustion_and_backoff(self):
        engine = mock.MagicMock()
        engine.begin.return_value.__enter__.return_value.execute.side_effect = (
            OperationalError("sql", None, "failed")
        )
        table = Table("test", MetaData(), Column("id", Integer))
        with mock.patch.object(bronze.time, "sleep") as sleep:
            count, errors = bronze.insert_rows(engine, table, [{"id": 1}], 1)
        self.assertEqual(count, 0)
        self.assertEqual(len(errors), 1)
        self.assertEqual(sleep.call_args_list, [mock.call(2.0), mock.call(4.0)])

    def test_insert_rows_does_not_retry_unknown_commit(self):
        engine = mock.MagicMock()
        engine.begin.return_value.__exit__.side_effect = OperationalError(
            "commit", None, "failed"
        )
        table = Table("test", MetaData(), Column("id", Integer))
        with mock.patch.object(bronze.time, "sleep") as sleep:
            count, errors = bronze.insert_rows(engine, table, [{"id": 1}])
        self.assertEqual(count, 0)
        self.assertTrue(errors)
        self.assertEqual(engine.begin.call_count, 1)
        sleep.assert_not_called()

    def test_csv_exhaustion_has_bounded_backoff(self):
        engine = mock.MagicMock()
        engine.begin.return_value.__enter__.return_value.execute.side_effect = (
            OperationalError("sql", None, "failed")
        )
        with (
            mock.patch.object(
                bronze.pd, "read_csv", return_value=bronze.pd.DataFrame({"id": [1]})
            ),
            mock.patch.object(bronze.time, "sleep") as sleep,
        ):
            with self.assertRaisesRegex(RuntimeError, "after 3 attempts"):
                bronze.ingest_csv(engine, Path("test.csv"), "public", "test")
        self.assertEqual(sleep.call_args_list, [mock.call(2.0), mock.call(4.0)])

    def test_bigquery_initialization_retry(self):
        from google.api_core.exceptions import GoogleAPICallError

        client = mock.Mock()
        with (
            mock.patch.object(
                bronze.bigquery,
                "Client",
                side_effect=[GoogleAPICallError("offline"), client],
            ) as create,
            mock.patch.object(bronze.time, "sleep") as sleep,
        ):
            self.assertIs(bronze._get_bigquery_client("test-project"), client)
        self.assertEqual(create.call_count, 2)
        sleep.assert_called_once_with(2.0)

    def test_bigquery_table_audit_retry(self):
        from datetime import UTC, datetime

        from google.api_core.exceptions import GoogleAPICallError

        client = mock.Mock()
        client.load_table_from_dataframe.side_effect = [
            GoogleAPICallError("offline"),
            mock.Mock(),
        ]
        with (
            mock.patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}),
            mock.patch.object(bronze, "_get_bigquery_client", return_value=client),
            mock.patch.object(bronze.time, "sleep") as sleep,
        ):
            bronze.log_table_ingestion_to_bigquery(
                datetime.now(UTC),
                "csv_ingestion",
                "test.csv",
                "public.test",
                2,
                2,
                1.0,
                "success",
            )
        self.assertEqual(client.load_table_from_dataframe.call_count, 2)
        self.assertEqual(
            client.load_table_from_dataframe.call_args.args[0].shape, (1, 10)
        )
        sleep.assert_called_once_with(2.0)

    def run_main(self, ingest_error=None, telemetry_error=None):
        with (
            mock.patch.object(bronze, "load_env"),
            mock.patch.object(bronze, "get_engine") as engine,
            mock.patch.object(bronze, "verify_connection"),
            mock.patch.object(
                bronze, "discover_csvs", return_value=[(Path("test.csv"), "crm_test")]
            ),
            mock.patch.object(
                bronze, "ingest_csv", return_value=2, side_effect=ingest_error
            ),
            mock.patch.object(
                bronze, "log_table_ingestion_to_bigquery", side_effect=telemetry_error
            ),
            mock.patch("utils.audit_logger.AuditLogger") as audit,
        ):
            result = bronze.main(["script", "source"])
        engine.return_value.dispose.assert_called_once()
        return result, audit.return_value

    def test_main_start_success(self):
        result, audit = self.run_main()
        self.assertEqual(result, 0)
        audit.log_start.assert_called_once_with(
            "ingest_bronze", {"source_folder": "source"}
        )
        audit.log_success.assert_called_once_with(
            "ingest_bronze", {"tables": 1, "rows": 2}
        )
        audit.log_failure.assert_not_called()

    def test_main_start_failure(self):
        result, audit = self.run_main(RuntimeError("bad csv"))
        self.assertEqual(result, 1)
        audit.log_start.assert_called_once()
        audit.log_failure.assert_called_once()
        audit.log_success.assert_not_called()

    def test_telemetry_failure_preserves_load_success(self):
        result, audit = self.run_main(telemetry_error=RuntimeError("offline"))
        self.assertEqual(result, 0)
        audit.log_success.assert_called_once()

    def test_missing_source_returns_usage_failure_before_engine(self):
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(bronze, "load_env"),
            mock.patch.object(bronze, "get_engine") as engine,
            mock.patch("utils.audit_logger.AuditLogger") as audit,
        ):
            self.assertEqual(bronze.main(["script"]), 2)
        engine.assert_not_called()
        audit.return_value.log_failure.assert_called_once()


if __name__ == "__main__":
    unittest.main()
