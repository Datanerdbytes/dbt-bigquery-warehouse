# Task: Address Production Credentials Vulnerability in Python/Dash Project

## Context & Issue Description
Our local workspace contains sensitive production configurations (including real Supabase keys, database passwords, and GCP service account private keys) inside untracked files like `.env` and `gcp-key.json`. While safely ignored by `.gitignore`, their presence in the active workspace poses a security leakage risk via local IDE caches, background daemons, or backup clones.

## Target Project Assets
- **Authentication Handling:** `my-dash-app/auth.py`
- **Data Load Engine:** `my-dash-app/data_loader.py`
- **Testing Core:** `tests/`
- **Testing Framework:** `pytest` (invoked via `uv run pytest`)

## Execution Steps

### Step 1: Secure Source Code Audit
1. Scan `my-dash-app/auth.py` and `my-dash-app/data_loader.py` to guarantee that all connection strings, Supabase keys, and GCP private variables are loaded strictly from environment processes (`os.environ` or `os.getenv`).
2. Verify that there are no hardcoded string keys or direct fallback variables pointing to the literal physical paths of your local untracked file objects.

### Step 2: Test Suitability Scan
1. Review your existing verification suites inside the `tests/` directory.
2. Ensure that any integration mock setups cleanly override environment parameters during testing phases without attempting to hook into live production clusters.

### Step 3: Local Quality Gate Check
1. Execute the local testing gate inside your active environment by running: `uv run pytest`
2. Validate that the security modifications haven't broken any of your 44 existing dashboard regression tests.

### Step 4: Repository History Scan
1. Audit the repository's Git commit history locally to check if raw contents of `gcp-key.json` or active `.env` strings were accidentally committed in any historical branch revisions.
2. Log any discovered historical commit hashes in the agent's task summary so they can be securely purged using `git filter-repo` on the upstream repository later.
