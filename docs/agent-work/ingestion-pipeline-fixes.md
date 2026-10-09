# Ingestion Pipeline Fixes — Task Plan

**Batch ID:** `ingestion-pipeline-fixes`
**Base Branch:** `integration` (commit TBD)
**Created:** 2026-10-09
**Owner:** Coordinator

---

## Objective

Fix all identified issues across the three data ingestion scripts (`ingest_bronze.py`, `ingest_bigquery.py`, `ingest_dbt_artifacts.py`) and supporting infrastructure (`run_pipeline.sh`, `.env.example`, logging utilities) to make the pipeline reliable, testable, and maintainable.

---

## Acceptance Criteria

1. **Driver consistency**: All scripts use SQL Server (ODBC Driver 18) via `mssql+pyodbc` — no `postgresql+psycopg2` references remain
2. **Import safety**: No I/O, credential validation, or client initialization at module level in any ingestion script
3. **Unified audit logging**: Single audit logging pattern via `utils.audit_logger` used everywhere
4. **Configurable paths**: `run_pipeline.sh` uses environment variables, not hardcoded `/Users/roelsomido/Source`
5. **Complete env vars**: `.env.example` documents all required variables (`SOURCE_FOLDER`, `TARGET_DATASET`, etc.)
6. **Retry/backoff**: Transient failures in `ingest_bronze.py` handled with exponential backoff
7. **Modern datetime**: `datetime.utcnow()` replaced with `datetime.now(timezone.utc)` in `ingest_dbt_artifacts.py`
8. **Test coverage**: Offline regression tests for all three scripts under `tests/`
9. **CI passes**: Full test suite (`.venv/bin/python -B -m unittest discover -s tests -v`) and pre-commit hooks pass

---

## Task Breakdown

| Task ID | Title | Owner | Branch | Base SHA | Status |
|---------|-------|-------|--------|----------|--------|
| T01 | Fix driver mismatch & add retry in `ingest_bronze.py` | Worker A | `agent/ingestion-pipeline-fixes/T01-driver-retry` | `<integration-sha>` | planned |
| T02 | Remove import-time side effects in `ingest_bigquery.py` | Worker B | `agent/ingestion-pipeline-fixes/T02-import-safety-bq` | `<integration-sha>` | planned |
| T03 | Remove import-time side effects & fix datetime in `ingest_dbt_artifacts.py` | Worker C | `agent/ingestion-pipeline-fixes/T03-import-safety-dbt` | `<integration-sha>` | planned |
| T04 | Unify audit logging in `utils/audit_logger.py` and all scripts | Worker D | `agent/ingestion-pipeline-fixes/T04-audit-logging` | `<integration-sha>` | planned |
| T05 | Fix hardcoded paths in `run_pipeline.sh` | Worker A | `agent/ingestion-pipeline-fixes/T05-run-pipeline-paths` | `<integration-sha>` (after T01) | planned |
| T06 | Add missing env vars to `.env.example` | Worker A | `agent/ingestion-pipeline-fixes/T06-env-vars` | `<integration-sha>` (after T01) | planned |
| T07 | Add regression tests for `ingest_bronze.py` | Worker A | `agent/ingestion-pipeline-fixes/T07-tests-bronze` | `<integration-sha>` (after T01, T04) | planned |
| T08 | Add regression tests for `ingest_bigquery.py` | Worker B | `agent/ingestion-pipeline-fixes/T08-tests-bq` | `<integration-sha>` (after T02, T04) | planned |
| T09 | Add regression tests for `ingest_dbt_artifacts.py` | Worker C | `agent/ingestion-pipeline-fixes/T09-tests-dbt` | `<integration-sha>` (after T03, T04) | planned |

---

## Dependency Graph

```
T01 ──────┬──→ T05 ──→ T07
          │
          └──→ T06 ──→ T07
T02 ─────────────────→ T08
T03 ─────────────────→ T09
T04 ─────────────────┬──→ T07
                     ├─→ T08
                     └─→ T09
```

**Integration order**: T01, T02, T03, T04 (parallel, no deps) → T05, T06 (depend on T01) → T07, T08, T09 (depend on T04 + respective script fix)

---

## Task Details

### T01: Fix driver mismatch & add retry in `ingest_bronze.py`
**Branch:** `agent/ingestion-pipeline-fixes/T01-driver-retry`
**Owned paths:** `Scripts/ingest_bronze.py`, `tests/test_ingest_bronze.py` (new)
**Allowed shared edits:** None
**Out of scope:** `ingest_bigquery.py`, `ingest_dbt_artifacts.py`
**Dependencies:** None
**Interface contract:**
- `get_engine()` returns SQLAlchemy engine using `mssql+pyodbc://` with ODBC Driver 18
- `insert_rows()` accepts `engine`, `table`, `rows`, `batch_size` — returns `(inserted_count, errors)`
- `main()` reads `SOURCE_FOLDER`, `DB_CONNECTION_STRING` from env
**Required checks:**
- Unit tests mock `create_engine`, verify retry/backoff on `OperationalError`
- `black Scripts/ingest_bronze.py` passes
- No `postgresql` or `psycopg2` strings in file

