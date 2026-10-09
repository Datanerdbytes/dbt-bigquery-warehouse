"""Offline regression checks: python -B -m unittest discover -s tests -v."""

import importlib
import json
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
from google.cloud import bigquery
from plotly.utils import PlotlyJSONEncoder

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "my-dash-app"))

import auth
import data_loader
from components import header

from utils.cache import cache
from utils.helpers import dataframe_value, filter_dataframe


class DashboardRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Importing the real app must never construct a production client.
        with (
            patch.object(
                bigquery,
                "Client",
                side_effect=AssertionError("Production access forbidden"),
            ),
            patch.object(cache, "init_app"),
        ):
            cls.dashboard = importlib.import_module("app")
        cache.init_app(cls.dashboard.server, config={"CACHE_TYPE": "SimpleCache"})
        cls.pipeline = sys.modules["pages.pipeline_health"]

    def setUp(self):
        self.no_production = patch.object(
            bigquery,
            "Client",
            side_effect=AssertionError("Production access forbidden"),
        )
        self.no_production.start()
        self.addCleanup(self.no_production.stop)
        cache.clear()

    def load_sales(self, frames):
        client = Mock()
        client.query.side_effect = [
            Mock(to_dataframe=Mock(return_value=frame)) for frame in frames
        ]
        with patch.object(data_loader, "get_bigquery_client", return_value=client):
            result = data_loader.load_and_prep_data.uncached()
        return result, client

    @staticmethod
    def frames(dates):
        sales = pd.DataFrame(
            {
                "product_key": ["p1"] * len(dates),
                "customer_key": ["c1"] * len(dates),
                "order_date": dates,
                "order_number": list(range(len(dates))),
                "quantity": [1] * len(dates),
                "gross_sales_amount": [20] * len(dates),
                "unit_price": [20] * len(dates),
            }
        )
        products = pd.DataFrame(
            [{"product_key": "p1", "product_name": "Bike", "category": "bikes"}]
        )
        customers = pd.DataFrame(
            [
                {
                    "customer_key": "c1",
                    "first_name": "A",
                    "last_name": "B",
                    "country": "PH",
                }
            ]
        )
        return sales, products, customers

    def test_empty_sources_keep_expected_schema_and_no_dates(self):
        for frames in [(None, None, None), (pd.DataFrame(),) * 3, self.frames([])]:
            with self.subTest(frames=type(frames[0]).__name__):
                (df, start, end, categories, countries), _ = self.load_sales(frames)
                self.assertTrue(df.empty)
                self.assertTrue(
                    {"order_date", "product_name", "country", "gross_sales_amount"}
                    <= set(df.columns)
                )
                self.assertIsNone(start)
                self.assertIsNone(end)
                self.assertEqual(
                    categories, [{"label": "All Categories", "value": "ALL"}]
                )
                self.assertEqual(
                    countries, [{"label": "All Countries", "value": "ALL"}]
                )

    def test_invalid_and_excluded_dates_do_not_crash(self):
        (df, start, end, *_), _ = self.load_sales(
            self.frames(["2009-12-31", None, "bad-date"])
        )
        self.assertTrue(df.empty)
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_valid_sales_keep_joins_and_totals(self):
        (df, start, end, categories, _), client = self.load_sales(
            self.frames(["2010-01-01", "2026-09-01"])
        )
        self.assertEqual(df["gross_sales_amount"].sum(), 40)
        self.assertEqual(list(df["product_name"]), ["Bike", "Bike"])
        self.assertEqual((start, end), ("2010-01-01", "2026-09-01"))
        self.assertEqual(categories[-1]["value"], "bikes")
        self.assertIn(
            "WHERE order_date >= DATE '2010-01-01'",
            client.query.call_args_list[0].args[0],
        )

    def test_decimal_amounts_are_normalized_to_float64(self):
        sales, products, customers = self.frames(["2026-09-01", "2026-09-02"])
        sales["gross_sales_amount"] = [Decimal("10.50"), Decimal("20.25")]
        sales["unit_price"] = [Decimal("5.25"), Decimal("10.125")]
        (df, *_), _ = self.load_sales((sales, products, customers))

        self.assertEqual(df["gross_sales_amount"].dtype, "float64")
        self.assertEqual(df["unit_price"].dtype, "float64")
        self.assertEqual(df["gross_sales_amount"].sum(), 30.75)
        self.assertEqual(df["unit_price"].sum(), 15.375)

    def test_non_numeric_amounts_become_nan_not_strings(self):
        sales, products, customers = self.frames(["2026-09-01"])
        sales["gross_sales_amount"] = [None]
        sales["unit_price"] = ["not-a-number"]
        (df, *_), _ = self.load_sales((sales, products, customers))

        self.assertEqual(df["gross_sales_amount"].dtype, "float64")
        self.assertEqual(df["unit_price"].dtype, "float64")
        self.assertTrue(df["gross_sales_amount"].isna().all())
        self.assertTrue(df["unit_price"].isna().all())

    def test_prepared_dataset_reuses_one_frame_per_ttl_window(self):
        loader = Mock(side_effect=lambda limit=10000: (pd.DataFrame({"a": [1]}),) * 5)
        data_loader._DATASET_HOT_CACHE.update(
            {"key": None, "value": None, "expires_at": 0.0}
        )
        self.addCleanup(
            data_loader._DATASET_HOT_CACHE.update,
            {"key": None, "value": None, "expires_at": 0.0},
        )

        with patch.object(data_loader, "load_and_prep_data", loader):
            first = data_loader.get_prepared_dataset()
            second = data_loader.get_prepared_dataset()

        self.assertEqual(loader.call_count, 1)
        self.assertIs(first, second)

        data_loader._DATASET_HOT_CACHE["expires_at"] = time.monotonic() - 1
        with patch.object(data_loader, "load_and_prep_data", loader):
            refreshed = data_loader.get_prepared_dataset()

        self.assertEqual(loader.call_count, 2)
        self.assertIsNot(first, refreshed)

    def test_prepared_dataset_coalesces_concurrent_cold_and_expired_loads(self):
        self.addCleanup(
            data_loader._DATASET_HOT_CACHE.update,
            {"key": None, "value": None, "expires_at": 0.0},
        )

        def check_concurrent_load(expired):
            frame = pd.DataFrame({"a": [1]})
            data_loader._DATASET_HOT_CACHE.update(
                key=(10000,) if expired else None,
                value=pd.DataFrame({"a": [0]}) if expired else None,
                expires_at=0.0,
            )
            all_waiting = threading.Event()
            release_loader = threading.Event()
            loader_started = threading.Event()
            count_lock = threading.Lock()
            population_lock = threading.Lock()
            attempts = 0

            class ObservedLock:
                def __enter__(self):
                    nonlocal attempts
                    with count_lock:
                        attempts += 1
                        if attempts == 8:
                            all_waiting.set()
                    population_lock.acquire()

                def __exit__(self, *args):
                    population_lock.release()

            def load(limit=10000):
                loader_started.set()
                if not release_loader.wait(timeout=5):
                    raise TimeoutError("Test did not release the dataset loader")
                return frame, None, None, [], []

            with (
                patch.object(data_loader, "_DATASET_HOT_CACHE_LOCK", ObservedLock()),
                patch.object(
                    data_loader, "load_and_prep_data", side_effect=load
                ) as loader,
                ThreadPoolExecutor(max_workers=8) as pool,
            ):
                futures = [
                    pool.submit(data_loader.get_prepared_dataset) for _ in range(8)
                ]
                try:
                    self.assertTrue(loader_started.wait(timeout=3))
                    self.assertTrue(all_waiting.wait(timeout=3))
                    self.assertEqual(loader.call_count, 1)
                finally:
                    release_loader.set()
                results = [future.result(timeout=3) for future in futures]
                self.assertEqual(loader.call_count, 1)
                for result in results:
                    self.assertIs(result, frame)

        for expired in (False, True):
            with self.subTest(expired=expired):
                check_concurrent_load(expired)

    def test_prepared_dataset_ttl_starts_after_loading_and_failure_can_retry(self):
        data_loader._DATASET_HOT_CACHE.update(key=None, value=None, expires_at=0.0)
        self.addCleanup(
            data_loader._DATASET_HOT_CACHE.update,
            {"key": None, "value": None, "expires_at": 0.0},
        )
        frame = pd.DataFrame({"a": [1]})
        with patch.object(
            data_loader, "load_and_prep_data", side_effect=RuntimeError("Load failed")
        ):
            with self.assertRaisesRegex(RuntimeError, "Load failed"):
                data_loader.get_prepared_dataset()
        self.assertIsNone(data_loader._DATASET_HOT_CACHE["key"])

        with (
            patch.object(
                data_loader, "load_and_prep_data", return_value=(frame,) * 5
            ) as loader,
            patch.object(data_loader.time, "monotonic", side_effect=[100, 200, 250]),
            patch.object(data_loader, "_dataset_cache_ttl_seconds", return_value=60),
        ):
            self.assertIs(data_loader.get_prepared_dataset(), frame)
            self.assertEqual(data_loader._DATASET_HOT_CACHE["expires_at"], 260)
            self.assertIs(data_loader.get_prepared_dataset(), frame)
            loader.assert_called_once_with(limit=10000)

    def test_prepared_dataset_reloads_for_a_different_limit(self):
        frame = pd.DataFrame({"a": [1, 2, 3, 4, 5]})
        loader = Mock(side_effect=lambda limit=10000: (frame.head(limit),) * 5)
        data_loader._DATASET_HOT_CACHE.update(
            {"key": None, "value": None, "expires_at": 0.0}
        )
        self.addCleanup(
            data_loader._DATASET_HOT_CACHE.update,
            {"key": None, "value": None, "expires_at": 0.0},
        )

        with patch.object(data_loader, "load_and_prep_data", loader):
            full = data_loader.get_prepared_dataset()
            small = data_loader.get_prepared_dataset(limit=3)

        self.assertEqual(loader.call_count, 2)
        self.assertEqual(len(full), 5)
        self.assertEqual(len(small), 3)

    def test_filtered_views_do_not_mutate_the_shared_dataset(self):
        frame = pd.DataFrame(
            {
                "order_date": pd.to_datetime(["2026-01-05", "2026-06-05"]),
                "quantity": [1, 2],
            }
        )
        original = frame.copy()
        filter_dataframe(frame, "2026-01-01", "2026-03-31", None, None)
        pd.testing.assert_frame_equal(frame, original)

    def test_missing_dimensions_do_not_discard_sales(self):
        sales, _, _ = self.frames(["2026-09-01"])
        (df, *_), _ = self.load_sales((sales, None, None))
        self.assertEqual(len(df), 1)
        self.assertTrue(df["category"].isna().all())

    def test_filter_handles_none_and_preserves_empty_schema(self):
        self.assertTrue(filter_dataframe(None, "2026-01-01", "2026-09-01").empty)
        empty = pd.DataFrame(columns=["order_date", "quantity"])
        self.assertEqual(
            list(filter_dataframe(empty, None, None).columns), list(empty.columns)
        )

    def test_filters_preserve_input_and_apply_date_category_country(self):
        df = pd.DataFrame(
            {
                "order_date": pd.to_datetime(
                    ["2026-01-01", "2026-01-02", "2026-01-02"]
                ),
                "category": ["bikes", "bikes", "parts"],
                "country": ["US", "PH", "PH"],
            }
        )
        before = df.copy(deep=True)
        result = filter_dataframe(df, "2026-01-02", "2026-01-02", "bikes", "PH")
        self.assertEqual(list(result.index), [1])
        pd.testing.assert_frame_equal(df, before)

    def test_optional_summary_values_handle_pandas_nulls(self):
        for frame in [
            None,
            pd.DataFrame(),
            pd.DataFrame([{"passed_tests": pd.NA}]),
            pd.DataFrame([{"other": 1}]),
        ]:
            self.assertEqual(dataframe_value(frame, "passed_tests", 0), 0)

    def test_header_layout_never_loads_health(self):
        with patch.object(
            header,
            "load_pipeline_health_summary",
            side_effect=AssertionError("Layout query"),
        ):
            layout = header.create_header()
            self.assertIn(
                "header-health-refresh", json.dumps(layout, cls=PlotlyJSONEncoder)
            )

    def test_dash_layout_and_callback_registration_work_without_queries(self):
        client = self.dashboard.server.test_client()
        with patch("auth.verify_access", return_value=({"id": "test-user"}, 3600)):
            for path in ["/dashboard", "/_dash-layout", "/_dash-dependencies"]:
                response = client.get(path)
                self.assertEqual(
                    response.status_code, 200, response.get_data(as_text=True)
                )
            dependencies = client.get("/_dash-dependencies").get_json()
        self.assertTrue(
            any("header-health-menu" in callback["output"] for callback in dependencies)
        )

    def test_auth_routes_and_bundle_are_registered_together(self):
        client = self.dashboard.server.test_client()
        with patch("auth.verify_access", return_value=({"id": "test-user"}, 3600)):
            html = client.get("/dashboard").get_data(as_text=True)
        self.assertEqual(html.count('src="/assets/auth.bundle.js"'), 1)
        self.assertNotIn("auth.bundle.js?m=", html)
        self.assertNotIn("showcase.bundle.js", html)
        self.assertIn('id="auth-session-loading"', html)
        self.assertIn('id="auth-form"', client.get("/login").get_data(as_text=True))
        with client.get("/assets/auth.bundle.js") as response:
            self.assertEqual(response.status_code, 200)
        with client.get("/assets/showcase.bundle.js") as response:
            self.assertEqual(response.status_code, 200)
        with patch(
            "auth.verify_access",
            side_effect=auth.AuthError("session_required", 401),
        ):
            self.assertEqual(client.get("/_dash-layout").status_code, 401)

    def test_empty_header_does_not_claim_healthy(self):
        for frame in [None, pd.DataFrame()]:
            state = header.build_health_state(frame)
            text = json.dumps(state, cls=PlotlyJSONEncoder)
            self.assertIn("unavailable", text)
            self.assertNotIn("Pipeline healthy", text)
            self.assertFalse(state[5])

    def test_header_handles_query_failure(self):
        with (
            patch.object(
                header,
                "load_pipeline_health_summary",
                side_effect=RuntimeError("offline"),
            ),
            self.assertLogs(header.logger, level="ERROR"),
        ):
            result = header.refresh_header_health("/", 0, None)
        self.assertIn("unavailable", json.dumps(result, cls=PlotlyJSONEncoder))
        self.assertFalse(result[5])

    def test_header_alerts_refresh_and_do_not_reopen_dismissed_toast(self):
        critical = pd.DataFrame(
            [
                {
                    "overall_system_status": "CRITICAL",
                    "failed_tests": 2,
                    "last_dbt_run": "2026-09-29",
                }
            ]
        )
        healthy = pd.DataFrame(
            [{"overall_system_status": "HEALTHY", "failed_tests": 0}]
        )
        with patch.object(
            header,
            "load_pipeline_health_summary",
            side_effect=[critical, critical, healthy],
        ):
            first = header.refresh_header_health("/", 0, None)
            repeated = header.refresh_header_health("/customers", 1, first[-1])
            cleared = header.refresh_header_health("/customers", 2, repeated[-1])
        self.assertTrue(first[5])
        self.assertIs(repeated[5], header.no_update)
        self.assertFalse(cleared[5])
        self.assertIsNone(cleared[-1])

    def test_header_null_counts_are_safe(self):
        state = header.build_health_state(
            pd.DataFrame(
                [
                    {
                        "overall_system_status": pd.NA,
                        "failed_tests": pd.NA,
                        "warning_tests": None,
                    }
                ]
            )
        )
        self.assertIn("UNKNOWN", json.dumps(state, cls=PlotlyJSONEncoder))

    def test_ingestion_history_is_bounded_and_parameterized(self):
        client = Mock()
        client.query.return_value.to_dataframe.return_value = pd.DataFrame()
        with patch.object(data_loader, "get_bigquery_client", return_value=client):
            data_loader.load_table_ingestion_logs.uncached(days_back=7, limit=50)
        sql = client.query.call_args.args[0]
        params = client.query.call_args.kwargs["job_config"].query_parameters
        self.assertIn("LIMIT @limit", sql)
        self.assertIn("INTERVAL @days_back DAY", sql)
        self.assertEqual(
            {p.name: p.value for p in params}, {"days_back": 7, "limit": 50}
        )

    def test_ingestion_query_rejects_invalid_bounds_before_fetch(self):
        with patch.object(data_loader, "get_bigquery_client") as factory:
            for kwargs in [
                {"days_back": 0},
                {"days_back": 366},
                {"limit": 0},
                {"limit": 1001},
                {"limit": "1; DROP"},
            ]:
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    data_loader.load_table_ingestion_logs.uncached(**kwargs)
            factory.assert_not_called()

    def test_latest_ingestion_snapshot_is_independent_of_history_window(self):
        client = Mock()
        client.query.return_value.to_dataframe.return_value = pd.DataFrame()
        with patch.object(data_loader, "get_bigquery_client", return_value=client):
            data_loader.load_table_ingestion_logs.uncached(latest_only=True)
        sql = client.query.call_args.args[0]
        self.assertIn("QUALIFY ROW_NUMBER()", sql)
        self.assertNotIn("TIMESTAMP_SUB", sql)
        self.assertNotIn("LIMIT", sql)

    def test_cache_separates_history_parameters_and_latest_snapshot(self):
        client = Mock()
        client.query.return_value.to_dataframe.return_value = pd.DataFrame()
        with patch.object(data_loader, "get_bigquery_client", return_value=client):
            data_loader.load_table_ingestion_logs(days_back=7, limit=10)
            data_loader.load_table_ingestion_logs(days_back=7, limit=10)
            data_loader.load_table_ingestion_logs(days_back=14, limit=10)
            data_loader.load_table_ingestion_logs(latest_only=True)
        self.assertEqual(client.query.call_count, 3)

    def test_source_freshness_uses_latest_successful_load_per_source(self):
        client = Mock()
        with patch.object(data_loader, "get_bigquery_client", return_value=client):
            data_loader.load_source_freshness.uncached()
        sql = client.query.call_args.args[0]
        self.assertIn("status IN ('pass', 'success')", sql)
        self.assertIn("PARTITION BY target_table, node_name", sql)
        self.assertIn("QUALIFY ROW_NUMBER()", sql)

    def test_pipeline_handles_null_summary_and_freshness(self):
        summary = pd.DataFrame(
            [{"passed_tests": pd.NA, "overall_column_coverage_pct": None}]
        )
        freshness = pd.DataFrame([{"hours_since_load": None, "last_loaded": None}])
        with (
            patch.object(
                self.pipeline, "load_pipeline_health_summary", return_value=summary
            ),
            patch.object(
                self.pipeline, "load_source_freshness", return_value=freshness
            ),
        ):
            result = self.pipeline.update_pipeline_data("tab-bq-costs")
        self.assertEqual(result[0].children, "N/A")
        self.assertEqual(result[1].children, "N/A")
        self.assertEqual(result[2].children, "0")
        self.assertTrue(all(value is header.no_update for value in result[12:]))

    def test_freshness_kpi_reports_oldest_source_not_newest(self):
        freshness = pd.DataFrame(
            {"hours_since_load": [1, 48], "last_loaded": ["2026-09-29", "2026-09-27"]}
        )
        with (
            patch.object(
                self.pipeline, "load_pipeline_health_summary", return_value=None
            ),
            patch.object(
                self.pipeline, "load_source_freshness", return_value=freshness
            ),
        ):
            result = self.pipeline.update_pipeline_data("tab-bq-costs")
        self.assertEqual(result[0].children, "48h")

    def test_stale_snapshot_chart_survives_empty_recent_history(self):
        latest = pd.DataFrame(
            [{"table_name": "stale_source", "source_rows": 10, "destination_rows": 10}]
        )
        with (
            patch.object(
                self.pipeline, "load_pipeline_health_summary", return_value=None
            ),
            patch.object(self.pipeline, "load_source_freshness", return_value=None),
            patch.object(
                self.pipeline,
                "load_table_ingestion_logs",
                side_effect=[pd.DataFrame(), latest],
            ),
        ):
            result = self.pipeline.update_pipeline_data("tab-table-ingestion")
        self.assertEqual(result[-1], [])
        self.assertEqual(len(result[-2].data), 2)
        self.assertEqual(list(result[-2].data[0].x), ["stale_source"])

    def test_layouts_have_flat_children_and_unique_ids(self):
        def walk(component, ids):
            if isinstance(component, (list, tuple)):
                for child in component:
                    self.assertNotIsInstance(child, (list, tuple))
                    walk(child, ids)
            elif hasattr(component, "to_plotly_json"):
                props = component.to_plotly_json()["props"]
                if props.get("id"):
                    self.assertNotIn(props["id"], ids)
                    ids.add(props["id"])
                walk(props.get("children"), ids)

        for name in ("overview", "customer_360", "pipeline_health"):
            with self.subTest(page=name):
                page = sys.modules[f"pages.{name}"]
                layout = page.layout() if callable(page.layout) else page.layout
                walk(layout, set())

    def test_ranked_products_respect_filters_and_limit(self):
        page = sys.modules["pages.overview"]
        df = pd.DataFrame(
            [
                dict(
                    product_name=f"P{i}",
                    order_date=pd.Timestamp("2025-01-15"),
                    category="Bikes",
                    country="PH",
                    quantity=i,
                    gross_sales_amount=i * 10,
                )
                for i in range(12)
            ]
        )
        filters = dict(
            start_date="2025-01-01",
            end_date="2025-12-31",
            category="Bikes",
            country="PH",
        )
        with patch.object(page, "get_prepared_dataset", return_value=df):
            rows = page.update_top_products(filters)
            self.assertEqual(len(rows), 10)
            self.assertEqual(rows[0], dict(product_name="P11", units=11, revenue=110))
            self.assertEqual(page.update_top_products(dict(filters, country="US")), [])

    def test_product_export_uses_selected_product_and_filters(self):
        page = sys.modules["pages.overview"]
        (df, *_), _ = self.load_sales(self.frames(["2025-01-15", "2025-02-15"]))
        filters = dict(
            start_date="2025-02-01",
            end_date="2025-02-28",
            category="ALL",
            country="ALL",
        )
        with patch.object(page, "get_prepared_dataset", return_value=df):
            result = page.export_selected_product_details(
                1, "Product Details: Bike", filters
            )
        self.assertIn("2025-02-15", result["content"])
        self.assertNotIn("2025-01-15", result["content"])
        self.assertTrue(result["filename"].endswith(".csv"))


if __name__ == "__main__":
    unittest.main()
