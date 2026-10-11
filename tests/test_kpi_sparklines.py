"""Offline KPI bucket math, filtering, and callback integration."""

import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from google.cloud import bigquery

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "my-dash-app"))
from components.kpi_sparklines import aggregate_kpi_trends, kpi_sparkline_figures

from utils.cache import cache


class KpiSparklineTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame(
            {
                "order_date": pd.to_datetime(["2026-01-03"] * 3 + ["2026-01-10"] * 2),
                "order_number": ["a", "a", "b", "c", "d"],
                "customer_key": ["one", "one", "two", "one", "one"],
                "gross_sales_amount": [10.0, 20.0, 70.0, 60.0, 40.0],
                "quantity": [1, 2, 7, 6, 4],
                "category": ["bikes"] * 5,
                "country": ["PH"] * 5,
            }
        )

    def test_product_buckets_distinct_counts_empty_and_partial(self):
        original = self.frame.copy(deep=True)
        trend = aggregate_kpi_trends(self.frame, "2026-01-03", "2026-01-25", "product")
        self.assertEqual(trend.metric0.tolist(), [100, 100, 0, 0])
        self.assertEqual(trend.metric1.tolist(), [2, 2, 0, 0])
        self.assertEqual(trend.metric2.tolist(), [10, 10, 0, 0])
        self.assertEqual(trend.metric3.tolist(), [2, 1, 0, 0])
        self.assertIn("Jan 03, 2026", trend.period.iloc[0])
        self.assertIn("partial period", trend.period.iloc[-1])
        self.assertNotIn("partial period", trend.period.iloc[0])
        pd.testing.assert_frame_equal(original, self.frame)

    def test_customer_ratios_are_per_bucket_not_cumulative(self):
        trend = aggregate_kpi_trends(self.frame, "2026-01-03", "2026-01-25", "customer")
        self.assertEqual(trend.metric0.tolist(), [2, 1, 0, 0])
        self.assertEqual(trend.metric1.iloc[:2].tolist(), [50, 100])
        self.assertEqual(trend.metric2.iloc[:2].tolist(), [1, 2])
        self.assertEqual(trend.metric3.iloc[:2].tolist(), [0, 100])
        self.assertTrue(
            trend.loc[2:, ["metric1", "metric2", "metric3"]].isna().all().all()
        )

    def test_ratio_lines_and_shading_preserve_missing_period_gaps(self):
        figures = kpi_sparkline_figures(
            self.frame, "2026-01-03", "2026-01-25", "customer"
        )
        figure = figures[1]
        self.assertEqual(figure.data[0].fill, "none")
        self.assertFalse(figure.data[0].connectgaps)
        self.assertEqual(list(figure.data[1].y), [50, 100])
        self.assertEqual(len(figure.data[1].x), 2)

    def test_monthly_clips_selection_and_single_point_and_no_data(self):
        trend = aggregate_kpi_trends(self.frame, "2025-11-15", "2026-01-20", "product")
        self.assertEqual(len(trend), 3)
        self.assertEqual(trend.metric0.tolist(), [0, 0, 200])
        self.assertIn("Nov 15", trend.period.iloc[0])
        self.assertIn("partial period", trend.period.iloc[0])
        self.assertNotIn("partial period", trend.period.iloc[1])
        self.assertIn("Jan 20", trend.period.iloc[2])
        figure = kpi_sparkline_figures(self.frame, "2026-01-03", "2026-01-03")[0]
        self.assertEqual(figure.data[0].mode, "lines+markers")
        self.assertIn("partial period", figure.data[0].customdata[0])
        for figure in kpi_sparkline_figures(
            self.frame.iloc[:0], "2026-01-03", "2026-01-25"
        ):
            self.assertEqual(figure.layout.annotations[0].text, "No trend data")


class KpiSparklineCallbackTests(unittest.TestCase):
    setUp = KpiSparklineTests.setUp

    @classmethod
    def setUpClass(cls):
        with (
            patch.object(
                bigquery, "Client", side_effect=AssertionError("No production access")
            ),
            patch.object(cache, "init_app"),
        ):
            importlib.import_module("app")
        cls.overview = sys.modules["pages.overview"]
        cls.customer = sys.modules["pages.customer_360"]

    def test_callbacks_filter_and_load_once_without_mutating_shared_data(self):
        original = self.frame.copy(deep=True)
        for module, callback in [
            (self.overview, self.overview.update_all_kpis),
            (self.customer, self.customer.update_customer_kpis),
        ]:
            filters = dict(
                start_date="2026-01-10",
                end_date="2026-01-16",
                category="bikes",
                country="PH",
            )
            with patch.object(
                module, "get_prepared_dataset", return_value=self.frame
            ) as loader:
                result = callback(filters)
            loader.assert_called_once()
            self.assertEqual(len(result), 20)
            self.assertIn("First available period", result[-4])
            self.assertIn("Latest available period", result[-4])
            self.assertEqual(
                list(result[-8].data[0].y), [100 if module is self.overview else 1]
            )
            with patch.object(module, "get_prepared_dataset", return_value=self.frame):
                empty = callback({**filters, "country": "DE"})
            self.assertTrue(
                all(
                    fig.layout.annotations[0].text == "No trend data"
                    for fig in empty[-8:-4]
                )
            )
            pd.testing.assert_frame_equal(self.frame, original)
