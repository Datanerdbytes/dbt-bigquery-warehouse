"""Offline SQL lint rendering must preserve model expressions and fail closed."""

import unittest
from pathlib import Path
from unittest.mock import patch

from sqlfluff.core import FluffConfig, Linter

from sqlfluff_libs.dbt_utils import generate_surrogate_key

ROOT = Path(__file__).resolve().parents[1]


class SqlLintTests(unittest.TestCase):
    def test_surrogate_key_matches_bigquery_compiled_expression(self):
        # Expressions verified against the existing BigQuery-compiled dbt models.
        self.assertEqual(
            generate_surrogate_key(["c.cst_id"]),
            "to_hex(md5(cast(coalesce(cast(c.cst_id as string), "
            "'_dbt_utils_surrogate_key_null_') as string)))",
        )
        self.assertEqual(
            generate_surrogate_key(["s.sls_ord_num", "s.sls_prd_key"]),
            "to_hex(md5(cast(coalesce(cast(s.sls_ord_num as string), "
            "'_dbt_utils_surrogate_key_null_') || '-' || "
            "coalesce(cast(s.sls_prd_key as string), "
            "'_dbt_utils_surrogate_key_null_') as string)))",
        )

    def test_models_parse_without_warehouse_client(self):
        config = FluffConfig.from_path(str(ROOT))
        linter = Linter(config=config)
        with patch(
            "google.cloud.bigquery.Client",
            side_effect=AssertionError("warehouse access"),
        ):
            for path in sorted((ROOT / "analytics_layer/models").rglob("*.sql")):
                with self.subTest(model=path.name):
                    result = linter.parse_string(path.read_text(), fname=str(path))
                    self.assertEqual(result.violations, [])

    def test_unknown_macros_and_invalid_sql_are_still_errors(self):
        config = FluffConfig.from_path(str(ROOT))
        linter = Linter(config=config)
        missing_macro = linter.parse_string("SELECT {{ dbt_utils.unsupported() }}")
        self.assertTrue(
            any(item.rule_code() == "TMP" for item in missing_macro.violations)
        )
        invalid_sql = linter.parse_string("SELECT * FROM")
        self.assertTrue(
            any(item.rule_code() == "PRS" for item in invalid_sql.violations)
        )
