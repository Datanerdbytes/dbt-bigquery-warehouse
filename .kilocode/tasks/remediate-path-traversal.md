# Task: Remediate Potential Path Traversal / Arbitrary File Read

## Target Files
- `my-dash-app/app_observability.py`
- `analytics_layer/scripts/calculate_coverage.py`

## Issue Description
The `MANIFEST_PATH` and manifest loading implementation currently use fixed paths. However, if any future endpoints or modifications allow user-controlled path parameters, using raw `json.load(open(...))` calls creates a severe path traversal vulnerability. This could allow an attacker to read arbitrary local system files.

## Remediation Requirements
1. **Strict Path Separation**: Enforce that manifest paths remain strictly hardcoded, environment-driven, or configuration-controlled. They must never accept dynamic user input.
2. **Defensive Validation**: Implement explicit file existence checks using `os.path.exists()` or `pathlib.Path.is_file()`.
3. **Secure Error Handling**: Add specific `FileNotFoundError` and `PermissionError` exceptions. Ensure that any logged messages or application responses do not leak absolute system paths or internal directory structures.
4. **Testing Verification**: Write matching `pytest` unit tests to ensure manifest parsing handles missing or invalid configuration paths gracefully without crashing or leaking sensitive error context.
