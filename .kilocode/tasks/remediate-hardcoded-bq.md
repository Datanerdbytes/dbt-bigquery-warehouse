# Task: Remediate Hardcoded Production BigQuery Table/Dataset Identifiers

## Target Files
- `analytics_layer/scripts/load_coverage_to_bq.py`
- `utils/audit_logger.py`

## Issue Description
Table and dataset identifiers (e.g., `quantum-echo-data-eng-prod.audit_metadata.dbt_test_coverage`) are currently hardcoded. This creates a high risk of cross-environment data contamination, where running code or test suites in a local/staging environment could accidentally write or overwrite critical production metrics.

## Remediation Requirements
1. **Pre-Implementation Audit (Crucial)**: Before modifying anything, check if previous tasks have already implemented a global configuration module, shared helper utilities, or standard environment gating flags (such as checking `NODE_ENV`). If an environment management pattern exists, reuse it to maintain a unified architecture.
2. **Environment-Driven Configuration**: Remove all hardcoded production table, dataset, and project prefixes. Refactor them to read dynamically from environment variables (e.g., `BQ_PROJECT_ID`, `BQ_DATASET_NAME`) with safe, non-production defaults.
3. **Environment Gating**: Implement an explicit runtime gate block immediately preceding any BigQuery write operations. Ensure that execution stops safely or re-routes to a sandbox if it detects a mismatch between the current environment configuration and the targeted table space.
4. **Testing Verification**: Write unit tests using `unittest.mock` or `pytest` to verify that when `NODE_ENV="test"` is active, the script seamlessly resolves to mock datasets and does not attempt any remote production calls.
