"""Offline regression checks: python -B -m unittest discover -s tests -v."""

import importlib
import json
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

import duckdb
import pandas as pd
from plotly.utils import PlotlyJSONEncoder

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "my-dash-app"))

import auth
import data_loader
import pipeline_telemetry
from components import header

from utils.cache import cache
from utils.helpers import dataframe_value, filter_dataframe

GOLD_DB = ROOT / "my-dash-app" / "data" / "analytics.duckdb"


class NetworkAccessForbidden(AssertionError):
    """Raised when a test tries to reach the network."""


def _forbid_network(*args, **kwargs):
    raise NetworkAccessForbidden("Network access is forbidden in offline tests")


class DashboardRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Importing the real app must never reach the network.
        with (
            patch.object(socket.socket, "connect", _forbid_network),
            patch.object(socket, "create_connection", _forbid_network),
            patch.object(cache, "init_app"),
        ):
            cls.dashboard = importlib.import_module("app")
        cache.init_app(cls.dashboard.server, config={"CACHE_TYPE": "SimpleCache"})
        cls.pipeline = sys.modules["pages.pipeline_health"]

    def setUp(self):
        for target, attribute in (
            (socket.socket, "connect"),
            (socket, "create_connection"),
        ):
            patcher = patch.object(target, attribute, _forbid_network)
            patcher.start()
            self.addCleanup(patcher.stop)
        cache.clear()

    def build_gold_database(self, sales, products, customers):
        """Write a temporary gold database shaped like the shipped artifact."""
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, True)
        path = Path(tmpdir) / "analytics.duckdb"

        connection = duckdb.connect(str(path))
        connection.execute("CREATE SCHEMA gold")
        for name, frame in (
            ("fct_sales", sales),
            ("dim_products", products),
            ("dim_customers", customers),
        ):
            if frame is None:
                frame = self.empty_frames()[
                    {
                        "fct_sales": 0,
                        "dim_products": 1,
                        "dim_customers": 2,
                    }[name]
                ]
            connection.register(f"{name}_frame", frame)
            connection.execute(
                f"CREATE TABLE gold.{name} AS SELECT * FROM {name}_frame"
            )
        connection.close()
        return path

    def load_sales(self, *frames):
        """Load the merged dataset from a temporary gold database."""
        if len(frames) == 1:
            sales, products, customers = frames[0]
        else:
            sales, products, customers = frames
        path = self.build_gold_database(sales, products, customers)
        with patch.object(data_loader, "gold_database_path", return_value=path):
            result = data_loader.load_and_prep_data.uncached()
        return result, path

    def write_telemetry(self, payload):
        """Write a temporary telemetry artifact and point the reader at it."""
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, True)
        path = Path(tmpdir) / "pipeline_telemetry.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        patcher = patch.object(pipeline_telemetry, "telemetry_path", return_value=path)
        patcher.start()
        self.addCleanup(patcher.stop)
        return path

    @staticmethod
    def frames(dates):
        sales = pd.DataFrame(
            {
                "sales_item_key": [f"s{index}" for index in range(len(dates))],
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
            [
                {
                    "product_key": "p1",
                    "product_name": "Bike",
                    "category": "bikes",
                    "cost": 5,
                }
            ]
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

    @staticmethod
    def empty_frames():
        empty_sales = pd.DataFrame(
            {
                "sales_item_key": pd.Series([], dtype="str"),
                "product_key": pd.Series([], dtype="str"),
                "customer_key": pd.Series([], dtype="str"),
                "order_date": pd.Series([], dtype="str"),
                "order_number": pd.Series([], dtype="str"),
                "quantity": pd.Series([], dtype="int64"),
                "gross_sales_amount": pd.Series([], dtype="float64"),
                "unit_price": pd.Series([], dtype="float64"),
            }
        )
        empty_products = pd.DataFrame(
            {
                "product_key": pd.Series([], dtype="str"),
                "product_name": pd.Series([], dtype="str"),
                "category": pd.Series([], dtype="str"),
                "cost": pd.Series([], dtype="float64"),
            }
        )
        empty_customers = pd.DataFrame(
            {
                "customer_key": pd.Series([], dtype="str"),
                "first_name": pd.Series([], dtype="str"),
                "last_name": pd.Series([], dtype="str"),
                "country": pd.Series([], dtype="str"),
            }
        )
        return empty_sales, empty_products, empty_customers

    def test_empty_sources_keep_expected_schema_and_no_dates(self):
        sales, products, customers = self.empty_frames()
        (df, start, end, categories, countries), _ = self.load_sales(
            sales, products, customers
        )
        self.assertTrue(df.empty)
        self.assertTrue(
            {"order_date", "product_name", "country", "gross_sales_amount"}
            <= set(df.columns)
        )
        self.assertIsNone(start)
        self.assertIsNone(end)
        self.assertEqual(categories, [{"label": "All Categories", "value": "ALL"}])
        self.assertEqual(countries, [{"label": "All Countries", "value": "ALL"}])

    def test_invalid_and_excluded_dates_do_not_crash(self):
        (df, start, end, *_), _ = self.load_sales(
            self.frames(["2009-12-31", None, "bad-date"])
        )
        self.assertTrue(df.empty)
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_valid_sales_keep_joins_and_totals(self):
        (df, start, end, categories, _), _ = self.load_sales(
            self.frames(["2010-01-01", "2026-09-01"])
        )
        self.assertEqual(df["gross_sales_amount"].sum(), 40)
        self.assertEqual(list(df["product_name"]), ["Bike", "Bike"])
        self.assertEqual((start, end), ("2010-01-01", "2026-09-01"))
        self.assertEqual(categories[-1]["value"], "bikes")
        self.assertEqual(list(df["country"]), ["PH", "PH"])

    def test_decimal_amounts_are_normalized_to_float64(self):
        sales, products, customers = self.frames(["2026-09-01", "2026-09-02"])
        sales["gross_sales_amount"] = [Decimal("10.50"), Decimal("20.25")]
        sales["unit_price"] = [Decimal("5.25"), Decimal("10.125")]
        products["cost"] = [Decimal("2.75")]
        (df, *_), _ = self.load_sales((sales, products, customers))

        self.assertEqual(df["gross_sales_amount"].dtype, "float64")
        self.assertEqual(df["unit_price"].dtype, "float64")
        self.assertEqual(df["gross_sales_amount"].sum(), 30.75)
        self.assertEqual(df["unit_price"].sum(), 15.375)
        self.assertEqual(df["cost"].dtype, "float64")
        self.assertEqual(list(df["cost"]), [2.75, 2.75])

    def test_non_numeric_amounts_become_nan_not_strings(self):
        sales, products, customers = self.frames(["2026-09-01"])
        sales["gross_sales_amount"] = [None]
        sales["unit_price"] = ["not-a-number"]
        (df, *_), _ = self.load_sales((sales, products, customers))

        self.assertEqual(df["gross_sales_amount"].dtype, "float64")
        self.assertEqual(df["unit_price"].dtype, "float64")
        self.assertTrue(df["gross_sales_amount"].isna().all())
        self.assertTrue(df["unit_price"].isna().all())

    def test_missing_dimensions_do_not_discard_sales(self):
        sales, _, _ = self.frames(["2026-09-01"])
        (df, *_), _ = self.load_sales((sales, None, None))
        self.assertEqual(len(df), 1)
        self.assertTrue(df["category"].isna().all())

    def test_loader_reads_the_bundled_gold_database(self):
        (df, start, end, categories, countries), path = self.load_sales(
            *self.frames(["2026-09-01"])
        )
        self.assertEqual(len(df), 1)
        self.assertTrue(path.exists())

        bundled = data_loader.load_and_prep_data.uncached()
        self.assertFalse(bundled[0].empty)
        self.assertEqual(bundled[0]["gross_sales_amount"].dtype, "float64")
        self.assertTrue(set(data_loader.MERGED_COLUMNS) <= set(bundled[0].columns))
        self.assertTrue(bundled[1] <= bundled[2])
        self.assertTrue(bundled[3][0]["value"] == "ALL")
        self.assertTrue(bundled[4][0]["value"] == "ALL")

    def test_missing_gold_database_reports_a_clear_error(self):
        with patch.object(
            data_loader,
            "gold_database_path",
            return_value=Path("/nonexistent/gold.duckdb"),
        ):
            with self.assertRaises(FileNotFoundError):
                data_loader.load_and_prep_data.uncached()

    def test_prepared_dataset_reuses_one_frame_per_ttl_window(self):
        loader = Mock(side_effect=lambda limit=None: (pd.DataFrame({"a": [1]}),) * 5)
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
                key=(None,) if expired else None,
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

            def load(limit=None):
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
            loader.assert_called_once_with(limit=None)

    def test_prepared_dataset_reloads_for_a_different_limit(self):
        frame = pd.DataFrame({"a": [1, 2, 3, 4, 5]})
        loader = Mock(side_effect=lambda limit=None: (frame.head(limit),) * 5)
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
        self.write_telemetry(self.telemetry_payload())
        rows = self.ingestion_rows()
        self.write_telemetry(self.telemetry_payload(rows))

        frame = data_loader.load_table_ingestion_logs.uncached(days_back=7, limit=1)
        self.assertEqual(len(frame), 1)
        self.assertIn("source_rows", frame.columns)
        self.assertIn("destination_rows", frame.columns)

    def test_ingestion_query_rejects_invalid_bounds_before_fetch(self):
        for kwargs in [
            {"days_back": 0},
            {"days_back": 366},
            {"limit": 0},
            {"limit": 1001},
            {"limit": "1; DROP"},
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                data_loader.load_table_ingestion_logs.uncached(**kwargs)

    def test_latest_ingestion_snapshot_is_independent_of_history_window(self):
        self.write_telemetry(self.telemetry_payload(self.ingestion_rows()))

        frame = data_loader.load_table_ingestion_logs.uncached(latest_only=True)
        self.assertEqual(len(frame), 2)
        self.assertEqual(
            set(frame["target_table"]), {"bronze.crm_cust_info", "bronze.erp_cust_az12"}
        )

    def test_cache_separates_history_parameters_and_latest_snapshot(self):
        self.write_telemetry(self.telemetry_payload(self.ingestion_rows()))
        with patch.object(
            data_loader,
            "ingestion_logs_frame",
            side_effect=lambda **kwargs: pd.DataFrame(),
        ) as loader:
            data_loader.load_table_ingestion_logs(days_back=7, limit=10)
            data_loader.load_table_ingestion_logs(days_back=7, limit=10)
            data_loader.load_table_ingestion_logs(days_back=14, limit=10)
            data_loader.load_table_ingestion_logs(latest_only=True)
        self.assertEqual(loader.call_count, 3)

    def test_source_freshness_uses_latest_successful_load_per_source(self):
        self.write_telemetry(self.telemetry_payload(self.ingestion_rows()))

        frame = data_loader.load_source_freshness.uncached()
        self.assertEqual(
            set(frame["target_table"]), {"bronze.crm_cust_info", "bronze.erp_cust_az12"}
        )
        self.assertIn("hours_since_load", frame.columns)
        self.assertIn("minutes_since_load", frame.columns)
        self.assertTrue((frame["hours_since_load"] >= 0).all())

    def test_missing_telemetry_artifact_degrades_to_empty_frames(self):
        self.write_telemetry({})
        self.assertTrue(data_loader.load_pipeline_health_summary.uncached().empty)
        self.assertTrue(data_loader.load_model_coverage_details.uncached().empty)
        self.assertTrue(data_loader.load_column_coverage_details.uncached().empty)
        self.assertTrue(data_loader.load_source_freshness.uncached().empty)
        self.assertTrue(data_loader.load_dbt_execution_logs.uncached().empty)
        self.assertTrue(data_loader.load_table_ingestion_logs.uncached().empty)

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
            patch.object(
                self.pipeline,
                "load_model_coverage_details",
                return_value=pd.DataFrame(),
            ),
        ):
            result = self.pipeline.update_pipeline_data("tab-model-coverage")
        self.assertEqual(result[0].children, "N/A")
        self.assertEqual(result[1].children, "N/A")
        self.assertEqual(result[2].children, "0")
        self.assertIs(result[12], header.no_update)

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
            patch.object(
                self.pipeline,
                "load_model_coverage_details",
                return_value=pd.DataFrame(),
            ),
        ):
            result = self.pipeline.update_pipeline_data("tab-model-coverage")
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

    @staticmethod
    def ingestion_rows():
        """Two loads of the same table plus one load of a second table.

        The timestamps are relative to now so the ``days_back`` window in the
        reader stays observable regardless of when the suite runs.
        """
        now = datetime.now(UTC)
        old = (now - timedelta(days=20)).isoformat()
        recent = (now - timedelta(days=2)).isoformat()
        recent_later = (now - timedelta(days=1)).isoformat()
        return [
            {
                "log_id": "1",
                "run_timestamp": old,
                "resource_type": "csv_to_duckdb",
                "table_name": "source_crm/cust_info.csv",
                "target_table": "bronze.crm_cust_info",
                "source_rows": 100,
                "destination_rows": 100,
                "rows_inserted": 100,
                "duration_seconds": 0.5,
                "status": "success",
                "error_message": None,
            },
            {
                "log_id": "2",
                "run_timestamp": recent,
                "resource_type": "csv_to_duckdb",
                "table_name": "source_crm/cust_info.csv",
                "target_table": "bronze.crm_cust_info",
                "source_rows": 120,
                "destination_rows": 120,
                "rows_inserted": 120,
                "duration_seconds": 0.6,
                "status": "success",
                "error_message": None,
            },
            {
                "log_id": "3",
                "run_timestamp": recent_later,
                "resource_type": "csv_to_duckdb",
                "table_name": "source_erp/CUST_AZ12.csv",
                "target_table": "bronze.erp_cust_az12",
                "source_rows": 50,
                "destination_rows": 50,
                "rows_inserted": 50,
                "duration_seconds": 0.2,
                "status": "success",
                "error_message": None,
            },
        ]

    @staticmethod
    def find_component(component, component_id):
        """Return the props of the component carrying ``component_id``."""
        if isinstance(component, (list, tuple)):
            for child in component:
                found = DashboardRegressionTests.find_component(child, component_id)
                if found is not None:
                    return found
            return None
        if not hasattr(component, "to_plotly_json"):
            return None
        props = component.to_plotly_json()["props"]
        if props.get("id") == component_id:
            return props
        return DashboardRegressionTests.find_component(
            props.get("children"), component_id
        )

    def test_placeholder_filter_bar_publishes_no_date_window(self):
        """The bar rendered before the dataset loads must not select a window.

        The selected range reaches every reader of the shared filter store, so a
        placeholder window outside the dataset blanks the whole dashboard.
        """
        from components.filter_bar import create_filter_bar

        props = self.find_component(
            create_filter_bar(
                pd.DataFrame(),
                date_picker_id="date-picker-range",
                category_dropdown_id="category-dropdown",
                country_dropdown_id="country-dropdown",
            ),
            "date-picker-range",
        )
        self.assertIsNotNone(props)
        self.assertIsNone(props["start_date"])
        self.assertIsNone(props["end_date"])

    def test_filter_store_writers_skip_an_incomplete_date_window(self):
        overview = sys.modules["pages.overview"]
        customer = sys.modules["pages.customer_360"]

        self.assertIs(
            overview.update_filter_store(None, None, "ALL", "ALL"),
            overview.no_update,
        )
        self.assertIs(
            overview.update_filter_store("2014-01-01", None, "ALL", "ALL"),
            overview.no_update,
        )
        self.assertIs(
            customer.sync_c360_filters_to_store(None, None, "ALL", "ALL"),
            customer.no_update,
        )
        self.assertEqual(
            overview.update_filter_store("2014-01-01", "2014-01-28", "ALL", "ALL"),
            dict(
                start_date="2014-01-01",
                end_date="2014-01-28",
                category="ALL",
                country="ALL",
            ),
        )

    def test_store_readers_ignore_a_filter_without_a_date_range(self):
        """A dateless filter must leave every panel untouched."""
        overview = sys.modules["pages.overview"]
        customer = sys.modules["pages.customer_360"]
        dateless = dict(start_date=None, end_date=None, category="ALL", country="ALL")

        with patch.object(
            overview,
            "get_prepared_dataset",
            side_effect=AssertionError("dataset must not be read"),
        ):
            self.assertEqual(
                overview.update_all_kpis(dateless), (overview.no_update,) * 20
            )
            self.assertIs(overview.update_sales_trend(dateless), overview.no_update)
            self.assertEqual(
                overview.update_category_pie(dateless), (overview.no_update,) * 5
            )
            self.assertIs(overview.update_top_products(dateless), overview.no_update)
            self.assertIs(overview.update_regional_sales(dateless), overview.no_update)

        with patch.object(
            customer,
            "get_prepared_dataset",
            side_effect=AssertionError("dataset must not be read"),
        ):
            self.assertEqual(
                customer.update_customer_kpis(dateless), (customer.no_update,) * 20
            )
            self.assertIs(customer.update_rfm_segments(dateless), customer.no_update)
            self.assertIs(
                customer.update_spend_distribution(dateless), customer.no_update
            )
            self.assertIs(
                customer.update_top_customers_table(dateless), customer.no_update
            )
            self.assertIs(customer.update_customer_trend(dateless), customer.no_update)

    @staticmethod
    def source_freshness_rows(ingestion_rows):
        """Newest successful load per target table."""
        latest: dict = {}
        for row in ingestion_rows:
            if row.get("status") != "success":
                continue
            target = row["target_table"]
            current = latest.get(target)
            if current is None or row["run_timestamp"] > current["last_loaded"]:
                latest[target] = {
                    "source_table": row["table_name"],
                    "target_table": target,
                    "last_loaded": row["run_timestamp"],
                }
        return list(latest.values())

    @classmethod
    def telemetry_payload(cls, ingestion_rows=None):
        rows = ingestion_rows or []
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "summary": {
                "last_dbt_run": datetime.now(UTC).isoformat(),
                "passed_tests": 10,
                "failed_tests": 0,
                "warning_tests": 0,
                "overall_system_status": "HEALTHY",
            },
            "execution_logs": [],
            "model_coverage": [],
            "column_coverage": [],
            "source_freshness": cls.source_freshness_rows(rows),
            "ingestion_logs": rows,
        }


if __name__ == "__main__":
    unittest.main()
