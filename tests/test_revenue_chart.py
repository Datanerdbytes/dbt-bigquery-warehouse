"""Revenue switcher regression tests; never connect to production."""

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
            "get_prepared_dataset",
            return_value=self.frame if frame is None else frame,
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
                title, "Revenue by Country" if is_map else "Revenue by Category"
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

    def test_donut_total_tracks_filters_and_does_not_mutate_shared_data(self):
        original = self.frame.copy(deep=True)
        for filters, total in [
            (self.filters, "$81"),
            ({**self.filters, "category": "bikes"}, "$30"),
            ({**self.filters, "country": "DE"}, "$40"),
        ]:
            figure, *_ = self.render("donut", filters)
            self.assertEqual(
                [annotation.text for annotation in figure.layout.annotations],
                ["Total revenue", total],
            )
        pd.testing.assert_frame_equal(self.frame, original)

    def test_donut_uses_legend_instead_of_slice_labels(self):
        figure, *_ = self.render("donut")
        self.assertEqual(figure.data[0].textinfo, "none")
        self.assertTrue(figure.layout.showlegend)
        self.assertEqual(figure.layout.legend.orientation, "h")
        self.assertEqual(figure.layout.legend.xanchor, "center")
        self.assertLess(figure.layout.legend.y, 0)
        self.assertEqual(set(figure.data[0].labels), {"Bikes", "Gear"})
        self.assertIn("%{label}", figure.data[0].hovertemplate)
        self.assertIn("%{percent}", figure.data[0].hovertemplate)

    def test_empty_and_unmappable(self):
        for frame in [pd.DataFrame(), None]:
            with patch.object(
                self.overview,
                "get_prepared_dataset",
                return_value=frame,
            ):
                fig, *_ = self.overview.update_category_pie(self.filters, "map")
                self.assertEqual(fig.layout.title.text, "No data for selected period")
        fig, _, details, *_ = self.render("map", frame=self.frame.iloc[3:5])
        self.assertIn("No geographic data", fig.layout.title.text)
        self.assertIn("$11", details[0].children)

    def test_layout_and_defaults(self):
        with patch.object(
            self.overview,
            "get_prepared_dataset",
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

        def find_graph(component):
            if getattr(component, "id", None) == "category-pie-graph":
                return component
            children = getattr(component, "children", None)
            for child in children if isinstance(children, list) else [children]:
                if child is not None:
                    found = find_graph(child)
                    if found is not None:
                        return found
            return None

        self.assertEqual(find_graph(layout).config["topojsonURL"], "/assets/topojson/")
        self.assertIsNotNone(revenue_menu())