---

### T02: Remove import-time side effects in `ingest_bigquery.py`
**Branch:** `agent/ingestion-pipeline-fixes/T02-import-safety-bq`
**Owned paths:** `Scripts/ingest_bigquery.py`, `tests/test_ingest_bigquery.py` (new)
**Allowed shared edits:** None
**Out of scope:** Other ingestion scripts
**Dependencies:** None
**Interface contract:**
- `get_bq_client()` returns `bigquery.Client` — called only inside functions
- `get_source_engine()` returns SQLAlchemy engine — called only inside functions
- `TABLES` constant remains module-level (list of table names)
- `main()` orchestrates: reads env, creates clients, runs extraction per table
**Required checks:**
- Importing module does not create BigQuery client or SQLAlchemy engine
- Unit tests patch `get_bq_client` and `get_source_engine`
- `black Scripts/ingest_bigquery.py` passes

---

### T03: Remove import-time side effects & fix datetime in `ingest_dbt_artifacts.py`
**Branch:** `agent/ingestion-pipeline-fixes/T03-import-safety-dbt`
**Owned paths:** `Scripts/ingest_dbt_artifacts.py`, `tests/test_ingest_dbt_artifacts.py` (new)
**Allowed shared edits:** None
**Out of scope:** Other ingestion scripts
**Dependencies:** None
**Interface contract:**
- `get_bq_client()` returns `bigquery.Client` — called only inside functions
- `load_run_results(path)` parses `run_results.json` — pure function
- `transform_run_results(data)` returns list of dicts for BigQuery insert — pure function
- `main()` reads `DBT_ARTIFACTS_PATH`, `TARGET_PROJECT`, `TARGET_DATASET` from env
- All `datetime.utcnow()` → `datetime.now(timezone.utc)`
**Required checks:**
- Importing module does not create BigQuery client
- Unit tests patch `get_bq_client`, verify transform output schema
- `black Scripts/ingest_dbt_artifacts.py` passes

---

### T04: Unify audit logging
**Branch:** `agent/ingestion-pipeline-fixes/T04-audit-logging`
**Owned paths:** `utils/audit_logger.py`, `utils/__init__.py` (re-export), `Scripts/ingest_bronze.py`, `Scripts/ingest_bigquery.py`, `Scripts/ingest_dbt_artifacts.py`
**Allowed shared edits:** All three scripts (coordinated via this task)
**Out of scope:** `utils/logging_config.py` (keep as-is for app logging)
**Dependencies:** None
**Interface contract:**
- `utils.audit_logger.AuditLogger` class with methods: `log_start(script, params)`, `log_success(script, stats)`, `log_failure(script, error, params)`
- All three scripts import: `from utils.audit_logger import AuditLogger`
- Each script instantiates `AuditLogger()` in `main()` and logs start/success/failure
- Log format: JSON lines with `timestamp`, `script`, `event`, `details`
**Required checks:**
- All three scripts use `AuditLogger` (grep confirms)
- No direct `audit_logger.info()` or `logger.info()` for audit events in scripts
- `black utils/audit_logger.py Scripts/*.py` passes

---

### T05: Fix hardcoded paths in `run_pipeline.sh`
**Branch:** `agent/ingestion-pipeline-fixes/T05-run-pipeline-paths`
**Owned paths:** `run_pipeline.sh`
**Allowed shared edits:** None
**Out of scope:** Ingestion scripts
**Dependencies:** T01 (must know final env var names)
**Interface contract:**
- `SOURCE_FOLDER` env var used instead of `/Users/roelsomido/Source`
- `DBT_PROJECT_DIR` env var for `analytics_layer` path (default: `./analytics_layer`)
- Script validates required env vars at start, exits with clear error if missing
- All `cd` commands use variables
**Required checks:**
- `shellcheck run_pipeline.sh` passes
- Script runs with `SOURCE_FOLDER=/tmp/test DBT_PROJECT_DIR=./analytics_layer bash run_pipeline.sh` (dry-run mode if available)

---

