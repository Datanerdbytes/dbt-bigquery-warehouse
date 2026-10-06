# Task: Remediate Disabled TLS Certificate Validation for SQL Server

## Context & Issue Description
The ODBC database connection configurations explicitly bypass security protocol verification by hardcoding `TrustServerCertificate=yes` within the ingestion setup strings. This leaves database ingestion traffic highly vulnerable to Man-in-the-Middle (MitM) interceptions, risking database credential leakage or raw data tampering.

## Target Project Assets
- **Data Ingestion Script:** `Scripts/ingest_bigquery.py`
- **Testing Core:** `tests/`
- **Testing Framework:** `pytest` (invoked via `uv run pytest`)

## Execution Steps

### Step 1: Connection Configuration Hardening
1. Audit connection string processing modules inside `Scripts/ingest_bigquery.py`.
2. Remove all instances of `TrustServerCertificate=yes` from the target connection parameters.
3. Enforce secure `encrypted=TLS` connections accompanied by valid server certificate validations.

### Step 2: Verification of Client-Side Trust Stores
1. Ensure the agent configures connection error handles so that missing or untrusted certificate states fail fast and loud during integration attempts.

### Step 3: Local Quality Gate Check
1. Execute the local testing gate inside your environment by running: `uv run pytest`
2. Confirm the security enforcement allows your core pipeline integration blocks to run smoothly without breaking underlying connection objects.
