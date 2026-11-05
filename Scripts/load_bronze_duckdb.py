"""Load the raw source CSVs into the DuckDB bronze schema.

This replaces the retired SQL Server -> BigQuery bronze hop. The column types
mirror the original SQL Server bronze tables (Scripts/ddl_create_bronze_*.sql),
so the dbt models read the same values they read in the warehouse:

    CSV -> SQL Server (pandas to_sql) -> BigQuery (autodetect)

Numeric source columns become BIGINT/DOUBLE and every date-like column stays
VARCHAR, because the source systems stored dates as text and dbt casts them
in the silver layer.

Usage:
    python Scripts/load_bronze_duckdb.py
    python Scripts/load_bronze_duckdb.py --source data/raw --db analytics_layer/build/analytics.duckdb
    python Scripts/load_bronze_duckdb.py --fresh

Every load writes a manifest next to the DuckDB file. The manifest is the
replacement for the retired ``audit_metadata.table_ingestion_logs`` table: it
records the source row count, the loaded row count and the duration of every
table, which is what the dashboard's ingestion parity view reads.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from datetime import UTC, datetime
from typing import Any

import duckdb

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_ROOT / "data" / "raw"
DEFAULT_DB = REPO_ROOT / "analytics_layer" / "build" / "analytics.duckdb"
DEFAULT_MANIFEST = REPO_ROOT / "analytics_layer" / "build" / "bronze_manifest.json"

# (bronze table, csv relative path, column list)
BRONZE_TABLES = [
    (
        "crm_cust_info",
        "source_crm/cust_info.csv",
        "cst_id BIGINT, cst_key VARCHAR, cst_firstname VARCHAR, cst_lastname VARCHAR, "
        "cst_marital_status VARCHAR, cst_gndr VARCHAR, cst_create_date VARCHAR",
    ),
    (
        "crm_prd_info",
        "source_crm/prd_info.csv",
        "prd_id BIGINT, prd_key VARCHAR, prd_nm VARCHAR, prd_cost DOUBLE, "
        "prd_line VARCHAR, prd_start_dt VARCHAR, prd_end_dt VARCHAR",
    ),
    (
        "crm_sales_details",
        "source_crm/sales_details.csv",
        "sls_ord_num VARCHAR, sls_prd_key VARCHAR, sls_cust_id BIGINT, "
        "sls_order_dt BIGINT, sls_ship_dt BIGINT, sls_due_dt BIGINT, "
        "sls_sales DOUBLE, sls_quantity BIGINT, sls_price DOUBLE",
    ),
    (
        "erp_cust_az12",
        "source_erp/CUST_AZ12.csv",
        "cid VARCHAR, bdate VARCHAR, gen VARCHAR",
    ),
    (
        "erp_loc_a101",
        "source_erp/LOC_A101.csv",
        "cid VARCHAR, cntry VARCHAR",
    ),
    (
        "erp_px_cat_g1v2",
        "source_erp/PX_CAT_G1V2.csv",
        "id VARCHAR, cat VARCHAR, subcat VARCHAR, maintenance VARCHAR",
    ),
]


def _count(connection, table: str) -> int:
    result = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(result[0]) if result is not None else 0


def load_bronze(
    source_dir: pathlib.Path,
    db_path: pathlib.Path,
    fresh: bool,
    manifest_path: pathlib.Path | None = None,
) -> list[dict]:
    """Load every source CSV into the bronze schema and write the load manifest.

    The CSV is first materialised into a staging table so the source row count
    and the bronze row count are measured independently: the source count comes
    from the parsed CSV, the destination count from the typed bronze table.
    """
    if fresh:
        db_path.unlink(missing_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = duckdb.connect(str(db_path))
    connection.execute("CREATE SCHEMA IF NOT EXISTS bronze")

    tables: list[dict] = []

    for table, csv_relative, columns in BRONZE_TABLES:
        csv_path = source_dir / csv_relative
        entry: dict[str, Any] = {
            "table_name": table,
            "target_table": f"bronze.{table}",
            "source_file": csv_relative,
            "source_rows": 0,
            "destination_rows": 0,
            "duration_seconds": 0.0,
            "status": "error",
            "error_message": None,
        }

        if not csv_path.exists():
            entry["error_message"] = f"Missing source file: {csv_path}"
            tables.append(entry)
            continue

        started = time.perf_counter()
        try:
            connection.execute(f"CREATE OR REPLACE TABLE bronze.{table} ({columns})")
            # all_varchar keeps the raw text; the explicit column list then casts.
            connection.execute(
                f"""
                CREATE OR REPLACE TEMP TABLE staging AS
                SELECT * FROM read_csv(
                    '{csv_path.as_posix()}',
                    header = true,
                    all_varchar = true,
                    nullstr = ''
                )
                """
            )
            entry["source_rows"] = _count(connection, "staging")
            connection.execute(f"INSERT INTO bronze.{table} SELECT * FROM staging")
            entry["destination_rows"] = _count(connection, f"bronze.{table}")
            entry["status"] = "success"
        except Exception as exc:  # noqa: BLE001 - recorded per table in the manifest
            entry["error_message"] = str(exc)
        finally:
            entry["duration_seconds"] = round(time.perf_counter() - started, 4)

        tables.append(entry)
        print(
            f"  bronze.{table:22s} {entry['destination_rows']:>7,} rows"
            f"  ({entry['status']})"
        )

    connection.close()

    if manifest_path is not None:
        manifest = {
            "loaded_at": datetime.now(UTC).isoformat(),
            "source_directory": str(source_dir),
            "database": str(db_path),
            "tables": tables,
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"Wrote load manifest to {manifest_path}")

    return tables


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=pathlib.Path,
        default=DEFAULT_SOURCE,
        help="Folder holding source_crm/ and source_erp/ (default: data/raw)",
    )
    parser.add_argument(
        "--db",
        type=pathlib.Path,
        default=DEFAULT_DB,
        help="DuckDB file to write (default: analytics_layer/build/analytics.duckdb)",
    )
    parser.add_argument(
        "--manifest",
        type=pathlib.Path,
        default=DEFAULT_MANIFEST,
        help="Load manifest to write (default: analytics_layer/build/bronze_manifest.json)",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Delete the DuckDB file before loading instead of replacing tables",
    )
    args = parser.parse_args(argv)

    source_dir = args.source.expanduser().resolve()
    db_path = args.db.expanduser().resolve()
    manifest_path = args.manifest.expanduser().resolve()

    print(f"Loading bronze from {source_dir} into {db_path}")
    tables = load_bronze(source_dir, db_path, args.fresh, manifest_path)
    failures = [entry for entry in tables if entry["status"] != "success"]
    if failures:
        for entry in failures:
            print(f"ERROR: {entry['table_name']}: {entry['error_message']}")
        return 1
    print("Bronze load complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