### T06: Add missing env vars to `.env.example`
**Branch:** `agent/ingestion-pipeline-fixes/T06-env-vars`
**Owned paths:** `.env.example`
**Allowed shared edits:** None
**Out of scope:** Ingestion scripts, `run_pipeline.sh`
**Dependencies:** T01 (confirms required vars)
**Interface contract:**
- Documents: `SOURCE_FOLDER`, `DB_CONNECTION_STRING`, `DBT_ARTIFACTS_PATH`, `TARGET_PROJECT`, `TARGET_DATASET`, `DBT_PROJECT_DIR`
- Each var has comment with description and example
- No actual secrets in file
**Required checks:**
- `grep -E 'SOURCE_FOLDER|DB_CONNECTION_STRING|DBT_ARTIFACTS_PATH|TARGET_PROJECT|TARGET_DATASET|DBT_PROJECT_DIR' .env.example` returns all 6

---

### T07: Add regression tests for `ingest_bronze.py`
**Branch:** `agent/ingestion-pipeline-fixes/T07-tests-bronze`
**Owned paths:** `tests/test_ingest_bronze.py`
**Allowed shared edits:** None
**Out of scope:** Other test files
**Dependencies:** T01, T04
**Required checks:**
- Tests mock `create_engine`, `AuditLogger`
- Verify retry logic with `side_effect` raising `OperationalError` then succeeding
- Verify audit log calls on start/success/failure
- Run: `.venv/bin/python -B -m unittest tests.test_ingest_bronze -v`

---

### T08: Add regression tests for `ingest_bigquery.py`
**Branch:** `agent/ingestion-pipeline-fixes/T08-tests-bq`
**Owned paths:** `tests/test_ingest_bigquery.py`
**Allowed shared edits:** None
**Out of scope:** Other test files
**Dependencies:** T02, T04
**Required checks:**
- Tests patch `get_bq_client`, `get_source_engine`, `AuditLogger`
- Verify no client creation at import time
- Verify per-table extraction logic
- Run: `.venv/bin/python -B -m unittest tests.test_ingest_bigquery -v`

---

### T09: Add regression tests for `ingest_dbt_artifacts.py`
**Branch:** `agent/ingestion-pipeline-fixes/T09-tests-dbt`
**Owned paths:** `tests/test_ingest_dbt_artifacts.py`
**Allowed shared edits:** None
**Out of scope:** Other test files
**Dependencies:** T03, T04
**Required checks:**
- Tests patch `get_bq_client`, `AuditLogger`
- Verify `transform_run_results` output schema matches BigQuery table
- Verify `datetime.now(timezone.utc)` used (no `utcnow()`)
- Run: `.venv/bin/python -B -m unittest tests.test_ingest_dbt_artifacts -v`

---

## Shared Contracts (Cross-Task)

| Contract | Owner | Consumers | Status |
|----------|-------|-----------|--------|
| `utils.audit_logger.AuditLogger` API | T04 | T01, T02, T03, T07, T08, T09 | Defined in T04 |
| Env var names (`SOURCE_FOLDER`, etc.) | T01, T06 | T05, T06, all scripts | T01 defines, T06 documents |
| SQL Server connection string format | T01 | T05 (validation) | `mssql+pyodbc://user:pass@host/db?driver=ODBC+Driver+18+for+SQL+Server` |

---

## Verification Gate (Run on Integration Candidate)

```bash
# 1. Full offline Python test suite
.venv/bin/python -B -m unittest discover -s tests -v

# 2. Pre-commit hooks (includes black, detect-secrets, dbt-checkpoint)
.venv/bin/python -m pre_commit run --all-files

# 3. Shellcheck on pipeline script
shellcheck run_pipeline.sh

# 4. Verify no postgres references in ingestion scripts
grep -r "postgresql\|psycopg2" Scripts/ingest_*.py && echo "FAIL: postgres refs remain" || echo "OK"

# 5. Verify import safety
python -c "import Scripts.ingest_bigquery; import Scripts.ingest_dbt_artifacts" && echo "OK: no import-time I/O"

# 6. Verify audit logger usage
grep -r "AuditLogger" Scripts/ingest_*.py | wc -l  # expect 3 (one per script)

# 7. Verify env vars documented
grep -E 'SOURCE_FOLDER|DB_CONNECTION_STRING|DBT_ARTIFACTS_PATH|TARGET_PROJECT|TARGET_DATASET|DBT_PROJECT_DIR' .env.example | wc -l  # expect 6
```

All checks must pass before marking batch `integrated`.

---

## Rollback Considerations

- Each task commits to its own branch; integration uses merge (not squash) to preserve history
- Pre-merge SHA of `integration` recorded before each merge
- If verification fails: `git reset --hard <pre-merge-sha>` on `integration`, diagnose, re-merge
- Recovery refs: `refs/heads/recovery/ingestion-pipeline-fixes/<task-id>`

---

## Cleanup (After Successful Integration)

- Delete task branches (local and remote) after confirming `integration` contains all changes
- Preserve recovery refs for 30 days
- No external resources to clean up (no containers, caches, cloud resources created)
