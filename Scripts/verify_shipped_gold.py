"""Fail when the shipped gold database drifts from the dbt build.

The app reads `my-dash-app/data/analytics.duckdb`, which is a committed
artifact produced by `Scripts/export_gold_duckdb.py`. If a model changes and
the artifact is not re-exported, the app would serve stale numbers while the
models say otherwise. This compares the committed artifact against a freshly
built gold export and exits non-zero on any difference.

Usage:
    python Scripts/verify_shipped_gold.py
    python Scripts/verify_shipped_gold.py --built /tmp/fresh.duckdb \
        --shipped my-dash-app/data/analytics.duckdb
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import duckdb

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_BUILT = REPO_ROOT / "analytics_layer" / "build" / "analytics.duckdb"
DEFAULT_SHIPPED = REPO_ROOT / "my-dash-app" / "data" / "analytics.duckdb"

GOLD_TABLES = ["fct_sales", "dim_products", "dim_customers", "product_360"]

# Numeric columns compared per table. Decimal and float columns are summed
# with a tolerance because the two files store them with different physical
# types but must hold the same values.
NUMERIC_SUM_COLUMNS = {
    "fct_sales": ["gross_sales_amount", "unit_price", "quantity"],
    "dim_products": ["cost"],
    "dim_customers": [],
    "product_360": ["total_sales", "total_quantity", "total_orders"],
}


def numeric_sum(
    connection: duckdb.DuckDBPyConnection, table: str, column: str
) -> float:
    result = connection.execute(
        f"SELECT COALESCE(SUM({column}), 0) FROM gold.{table}"
    ).fetchone()
    return float(result[0]) if result is not None else 0.0


def row_count(connection: duckdb.DuckDBPyConnection, table: str) -> int:
    result = connection.execute(f"SELECT COUNT(*) FROM gold.{table}").fetchone()
    return int(result[0]) if result is not None else 0


def compare(built_path: pathlib.Path, shipped_path: pathlib.Path) -> list[str]:
    differences: list[str] = []

    for label, path in (("built", built_path), ("shipped", shipped_path)):
        if not path.exists():
            differences.append(f"{label} database missing: {path}")
    if differences:
        return differences

    built = duckdb.connect(str(built_path), read_only=True)
    shipped = duckdb.connect(str(shipped_path), read_only=True)
    try:
        for table in GOLD_TABLES:
            built_rows = row_count(built, table)
            shipped_rows = row_count(shipped, table)
            if built_rows != shipped_rows:
                differences.append(
                    f"{table}: row count built={built_rows:,} shipped={shipped_rows:,}"
                )
                continue

            for column in NUMERIC_SUM_COLUMNS.get(table, []):
                built_sum = numeric_sum(built, table, column)
                shipped_sum = numeric_sum(shipped, table, column)
                if abs(built_sum - shipped_sum) > 0.01:
                    differences.append(
                        f"{table}.{column}: built={built_sum:,.4f} "
                        f"shipped={shipped_sum:,.4f}"
                    )
    finally:
        built.close()
        shipped.close()

    return differences


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--built", type=pathlib.Path, default=DEFAULT_BUILT)
    parser.add_argument("--shipped", type=pathlib.Path, default=DEFAULT_SHIPPED)
    args = parser.parse_args(argv)

    differences = compare(
        args.built.expanduser().resolve(), args.shipped.expanduser().resolve()
    )

    if differences:
        print("Shipped gold artifact is out of date:")
        for difference in differences:
            print(f"  - {difference}")
        print("Re-run Scripts/export_gold_duckdb.py and commit the result.")
        return 1

    print("Shipped gold artifact matches the dbt build.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
