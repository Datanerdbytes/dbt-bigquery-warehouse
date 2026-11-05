"""Offline checks for the pipeline telemetry export and the shipped artifact.

The dbt build produces the same facts the retired BigQuery ``audit_metadata``
tables used to carry. ``Scripts/export_pipeline_telemetry.py`` folds them into
one JSON artifact; these tests pin the export rules and check that the
committed artifact still matches what the dashboard reader expects.
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "my-dash-app"))

import pipeline_telemetry


def _load_export_module():
    path = ROOT / "Scripts" / "export_pipeline_telemetry.py"
    spec = importlib.util.spec_from_file_location("export_pipeline_telemetry", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


export = _load_export_module()

TELEMETRY_PATH = ROOT / "my-dash-app" / "data" / "pipeline_telemetry.json"
GOLD_DB_PATH = ROOT / "my-dash-app" / "data" / "analytics.duckdb"

MANIFEST = {
    "nodes": {
        "model.analytics.dim_products": {
            "resource_type": "model",
            "name": "dim_products",
            "alias": "dim_products",
            "schema": "gold",
            "database": "analytics",
            "columns": {
                "product_key": {
                    "name": "product_key",
                    "description": "Surrogate key",
                    "data_type": "VARCHAR",
                },
                "category": {
                    "name": "category",
                    "description": "",
                    "data_type": "VARCHAR",
                },
            },
        },
        "test.analytics.not_null_dim_products_product_key": {
            "resource_type": "test",
            "name": "not_null_dim_products_product_key",
            "attached_node": "model.analytics.dim_products",
            "column_name": "product_key",
        },
        "test.analytics.source_unique_bronze_source_crm_cust_info_cst_id": {
            "resource_type": "test",
            "name": "source_unique_bronze_source_crm_cust_info_cst_id",
            "attached_node": None,
            "column_name": "cst_id",
            "test_metadata": {
                "name": "unique",
                "kwargs": {
                    "column_name": "cst_id",
                    "model": (
                        "{{ get_where_subquery(source('bronze_source', "
                        "'crm_cust_info')) }}"
                    ),
                },
                "namespace": None,
            },
        },
    },
    "sources": {
        "source.analytics.bronze_source.crm_cust_info": {
            "resource_type": "source",
            "source_name": "bronze_source",
            "name": "crm_cust_info",
            "identifier": "crm_cust_info",
            "schema": "bronze",
            "database": "analytics",
        }
    },
}

RUN_RESULTS = {
    "metadata": {
        "dbt_version": "1.9.0",
        "invocation_id": "run-1",
        "invocation_started_at": "2026-11-05T16:59:20Z",
        "generated_at": "2026-11-05T16:59:23Z",
    },
    "elapsed_time": 3.2,
    "results": [
        {
            "unique_id": "model.analytics.dim_products",
            "status": "success",
            "execution_time": 1.23456,
            "failures": None,
            "message": None,
        },
        {
            "unique_id": "test.analytics.not_null_dim_products_product_key",
            "status": "pass",
            "execution_time": 0.5,
            "failures": None,
            "message": None,
        },
        {
            "unique_id": "test.analytics.source_unique_bronze_source_crm_cust_info_cst_id",
            "status": "pass",
            "execution_time": 0.25,
            "failures": None,
            "message": None,
        },
    ],
}

BRONZE_MANIFEST = {
    "loaded_at": "2026-11-05T17:05:56+00:00",
    "source_directory": "/tmp/source",
    "database": "/tmp/bronze.duckdb",
    "tables": [
        {
            "source_file": "source_crm/cust_info.csv",
            "target_table": "bronze.crm_cust_info",
            "source_rows": 100,
            "destination_rows": 100,
            "duration_seconds": 0.07,
            "status": "success",
            "error_message": None,
        },
        {
            "source_file": "source_erp/CUST_AZ12.csv",
            "target_table": "bronze.erp_cust_az12",
            "source_rows": 50,
            "destination_rows": 49,
            "duration_seconds": 0.02,
            "status": "failed",
            "error_message": "row rejected",
        },
    ],
}


class ExportRulesTests(unittest.TestCase):
    def test_execution_logs_resolve_model_test_and_source_targets(self):
        rows = export.build_execution_logs(RUN_RESULTS, MANIFEST)
        targets = {row["node_name"]: row["target_table"] for row in rows}

        self.assertEqual(targets["dim_products"], "gold.dim_products")
        self.assertEqual(
            targets["not_null_dim_products_product_key"], "gold.dim_products"
        )
        self.assertEqual(
            targets["source_unique_bronze_source_crm_cust_info_cst_id"],
            "bronze.crm_cust_info",
        )

    def test_execution_logs_mirror_run_results_fields(self):
        rows = export.build_execution_logs(RUN_RESULTS, MANIFEST)
        model = next(row for row in rows if row["node_name"] == "dim_products")

        self.assertEqual(model["resource_type"], "model")
        self.assertEqual(model["execution_id"], "run-1")
        self.assertEqual(model["run_timestamp"], "2026-11-05T16:59:23Z")
        self.assertEqual(model["execution_time_seconds"], 1.23)
        self.assertEqual(model["rows_affected"], 0)
        self.assertEqual(model["status"], "success")

    def test_execution_logs_carry_failures_as_affected_rows(self):
        run_results = {
            "metadata": RUN_RESULTS["metadata"],
            "results": [
                {
                    "unique_id": "test.analytics.not_null_dim_products_product_key",
                    "status": "fail",
                    "execution_time": 0.1,
                    "failures": 3,
                    "message": "3 rows failed",
                }
            ],
        }
        rows = export.build_execution_logs(run_results, MANIFEST)
        self.assertEqual(rows[0]["rows_affected"], 3)
        self.assertEqual(rows[0]["error_message"], "3 rows failed")

    def test_coverage_rows_come_from_the_manifest(self):
        model_rows, column_rows = export.build_coverage(MANIFEST)

        self.assertEqual(len(model_rows), 1)
        self.assertEqual(model_rows[0]["model_name"], "dim_products")
        self.assertEqual(model_rows[0]["total_columns"], 2)
        self.assertEqual(model_rows[0]["columns_with_tests"], 1)
        self.assertEqual(model_rows[0]["column_coverage_pct"], 50.0)
        self.assertEqual(model_rows[0]["total_tests"], 1)

        self.assertEqual(len(column_rows), 2)
        tested = next(row for row in column_rows if row["column_name"] == "product_key")
        untested = next(row for row in column_rows if row["column_name"] == "category")
        self.assertTrue(tested["has_tests"])
        self.assertFalse(untested["has_tests"])

    def test_summary_status_follows_the_worst_test_result(self):
        model_rows, _ = export.build_coverage(MANIFEST)

        healthy = export.build_summary(RUN_RESULTS, model_rows)
        self.assertEqual(healthy["overall_system_status"], "HEALTHY")
        self.assertEqual(healthy["passed_tests"], 2)
        self.assertEqual(healthy["failed_tests"], 0)
        self.assertEqual(healthy["total_models"], 1)
        self.assertEqual(healthy["overall_column_coverage_pct"], 50.0)

        warned = export.build_summary(
            {
                "metadata": RUN_RESULTS["metadata"],
                "results": [
                    {
                        "unique_id": "test.analytics.not_null_dim_products_product_key",
                        "status": "warn",
                        "execution_time": 0.1,
                    }
                ],
            },
            model_rows,
        )
        self.assertEqual(warned["overall_system_status"], "WARNING")
        self.assertEqual(warned["warning_tests"], 1)

        failed = export.build_summary(
            {
                "metadata": RUN_RESULTS["metadata"],
                "results": [
                    {
                        "unique_id": "test.analytics.not_null_dim_products_product_key",
                        "status": "fail",
                        "execution_time": 0.1,
                    }
                ],
            },
            model_rows,
        )
        self.assertEqual(failed["overall_system_status"], "CRITICAL")
        self.assertEqual(failed["failed_tests"], 1)

    def test_ingestion_logs_carry_the_bronze_row_parity(self):
        rows = export.build_ingestion_logs(BRONZE_MANIFEST)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["resource_type"], "csv_to_duckdb")
        self.assertEqual(rows[0]["target_table"], "bronze.crm_cust_info")
        self.assertEqual(rows[0]["source_rows"], 100)
        self.assertEqual(rows[0]["destination_rows"], 100)
        self.assertEqual(rows[1]["status"], "failed")
        self.assertEqual(rows[1]["error_message"], "row rejected")

    def test_ingestion_history_keeps_the_newest_load_of_every_run(self):
        older = export.build_ingestion_logs(
            {
                "loaded_at": "2026-10-01T00:00:00+00:00",
                "tables": BRONZE_MANIFEST["tables"][:1],
            }
        )
        newer = export.build_ingestion_logs(BRONZE_MANIFEST)

        merged = export.merge_ingestion_history(older, newer)
        # One row per load: the same table loaded on two dates keeps both, the
        # newest run first.
        self.assertEqual(len(merged), 3)
        self.assertEqual(merged[0]["run_timestamp"], newer[0]["run_timestamp"])
        self.assertEqual(merged[-1]["run_timestamp"], older[0]["run_timestamp"])

        duplicated = export.merge_ingestion_history(newer, newer)
        self.assertEqual(len(duplicated), 2)

    def test_source_freshness_uses_the_newest_successful_load(self):
        rows = export.build_ingestion_logs(BRONZE_MANIFEST)
        freshness = export.build_source_freshness(rows)

        self.assertEqual(len(freshness), 1)
        self.assertEqual(freshness[0]["target_table"], "bronze.crm_cust_info")
        self.assertEqual(freshness[0]["source_table"], "source_crm/cust_info.csv")


class ShippedArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = json.loads(TELEMETRY_PATH.read_text(encoding="utf-8"))

    def test_artifact_has_every_section_the_reader_expects(self):
        for section in (
            "summary",
            "execution_logs",
            "model_coverage",
            "column_coverage",
            "source_freshness",
            "ingestion_logs",
        ):
            with self.subTest(section=section):
                self.assertIn(section, self.artifact)

    def test_artifact_sections_match_the_reader_columns(self):
        expected = {
            "execution_logs": pipeline_telemetry.EXECUTION_LOG_COLUMNS,
            "model_coverage": pipeline_telemetry.MODEL_COVERAGE_COLUMNS,
            "column_coverage": pipeline_telemetry.COLUMN_COVERAGE_COLUMNS,
            "ingestion_logs": pipeline_telemetry.INGESTION_COLUMNS,
        }
        for section, columns in expected.items():
            with self.subTest(section=section):
                rows = self.artifact[section]
                self.assertTrue(rows)
                for row in rows:
                    self.assertEqual(set(row), set(columns))

    def test_source_freshness_is_stored_without_the_computed_ages(self):
        # The ages are derived at read time, so the artifact only stores the
        # source, the target and the load timestamp.
        for row in self.artifact["source_freshness"]:
            with self.subTest(target=row["target_table"]):
                self.assertEqual(
                    set(row), {"source_table", "target_table", "last_loaded"}
                )
                self.assertLessEqual(
                    set(row), set(pipeline_telemetry.SOURCE_FRESHNESS_COLUMNS)
                )

    def test_every_execution_log_resolves_a_target_table(self):
        for row in self.artifact["execution_logs"]:
            with self.subTest(node=row["node_name"]):
                self.assertTrue(row["target_table"])

    def test_summary_counts_agree_with_the_coverage_rows(self):
        summary = self.artifact["summary"]
        model_rows = self.artifact["model_coverage"]

        self.assertEqual(summary["total_models"], len(model_rows))
        self.assertEqual(
            summary["total_columns"],
            sum(row["total_columns"] for row in model_rows),
        )
        self.assertEqual(
            summary["overall_column_coverage_pct"],
            round(
                sum(row["columns_with_tests"] for row in model_rows)
                / sum(row["total_columns"] for row in model_rows)
                * 100,
                2,
            ),
        )
        self.assertIn(
            summary["overall_system_status"],
            {"HEALTHY", "WARNING", "CRITICAL"},
        )

    def test_source_freshness_matches_the_ingestion_history(self):
        self.assertEqual(
            self.artifact["source_freshness"],
            export.build_source_freshness(self.artifact["ingestion_logs"]),
        )

    def test_reader_returns_frames_from_the_shipped_artifact(self):
        summary = pipeline_telemetry.summary_frame()
        self.assertEqual(len(summary), 1)
        self.assertEqual(
            summary.iloc[0]["overall_system_status"],
            self.artifact["summary"]["overall_system_status"],
        )
        self.assertFalse(pipeline_telemetry.execution_logs_frame().empty)
        self.assertFalse(pipeline_telemetry.model_coverage_frame().empty)
        self.assertFalse(pipeline_telemetry.column_coverage_frame().empty)
        self.assertFalse(pipeline_telemetry.source_freshness_frame().empty)
        self.assertFalse(pipeline_telemetry.ingestion_logs_frame().empty)

    def test_bundled_gold_database_holds_the_dashboard_tables(self):
        import duckdb

        connection = duckdb.connect(str(GOLD_DB_PATH), read_only=True)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'gold'"
                ).fetchall()
            }
            rows = connection.execute("SELECT COUNT(*) FROM gold.fct_sales").fetchone()[
                0
            ]
        finally:
            connection.close()

        self.assertLessEqual({"fct_sales", "dim_products", "dim_customers"}, tables)
        self.assertGreater(rows, 0)


if __name__ == "__main__":
    unittest.main()
