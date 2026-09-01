"""
Bronze-layer ingestion pipeline.

Walks a source folder, picks up every CSV, and loads it into the matching
table in the `bronze` schema. Table name is derived from the CSV filename
(strip extension), and the schema is inferred from the parent folder name
(`source_crm` -> crm, `source_erp` -> erp). Unknown folders fall back to
the folder slug as-is.

Required environment variables (loaded from .env or the shell):
    DB_SERVER        e.g. localhost
    DB_DATABASE      e.g. Demo_Database
    DB_USERNAME      e.g. sa
    DB_PASSWORD      the secret
    DB_DRIVER        e.g. ODBC Driver 18 for SQL Server  (optional, default shown)

Usage:
    python Scripts/ingest_bronze.py <source_folder>

If <source_folder> is omitted, SOURCE_FOLDER from the environment is used.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


# ----- Configuration --------------------------------------------------------

DEFAULT_DRIVER = "ODBC Driver 18 for SQL Server"
CHUNKSIZE = 10_000

# Folders under the source root that should be skipped.
SKIP_FOLDERS = {".DS_Store", "__pycache__"}

# Folders whose name maps to a short schema prefix used in the bronze table
# (e.g. source_crm/cust_info.csv -> bronze.crm_cust_info).
SCHEMA_PREFIX_MAP = {
    "source_crm": "crm",
    "source_erp": "erp",
}


# ----- Helpers --------------------------------------------------------------

def load_env(env_file: Path | None = None) -> None:
    """Best-effort .env loader. We keep this dependency-free so the script
    works on a clean `uv sync` without extra packages."""
    candidate = env_file or (Path.cwd() / ".env")
    if not candidate.exists():
        return
    for raw in candidate.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Don't clobber an existing env var (shell wins over .env).
        os.environ.setdefault(key, value)


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def build_engine() -> Engine:
    server = require_env("DB_SERVER")
    database = require_env("DB_DATABASE")
    username = require_env("DB_USERNAME")
    password = require_env("DB_PASSWORD")
    driver = os.environ.get("DB_DRIVER", DEFAULT_DRIVER)

    connection_string = (
        f"mssql+pyodbc://{username}:{password}@{server}/{database}?"
        f"driver={driver}&TrustServerCertificate=yes"
    )
    return create_engine(connection_string, pool_pre_ping=True, fast_executemany=True)


def verify_connection(engine: Engine) -> None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT DB_NAME() AS db, SUSER_SNAME() AS usr")
        ).fetchone()
    print(f"Connected to '{row.db}' as '{row.usr}'")


def schema_prefix_for(folder_name: str) -> str:
    """Return the bronze table prefix for a given source folder name."""
    return SCHEMA_PREFIX_MAP.get(folder_name, folder_name)


def discover_csvs(source_root: Path) -> Iterable[tuple[Path, str]]:
    """Yield (csv_path, target_table) pairs discovered under source_root."""
    if not source_root.is_dir():
        raise FileNotFoundError(f"Source folder not found: {source_root}")

    for folder in sorted(source_root.iterdir()):
        if not folder.is_dir() or folder.name in SKIP_FOLDERS:
            continue
        prefix = schema_prefix_for(folder.name)
        for csv_path in sorted(folder.glob("*.csv")):
            table = f"{prefix}_{csv_path.stem}".lower()
            yield csv_path, table


def ingest_csv(engine: Engine, csv_path: Path, schema: str, table: str) -> int:
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()

    # Re-runnable: TRUNCATE the target first so re-running the script doesn't
    # duplicate rows. Use an explicit autocommit transaction so the TRUNCATE
    # is visible to the subsequent bulk insert on the same engine.
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {schema}.{table}"))

    df.to_sql(
        name=table,
        con=engine,
        schema=schema,
        if_exists="append",
        index=False,
        chunksize=CHUNKSIZE,
    )
    return len(df)


def main(argv: list[str]) -> int:
    load_env()

    source_root = Path(argv[1]) if len(argv) > 1 else Path(
        os.environ.get("SOURCE_FOLDER", "")
    )
    if not source_root:
        print("Usage: python ingest_bronze.py <source_folder>", file=sys.stderr)
        return 2

    schema = "bronze"
    engine = build_engine()
    verify_connection(engine)

    pairs = list(discover_csvs(source_root))
    if not pairs:
        print(f"No CSVs found under {source_root}")
        return 0

    print(f"Found {len(pairs)} CSV file(s) under {source_root}")
    failures = 0
    for csv_path, table in pairs:
        try:
            rows = ingest_csv(engine, csv_path, schema, table)
            print(f"  ok   {csv_path.name:<30} -> {schema}.{table:<25} ({rows:,} rows)")
        except Exception as exc:  # noqa: BLE001 - log and continue
            failures += 1
            print(f"  FAIL {csv_path.name:<30} -> {schema}.{table:<25} ({exc})")

    print(f"Done. {len(pairs) - failures} succeeded, {failures} failed.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
