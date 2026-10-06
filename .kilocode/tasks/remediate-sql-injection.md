# Task: Remediate SQL Injection via Unquoted Table Name Interpolation

## Context & Issue Description
The pipeline constructs dynamic SQL statements by directly interpolating unquoted directory listing inputs into query strings (e.g., `f"SELECT * FROM bronze.{table_name}"`). If an external attacker or unprivileged process gains control over directory contents or naming schemas, they can inject malicious SQL fragments to bypass security barriers.

## Target Project Assets
- **Data Ingestion Script:** `Scripts/ingest_bigquery.py`
- **Testing Core:** `tests/`
- **Testing Framework:** `pytest` (invoked via `uv run pytest`)

## Execution Steps

### Step 1: Secure Code Refactoring
1. Review the interpolation logic inside `Scripts/ingest_bigquery.py`.
2. Implement strict input validation on the `table_name` variable against a secure regex allowlist: `^[A-Za-z_][A-Za-z0-9_]*$`.
3. Refactor the string-concatenated identifier logic to utilize structured parameterized APIs or official BigQuery Table Reference objects instead of direct string manipulation.

### Step 2: Security Unit Test Implementation
1. Add a dedicated test block in the `tests/` directory ensuring that table names containing special characters, whitespaces, or semicolon separators (`localhost; DROP TABLE...`) are blocked or sanitized before query composition.

### Step 3: Local Quality Gate Check
1. Execute the local testing gate inside your environment by running: `uv run pytest`
2. Validate that the query compilation updates do not disrupt existing data ingestion flows.
