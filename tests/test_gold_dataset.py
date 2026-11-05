"""Offline regression checks for the shipped gold database.

`my-dash-app/data/analytics.duckdb` is the artifact the app reads at
runtime. It is produced by the dbt build:

    python Scripts/load_bronze_duckdb.py --fresh
    cd analytics_layer && ../.venv/bin/dbt build --profiles-dir .
    python Scripts/export_gold_duckdb.py

The figures below are the output of that pipeline, cross-checked against an
independent pandas re-implementation of the same model SQL. They fail loudly
if a rebuild changes the transformation, so the port cannot silently drift.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

import duckdb
import pandas as pd

from Scripts.verify_shipped_gold import compare

ROOT = Path(__file__).resolve().parents[1]
GOLD_DB = ROOT / "my-dash-app" / "data" / "analytics.duckdb"

EXPECTED_ROWS = {
    "fct_sales": 60_398,
    "dim_products": 295,
    "dim_customers": 18_484,
    "product_360": 130,
}

EXPECTED_TOTAL_REVENUE = 29_355_866.00
EXPECTED_TOTAL_UNITS = 60_423
EXPECTED_DISTINCT_ORDERS = 27_659
EXPECTED_MIN_DATE = "1900-01-01"
EXPECTED_MAX_DATE = "2014-01-28"


class GoldDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not GOLD_DB.exists():
            raise AssertionError(
                f"Missing gold database artifact: {GOLD_DB}. "
                "Rebuild it with Scripts/load_bronze_duckdb.py, dbt build and "
                "Scripts/export_gold_duckdb.py."
            )
        cls.connection = duckdb.connect(str(GOLD_DB), read_only=True)

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def test_gold_tables_have_expected_row_counts(self):
        for table, expected in EXPECTED_ROWS.items():
            with self.subTest(table=table):
                rows = self.connection.execute(
                    f"SELECT COUNT(*) FROM gold.{table}"
                ).fetchone()[0]
                self.assertEqual(rows, expected)

    def test_fact_measures_match_expected_values(self):
        row = self.connection.execute(
            """
            SELECT
                SUM(gross_sales_amount),
                SUM(quantity),
                COUNT(DISTINCT order_number),
                MIN(order_date),
                MAX(order_date),
                COUNT(*) FILTER (WHERE gross_sales_amount IS NULL)
            FROM gold.fct_sales
            """
        ).fetchone()

        self.assertAlmostEqual(float(row[0]), EXPECTED_TOTAL_REVENUE, places=2)
        self.assertEqual(row[1], EXPECTED_TOTAL_UNITS)
        self.assertEqual(row[2], EXPECTED_DISTINCT_ORDERS)
        self.assertEqual(str(row[3])[:10], EXPECTED_MIN_DATE)
        self.assertEqual(str(row[4])[:10], EXPECTED_MAX_DATE)
        self.assertEqual(row[5], 0)

    def test_dimension_attributes_are_populated(self):
        customers = self.connection.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE country IS NULL),
                COUNT(DISTINCT country),
                COUNT(DISTINCT marital_status)
            FROM gold.dim_customers
            """
        ).fetchone()
        self.assertEqual(customers[0], 337)
        self.assertEqual(customers[1], 6)
        self.assertEqual(customers[2], 2)

        products = self.connection.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE category IS NULL),
                COUNT(DISTINCT category)
            FROM gold.dim_products
            """
        ).fetchone()
        self.assertEqual(products[0], 0)
        self.assertEqual(products[1], 4)

    def test_app_shaped_merge_keeps_the_dataframe_contract(self):
        merged = self.connection.execute(
            """
            SELECT
                f.product_key,
                f.customer_key,
                f.order_date,
                f.order_number,
                f.quantity,
                f.gross_sales_amount,
                f.unit_price,
                p.product_name,
                p.category,
                p.cost,
                c.first_name,
                c.last_name,
                c.country
            FROM gold.fct_sales f
            LEFT JOIN gold.dim_products p ON p.product_key = f.product_key
            LEFT JOIN gold.dim_customers c ON c.customer_key = f.customer_key
            WHERE f.order_date >= DATE '2010-01-01'
            """
        ).df()

        self.assertEqual(len(merged), 60_379)
        self.assertAlmostEqual(
            float(merged["gross_sales_amount"].sum()), 29_350_874.00, places=2
        )
        self.assertEqual(merged["order_number"].nunique(), 27_657)
        self.assertEqual(merged["category"].nunique(), 3)
        self.assertEqual(merged["country"].nunique(), 6)
        self.assertEqual(merged["customer_key"].nunique(), 18_482)

        # The dashboard normalizes these to float64 before any aggregation.
        self.assertTrue(str(merged["order_date"].dtype).startswith("datetime64"))
        for column in ("gross_sales_amount", "unit_price", "cost"):
            normalized = pd.to_numeric(merged[column], errors="coerce").astype(
                "float64"
            )
            self.assertEqual(normalized.dtype, "float64")
            self.assertFalse(normalized.isna().any())


class ShippedGoldDriftTests(unittest.TestCase):
    """The CI drift gate must detect a stale shipped artifact."""

    def test_identical_databases_report_no_drift(self):
        self.assertEqual(compare(GOLD_DB, GOLD_DB), [])

    def test_modified_database_is_reported_as_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            tampered = Path(tmp) / "tampered.duckdb"
            shutil.copyfile(GOLD_DB, tampered)

            connection = duckdb.connect(str(tampered))
            connection.execute(
                """
                UPDATE gold.fct_sales
                SET gross_sales_amount = gross_sales_amount + 1
                WHERE sales_item_key = (
                    SELECT sales_item_key FROM gold.fct_sales LIMIT 1
                )
                """
            )
            connection.close()

            differences = compare(GOLD_DB, tampered)

        self.assertTrue(differences)
        self.assertTrue(any("gross_sales_amount" in item for item in differences))


if __name__ == "__main__":
    unittest.main()
