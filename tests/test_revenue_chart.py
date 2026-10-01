"""Revenue switcher regression tests; never connect to production."""

import importlib
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
from google.cloud import bigquery

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "my-dash-app"))
from components.revenue_chart import (
    aggregate_countries,
    country_code,
    normalize_view,
    revenue_menu,
)
from utils.cache import cache


class RevenueChartTests(unittest.TestCase):
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

    def setUp(self):
        self.frame = pd.DataFrame(
            {
                "country": ["US", "United States", "DE", None, "Atlantis", "PH"],
                "category": ["bikes", "bikes", "gear", "gear", "gear", "bikes"],
                "gross_sales_amount": [10, 20, 40, 5, 6, 80],
                "order_date": pd.to_datetime(["2025-01-01"] * 5 + ["2024-01-01"]),
            }
        )
        self.filters = {
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
            "category": "ALL",
            "country": "ALL",
        }

    def render(self, view, filters=None, frame=None):
        with patch.object(
            self.overview,
            "load_and_prep_data",
            return_value=(
                self.frame if frame is None else frame,
                None,
                None,
                None,
                None,
            ),
        ):
            return self.overview.update_category_pie(
                self.filters if filters is None else filters, view
            )

    def test_aliases_and_unknown_revenue(self):
        grouped, missing, has_missing = aggregate_countries(self.frame)
        values = grouped.set_index("iso3")["gross_sales_amount"].to_dict()
        self.assertEqual(values, {"USA": 30, "DEU": 40, "PHL": 80})
        self.assertEqual(missing, 11)
        self.assertTrue(has_missing)
        for raw in ["us", " USA ", "United States"]:
            self.assertEqual(country_code(raw), "USA")
        self.assertIsNone(country_code(None))
        self.assertIsNone(country_code("Atlantis"))

    def test_switching_and_filters(self):
        for view in ["donut", "map", "donut", "invalid"]:
            fig, title, details, donut, map_active = self.render(view)
            is_map = view == "map"
            self.assertEqual(fig.data[0].type, "choropleth" if is_map else "pie")
            self.assertEqual(
                title, "Revenue by country" if is_map else "Revenue by category"
            )
            self.assertEqual((donut, map_active), (not is_map, is_map))
            self.assertEqual(
                sum(fig.data[0].z if is_map else fig.data[0].values),
                70 if is_map else 81,
            )
        fig, *_ = self.render("map", {**self.filters, "category": "bikes"})
        self.assertEqual(list(fig.data[0].locations), ["USA"])
        self.assertEqual(list(fig.data[0].z), [30])
        fig, *_ = self.render("map", {**self.filters, "country": "DE"})
        self.assertEqual(list(fig.data[0].z), [40])

    def test_empty_and_unmappable(self):
        for frame in [pd.DataFrame(), None]:
            with patch.object(
                self.overview,
                "load_and_prep_data",
                return_value=(frame, None, None, None, None),
            ):
                fig, *_ = self.overview.update_category_pie(self.filters, "map")
                self.assertEqual(fig.layout.title.text, "No data for selected period")
        fig, _, details, *_ = self.render("map", frame=self.frame.iloc[3:5])
        self.assertIn("No geographic data", fig.layout.title.text)
        self.assertIn("$11", details[0].children)

    def test_layout_and_defaults(self):
        with patch.object(
            self.overview,
            "load_and_prep_data",
            side_effect=AssertionError("Layout queried data"),
        ):
            layout = self.overview.layout()
        store = next(
            child
            for child in layout.children
            if getattr(child, "id", None) == "overview-revenue-view"
        )
        self.assertEqual(store.storage_type, "session")
        self.assertEqual(store.data, "donut")
        self.assertEqual(normalize_view({"unexpected": True}), "donut")
        self.assertIsNotNone(revenue_menu())
