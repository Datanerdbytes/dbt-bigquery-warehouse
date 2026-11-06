"""Lock the KPI values the dashboard shows on the shipped gold database.

The warehouse that used to serve this app is gone and the transformation was
rebuilt on dbt-duckdb, so the numbers on the overview page changed when the
old ``LIMIT 10000`` sample disappeared. These figures are the output of that
rebuild, cross-checked against an independent pandas re-implementation of the
same model SQL (docs/vercel-migration-plan.md section 1.5).

The assertions run through the app's own loader and callbacks rather than
re-implementing the SQL, so they fail when the transformation or the KPI
mathematics drift, not only when the database changes.
"""

import importlib
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "my-dash-app"))

from utils.cache import cache
from utils.helpers import filter_dataframe

START_DATE = "2010-12-29"
END_DATE = "2014-01-28"

EXPECTED_ROWS = 60_379
EXPECTED_TOTAL_SALES = 29_350_874.00
EXPECTED_TOTAL_ORDERS = 27_657
EXPECTED_TOTAL_QUANTITY = 60_404
EXPECTED_TOTAL_CUSTOMERS = 18_482
EXPECTED_ACTIVE_DAYS = 1_124
EXPECTED_CATEGORIES = 3
EXPECTED_COUNTRIES = 6

EXPECTED_KPI_DISPLAY = ("$29.35M", "27,657", "60,404", "18,482")

EXPECTED_REVENUE_BY_COUNTRY = {
    "United States": 9_161_952.00,
    "Australia": 9_060_145.00,
    "United Kingdom": 3_388_998.00,
    "Germany": 2_894_016.00,
    "France": 2_641_260.00,
    "Canada": 1_977_683.00,
}
# Revenue of the 337 customers whose country the source data never filled in.
# It stays visible instead of being dropped.
EXPECTED_UNMAPPED_REVENUE = 226_820.00
EXPECTED_UNMAPPED_ROWS = 871
EXPECTED_UNMAPPED_CUSTOMERS = 337

EXPECTED_RFM_SEGMENTS = {
    "Champions": 142,
    "Loyal Customers": 1_183,
    "Promising / Recent": 3_607,
    "Hibernating / Lost": 13_550,
}


def _forbid_network(*args, **kwargs):
    raise AssertionError("Network access is forbidden in offline tests")


class KpiFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (
            patch.object(socket.socket, "connect", _forbid_network),
            patch.object(socket, "create_connection", _forbid_network),
            patch.object(cache, "init_app"),
        ):
            cls.app = importlib.import_module("app")
        cache.init_app(cls.app.server, config={"CACHE_TYPE": "SimpleCache"})

        cls.data_loader = importlib.import_module("data_loader")
        cls.overview = importlib.import_module("pages.overview")
        cls.customer_360 = importlib.import_module("pages.customer_360")

        cls.merged = cls.data_loader.get_prepared_dataset()
        cls.filtered = filter_dataframe(cls.merged, START_DATE, END_DATE, "ALL", "ALL")

    def test_merged_frame_matches_the_documented_figures(self):
        self.assertEqual(len(self.filtered), EXPECTED_ROWS)
        self.assertEqual(self.filtered["category"].nunique(), EXPECTED_CATEGORIES)
        self.assertEqual(self.filtered["country"].nunique(), EXPECTED_COUNTRIES)
        self.assertEqual(
            self.filtered["order_date"].min().strftime("%Y-%m-%d"), START_DATE
        )
        self.assertEqual(
            self.filtered["order_date"].max().strftime("%Y-%m-%d"), END_DATE
        )

    def test_kpi_aggregates_match_the_documented_figures(self):
        self.assertAlmostEqual(
            float(self.filtered["gross_sales_amount"].sum()),
            EXPECTED_TOTAL_SALES,
            places=2,
        )
        self.assertEqual(
            int(self.filtered["order_number"].nunique()), EXPECTED_TOTAL_ORDERS
        )
        self.assertEqual(int(self.filtered["quantity"].sum()), EXPECTED_TOTAL_QUANTITY)
        self.assertEqual(
            int(self.filtered["customer_key"].nunique()), EXPECTED_TOTAL_CUSTOMERS
        )
        self.assertEqual(
            int(self.filtered["order_date"].dt.date.nunique()), EXPECTED_ACTIVE_DAYS
        )

    def test_overview_callback_returns_the_locked_kpi_display(self):
        result = self.overview.update_all_kpis(
            {
                "start_date": START_DATE,
                "end_date": END_DATE,
                "category": "ALL",
                "country": "ALL",
            }
        )

        self.assertEqual(result[0:4], EXPECTED_KPI_DISPLAY)

    def test_overview_tooltips_report_the_locked_ratios(self):
        result = self.overview.update_all_kpis(
            {
                "start_date": START_DATE,
                "end_date": END_DATE,
                "category": "ALL",
                "country": "ALL",
            }
        )

        sales_tooltip = " ".join(
            str(child.children) for child in result[4] if child.children
        )
        customers_tooltip = " ".join(
            str(child.children) for child in result[7] if child.children
        )

        self.assertIn(
            f"${EXPECTED_TOTAL_SALES / EXPECTED_TOTAL_ORDERS:,.2f}", sales_tooltip
        )
        self.assertIn(
            f"${EXPECTED_TOTAL_SALES / EXPECTED_TOTAL_CUSTOMERS:,.2f}",
            customers_tooltip,
        )

    def test_revenue_by_country_matches_the_documented_figures(self):
        revenue = self.filtered.groupby("country")["gross_sales_amount"].sum()

        for country, expected in EXPECTED_REVENUE_BY_COUNTRY.items():
            with self.subTest(country=country):
                self.assertAlmostEqual(float(revenue[country]), expected, places=2)

    def test_unmapped_customers_keep_their_revenue_visible(self):
        unmapped = self.filtered[self.filtered["country"].isna()]

        self.assertEqual(len(unmapped), EXPECTED_UNMAPPED_ROWS)
        self.assertEqual(
            int(unmapped["customer_key"].nunique()), EXPECTED_UNMAPPED_CUSTOMERS
        )
        self.assertAlmostEqual(
            float(unmapped["gross_sales_amount"].sum()),
            EXPECTED_UNMAPPED_REVENUE,
            places=2,
        )

    def test_rfm_segments_match_the_documented_figures(self):
        figure = self.customer_360.update_rfm_segments(
            {
                "start_date": START_DATE,
                "end_date": END_DATE,
                "category": "ALL",
                "country": "ALL",
            }
        )

        counts = {}
        for trace in figure.data:
            for segment, count in zip(trace.y, trace.x, strict=True):
                counts[str(segment)] = int(count)

        self.assertEqual(counts, EXPECTED_RFM_SEGMENTS)
        self.assertEqual(sum(counts.values()), EXPECTED_TOTAL_CUSTOMERS)


if __name__ == "__main__":
    unittest.main()
