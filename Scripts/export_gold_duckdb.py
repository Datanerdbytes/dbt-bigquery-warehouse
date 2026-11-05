"""Export the gold schema into the standalone database file the app ships with.

The dbt build produces one DuckDB file with bronze, silver and gold schemas.
Only the gold tables are needed at runtime, and the app must run from a
read-only filesystem, so the shipped artifact is a separate file that holds
the gold tables alone.

Usage:
    python Scripts/export_gold_duckdb.py
    python Scripts/export_gold_duckdb.py --db analytics_layer/build/analytics.duckdb \
        --out my-dash-app/data/analytics.duckdb
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import duckdb

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "analytics_layer" / "build" / "analytics.duckdb"
DEFAULT_OUT = REPO_ROOT / "my-dash-app" / "data" / "analytics.duckdb"

GOLD_TABLES = ["fct_sales", "dim_products", "dim_customers", "product_360"]


def export_gold(db_path: pathlib.Path, out_path: pathlib.Path) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Build database not found: {db_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.unlink(missing_ok=True)

    connection = duckdb.connect(str(out_path))
    connection.execute(f"ATTACH '{db_path.as_posix()}' AS src (READ_ONLY)")
    connection.execute("CREATE SCHEMA gold")

    for table in GOLD_TABLES:
        connection.execute(
            f"CREATE TABLE gold.{table} AS SELECT * FROM src.gold.{table}"
        )
        result = connection.execute(f"SELECT COUNT(*) FROM gold.{table}").fetchone()
        rows = result[0] if result is not None else 0
        print(f"  gold.{table:18s} {rows:>7,} rows")

    connection.execute("DETACH src")
    connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=pathlib.Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    db_path = args.db.expanduser().resolve()
    out_path = args.out.expanduser().resolve()

    print(f"Exporting gold tables from {db_path} to {out_path}")
    export_gold(db_path, out_path)
    print(f"Wrote {out_path} ({out_path.stat().st_size / 1_000_000:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
