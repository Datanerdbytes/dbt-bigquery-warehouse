# Task: Remediate Logging of Sensitive Metadata in Plain Text

## Target Files
- `utils/audit_logger.py`
- `Scripts/` (All data ingestion scripts inside this directory)

## Issue Description
The codebase currently relies on raw `print()` statements that risk exposing sensitive application metadata, such as system file paths, explicit BigQuery table structures, internal parameters, or granular database error tracebacks. This introduces an information leakage vulnerability into container logs, CI output pipelines, and standard local output streams.

## Remediation Requirements
1. **Pre-Implementation Audit**: Review how logs are currently structured across the `utils/` and `Scripts/` directories to ensure that formatting fixes do not conflict with or double-register handlers against any existing root log configurations.
2. **Structured Logging Migration**: Systematically replace unstructured `print()` statements with standard Python `logging` modules configured with proper level gating (`logging.info`, `logging.warning`, `logging.error`).
3. **Metadata Redaction & Formatting**: Implement a central log formatter, helper function, or logging filter to sanitize information before it outputs. Explicitly redact database connection strings, absolute file paths, raw SQL query strings containing identifiers, and system credentials.
4. **Testing Verification**: Write unit tests using `pytest` and `capsys` (or `pytest.LogCaptureFixture`) to guarantee that logging modules trap runtime metrics correctly, while explicitly validating that raw internal paths or un-redacted queries never reach stdout or stderr output buffers.
