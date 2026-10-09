"""
Unit tests for Scripts/ingest_bronze.py

Tests mock SQLAlchemy create_engine to avoid real DB connections.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import TestCase, mock

# Add repository root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set required env vars before importing the module
os.environ.setdefault("DB_DRIVER", "ODBC Driver 18 for SQL Server")
os.environ.setdefault("DB_SERVER", "localhost")
os.environ.setdefault("DB_DATABASE", "TestDB")
os.environ.setdefault("DB_USERNAME", "sa")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("GCP_PROJECT_ID", "test-project")


class TestIngestBronze(TestCase):
    """Tests for the bronze ingestion script."""

    @mock.patch("Scripts.ingest_bronze.create_engine")
    def test_build_engine_uses_mssql_pyodbc(self, mock_create_engine):
        """Test that build_engine creates mssql+pyodbc URL, not postgresql."""
        from Scripts.ingest_bronze import build_engine

        mock_engine = mock.MagicMock()
        mock_create_engine.return_value = mock_engine

        engine = build_engine()

        mock_create_engine.assert_called_once()
        call_args = mock_create_engine.call_args
        # Check the URL was created with mssql+pyodbc dialect
        url = call_args[0][0]
        self.assertEqual(url.get_dialect().name, "mssql")
        self.assertEqual(url.get_driver_name(), "pyodbc")
        # Verify driver parameter is passed
        self.assertIn("driver", url.query)
        self.assertEqual(url.query["driver"], "ODBC Driver 18 for SQL Server")
        self.assertEqual(url.query["TrustServerCertificate"], "yes")

    @mock.patch("Scripts.ingest_bronze.create_engine")
    def test_build_engine_defaults_port_1433(self, mock_create_engine):
        """Test that DB_PORT defaults to 1433 (SQL Server default)."""
        from Scripts.ingest_bronze import build_engine

        mock_engine = mock.MagicMock()
        mock_create_engine.return_value = mock_engine

        # Remove DB_PORT to test default
        os.environ.pop("DB_PORT", None)

        engine = build_engine()

        url = mock_create_engine.call_args[0][0]
        self.assertEqual(url.port, 1433)

    @mock.patch("Scripts.ingest_bronze.create_engine")
    def test_verify_connection_sql_server_query(self, mock_create_engine):
        """Test verify_connection runs SQL Server query, not PostgreSQL."""
        from Scripts.ingest_bronze import build_engine, verify_connection

        mock_engine = mock.MagicMock()
        mock_conn = mock.MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_create_engine.return_value = mock_engine

        engine = build_engine()
        verify_connection(engine)

        # Verify SQL Server query was executed
        mock_conn.execute.assert_called()
        executed_query = str(mock_conn.execute.call_args[0][0])
        self.assertIn("DB_NAME()", executed_query)
        self.assertIn("SYSTEM_USER", executed_query)
        # Ensure no PostgreSQL-specific query
        self.assertNotIn("current_database()", executed_query)
        self.assertNotIn("current_user", executed_query)

    @mock.patch("Scripts.ingest_bronze.create_engine")
    def test_ingest_csv_retry_on_operational_error(self, mock_create_engine):
        """Test ingest_csv retries on OperationalError with exponential backoff."""
        import time
        from sqlalchemy.exc import OperationalError
        from Scripts.ingest_bronze import build_engine, ingest_csv

        mock_engine = mock.MagicMock()
        mock_conn = mock.MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_create_engine.return_value = mock_engine

        # First two attempts fail with OperationalError, third succeeds
        mock_conn.execute.side_effect = [
            OperationalError("statement", "params", "orig"),
            OperationalError("statement", "params", "orig"),
            None,  # Third attempt succeeds for TRUNCATE
        ]

        # Mock to_sql to succeed
        import pandas as pd
        with mock.patch.object(pd.DataFrame, "to_sql") as mock_to_sql:
            engine = build_engine()
            # Create a dummy CSV for testing
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
                f.write("col1,col2\n1,2\n3,4\n")
                csv_path = Path(f.name)

            try:
                rows = ingest_csv(engine, csv_path, "public", "test_table")
                self.assertEqual(rows, 2)
                # Should have retried 3 times (2 failures + 1 success)
                self.assertEqual(mock_conn.execute.call_count, 3)
            finally:
                os.unlink(csv_path)

    @mock.patch("Scripts.ingest_bronze.create_engine")
    def test_ingest_csv_raises_after_max_retries(self, mock_create_engine):
        """Test ingest_csv raises after max retries exhausted."""
        from sqlalchemy.exc import OperationalError
        from Scripts.ingest_bronze import build_engine, ingest_csv

        mock_engine = mock.MagicMock()
        mock_conn = mock.MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_create_engine.return_value = mock_engine

        # All attempts fail
        mock_conn.execute.side_effect = OperationalError("statement", "params", "orig")

        import pandas as pd
        with mock.patch.object(pd.DataFrame, "to_sql") as mock_to_sql:
            engine = build_engine()
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
                f.write("col1,col2\n1,2\n")
                csv_path = Path(f.name)

            try:
                with self.assertRaises(RuntimeError) as cm:
                    ingest_csv(engine, csv_path, "public", "test_table")
                self.assertIn("after 3 attempts", str(cm.exception))
                # Should have attempted 3 times
                self.assertEqual(mock_conn.execute.call_count, 3)
            finally:
                os.unlink(csv_path)

    @mock.patch("Scripts.ingest_bronze.create_engine")
    @mock.patch("Scripts.ingest_bronze.bigquery.Client")
    def test_log_table_ingestion_to_bigquery_retry(self, mock_bq_client, mock_create_engine):
        """Test BigQuery logging retries on GoogleAPICallError."""
        from google.api_core.exceptions import GoogleAPICallError
        from Scripts.ingest_bronze import build_engine, log_table_ingestion_to_bigquery
        from datetime import datetime, UTC

        mock_engine = mock.MagicMock()
        mock_create_engine.return_value = mock_engine

        mock_client = mock.MagicMock()
        mock_bq_client.return_value = mock_client

        # First two attempts fail, third succeeds
        mock_job = mock.MagicMock()
        mock_client.load_table_from_dataframe.side_effect = [
            GoogleAPICallError("attempt 1"),
            GoogleAPICallError("attempt 2"),
            mock_job,  # Third attempt succeeds
        ]

        engine = build_engine()
        log_table_ingestion_to_bigquery(
            run_timestamp=datetime.now(UTC),
            resource_type="csv_ingestion",
            table_name="test.csv",
            target_table="public.test_table",
            source_rows=10,
            destination_rows=10,
            duration_seconds=1.5,
            status="success",
        )

        self.assertEqual(mock_client.load_table_from_dataframe.call_count, 3)
        mock_job.result.assert_called_once()

    @mock.patch("Scripts.ingest_bronze.create_engine")
    @mock.patch("Scripts.ingest_bronze.bigquery.Client")
    def test_get_bigquery_client_retry_on_error(self, mock_bq_client, mock_create_engine):
        """Test _get_bigquery_client retries on GoogleAPICallError with exponential backoff."""
        from google.api_core.exceptions import GoogleAPICallError
        from Scripts.ingest_bronze import build_engine, _get_bigquery_client

        mock_engine = mock.MagicMock()
        mock_create_engine.return_value = mock_engine

        # First two attempts fail, third succeeds
        mock_client = mock.MagicMock()
        mock_bq_client.side_effect = [
            GoogleAPICallError("attempt 1"),
            GoogleAPICallError("attempt 2"),
            mock_client,  # Third attempt succeeds
        ]

        engine = build_engine()
        client = _get_bigquery_client("test-project")

        self.assertEqual(mock_bq_client.call_count, 3)
        self.assertEqual(client, mock_client)

    @mock.patch("Scripts.ingest_bronze.create_engine")
    @mock.patch("Scripts.ingest_bronze.bigquery.Client")
    def test_get_bigquery_client_raises_after_max_retries(self, mock_bq_client, mock_create_engine):
        """Test _get_bigquery_client raises after max retries exhausted."""
        from google.api_core.exceptions import GoogleAPICallError
        from Scripts.ingest_bronze import build_engine, _get_bigquery_client

        mock_engine = mock.MagicMock()
        mock_create_engine.return_value = mock_engine

        # All attempts fail
        mock_bq_client.side_effect = GoogleAPICallError("persistent error")

        engine = build_engine()
        with self.assertRaises(RuntimeError) as cm:
            _get_bigquery_client("test-project")

        self.assertIn("after 3 attempts", str(cm.exception))
        self.assertEqual(mock_bq_client.call_count, 3)

    def test_no_postgresql_strings_in_module(self):
        """Ensure no PostgreSQL-specific strings remain in the module."""
        import Scripts.ingest_bronze as ingest_module
        import inspect

        source = inspect.getsource(ingest_module)
        # Check for PostgreSQL-specific patterns that should not exist
        forbidden = [
            "postgresql",
            "psycopg2",
            "current_database()",
            "current_user",
            "sslmode",
        ]
        for pattern in forbidden:
            self.assertNotIn(pattern.lower(), source.lower(),
                             f"Forbidden pattern '{pattern}' found in module")


if __name__ == "__main__":
    import unittest
    unittest.main()
