"""Security tests for Scripts/ingest_bigquery.py.

These tests verify that table names are validated against a strict allowlist
and that identifiers are never interpolated directly into SQL strings.
"""

import importlib
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Allowlist regex used by the ingestion script.
TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _import_module():
    """Import the ingestion module with heavy dependencies patched out."""
    if "Scripts.ingest_bigquery" in sys.modules:
        del sys.modules["Scripts.ingest_bigquery"]
    with (
        patch("Scripts.ingest_bigquery.service_account") as _sa,
        patch("Scripts.ingest_bigquery.bigquery") as _bq,
        patch("Scripts.ingest_bigquery.create_engine") as _engine,
        patch("Scripts.ingest_bigquery.log_execution_to_bigquery"),
    ):
        return importlib.import_module("Scripts.ingest_bigquery")


class TestTableAllowlist(unittest.TestCase):
    """Validate that only safe table names pass the allowlist."""

    VALID = [
        "crm_cust_info",
        "crm_prd_info",
        "crm_sales_details",
        "erp_cust_az12",
        "erp_loc_a101",
        "erp_px_cat_g1v2",
        "a",
        "_underscore",
        "CamelCase",
        "name123",
    ]

    INVALID = [
        "localhost; DROP TABLE users",
        "table'--",
        "table; DELETE FROM",
        "table name",
        "table\n",
        "1bad",
        "-dash",
        "dot.table",
        "semi;separated",
        "  spaces  ",
        "",
        "table--comment",
        "table/*block*/",
        "drop;table",
        "drop table",
    ]

    def test_valid_names_match_allowlist(self):
        for name in self.VALID:
            with self.subTest(name=name):
                self.assertIsNotNone(TABLE_NAME_RE.fullmatch(name))

    def test_invalid_names_rejected_by_allowlist(self):
        for name in self.INVALID:
            with self.subTest(name=name):
                self.assertIsNone(TABLE_NAME_RE.fullmatch(name))


class TestTableInterpolationIsSafe(unittest.TestCase):
    """Ensure the ingestion script never interpolates raw table names."""

    def test_query_uses_quoted_identifier_not_raw_interpolation(self):
        """The generated SQL must use a quoted identifier, not raw text."""
        module = _import_module()
        sql = module._build_query("crm_cust_info")
        # The query must use a quoted identifier (square brackets).
        self.assertEqual(
            sql, "SELECT * FROM bronze.[crm_cust_info]"
        )
        # The raw name must not appear unquoted in the SQL.
        self.assertNotIn("FROM bronze.crm_cust_info", sql)

    def test_unsafe_table_name_is_blocked(self):
        """Unsafe names must raise before any SQL is constructed."""
        module = _import_module()
        for bad in [
            "localhost; DROP TABLE users",
            "table'--",
            "table; DELETE FROM",
            "table name",
            "1bad",
            "-dash",
            "dot.table",
            "drop;table",
            "drop table",
        ]:
            with self.subTest(name=bad):
                with self.assertRaises(ValueError):
                    module._build_query(bad)

    def test_validate_table_name_returns_input_on_success(self):
        module = _import_module()
        self.assertEqual(module._validate_table_name("crm_cust_info"), "crm_cust_info")


if __name__ == "__main__":
    unittest.main()
