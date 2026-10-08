# Dependency Audit Report

**Date:** 2026-10-08
**Task:** [02-dependency-audit.md](../tasks/02-dependency-audit.md)
**Branch:** agent/security-dependency-audit
**Auditor:** Kilo Security Audit

---

## Executive Summary

A security audit of locked Python and Node.js dependencies was conducted using `pip-audit` and `npm audit`. Four vulnerabilities were identified in three Python packages; all have been remediated via minimal version upgrades. No vulnerabilities were found in Node.js dependencies.

| Ecosystem | Vulnerabilities Found | Remediated | Status |
|-----------|----------------------|------------|--------|
| Python (pip-audit) | 4 (3 packages) | 4 | ✅ Complete |
| Node.js (npm audit) | 0 | N/A | ✅ Clean |

---

## Python Findings (pip-audit)

### Vulnerabilities Identified

| Package | Current Version | Fixed Version | CVE / Advisory | Severity | Description |
|---------|----------------|---------------|----------------|----------|-------------|
| `oauthlib` | 3.3.1 | 4.0.0 | PYSEC-2026-4114 / CVE-2026-49265 | High | Timing side-channel in PKCE code verifier comparison |
| `urllib3` | 2.7.0 | 2.8.0 | PYSEC-2026-4177 / CVE-2026-97689 | High | Chunked encoding buffer overflow in HTTP response parsing |
| `urllib3` | 2.7.0 | 2.8.0 | PYSEC-2026-4176 / CVE-2026-97688 | High | Chunked encoding buffer overflow (secondary vector) |
| `werkzeug` | 3.1.8 | 3.1.9 | CVE-2026-102598 | Medium | Windows device name path traversal in `safe_join` |

### Remediation Applied

Upgraded packages to fixed versions via `uv add`:

```bash
uv add "oauthlib>=4.0.0" "urllib3>=2.8.0" "werkzeug>=3.1.9"
```

**Resulting changes in `uv.lock`:**
- `oauthlib`: 3.3.1 → 4.0.0
- `urllib3`: 2.7.0 → 2.8.0
- `werkzeug`: 3.1.8 → 3.1.9

### Verification

- Re-ran `pip-audit`: **"No known vulnerabilities found"**
- All 54 existing unit tests pass (`python -m unittest discover -s tests -v`)

---

## Node.js Findings (npm audit)

### Scan Results

```
npm audit --json
# 0 vulnerabilities found
```

No vulnerabilities detected in production or development dependencies.

---

## Software Bill of Materials (SBOM)

### Python SBOM
- **Location:** `sbom-python.json` (generated via `pip-audit` from the lockfile export)
- **Format:** CycloneDX JSON
- **Size:** ~275 KB
- **Packages:** 215 dependencies catalogued
- **Generated:** `uv tool run --from pip-audit==2.10.1 pip-audit -r audit-requirements.txt --no-deps --disable-pip --format=cyclonedx-json --output=sbom-python.json`

### Node.js SBOM
- **Location:** `sbom-npm.json` (generated via `npm sbom`)
- **Format:** CycloneDX JSON
- **Packages:** All production dependencies from `package-lock.json`
- **Generated:** `npm sbom --sbom-format=cyclonedx --json > sbom-npm.json`

> **Note:** Both SBOMs are uploaded as artifacts in the CI workflow (retention: 90 days).

---

## CI/CD Integration

A new GitHub Actions workflow has been created at `.github/workflows/security_dependency_audit.yml` with:

### Triggers
- **Scheduled:** Weekly on Mondays at 06:00 UTC
- **On push/PR:** Changes to `pyproject.toml`, `uv.lock`, `package.json`, `package-lock.json`
- **Manual:** `workflow_dispatch` for ad-hoc runs

### Jobs
1. **python-audit** — Runs `pip-audit`, generates Python SBOM, fails on any known vulnerability or scanner error
2. **npm-audit** — Runs `npm audit`, generates npm SBOM, fails on moderate-or-higher vulnerabilities or scanner errors
3. **summary** — Aggregates results from both ecosystems

### Artifacts (90-day retention)
- `pip-audit-results.json` — Raw pip-audit output
- `npm-audit-results.json` — Raw npm audit output
- `sbom-python.json` — Python CycloneDX SBOM
- `sbom-npm.json` — Node.js CycloneDX SBOM

---

## Recurrence Prevention

### For Developers
1. **Before merging dependency changes:** Run `uv run pip-audit` and `npm audit` locally
2. **When adding new dependencies:** Pin to versions without known vulnerabilities
3. **Weekly:** Review scheduled workflow results in GitHub Actions

### For CI/CD
1. The weekly scheduled workflow catches new CVEs in existing dependencies
2. PR checks block any known Python vulnerability and moderate-or-higher npm vulnerabilities
3. SBOM artifacts provide traceability for compliance audits

### For Dependencies
1. **Python:** Use `uv` lockfile (`uv.lock`) for reproducible builds
2. **Node.js:** Use `package-lock.json` and `npm ci` for deterministic installs
3. Both lockfiles are committed to version control

---

## Files Modified

| File | Change |
|------|--------|
| `uv.lock` | Updated oauthlib, urllib3, werkzeug to fixed versions |
| `.github/workflows/security_dependency_audit.yml` | New CI workflow for automated auditing |
| `docs/security/dependency-audit.md` | This report |

---

## Commands Reference

### Local Python Audit
```bash
uv export --locked --no-emit-project --output-file audit-requirements.txt
uv tool run --from pip-audit==2.10.1 pip-audit -r audit-requirements.txt --no-deps --disable-pip --format=json --output=pip-audit-results.json
uv tool run --from pip-audit==2.10.1 pip-audit -r audit-requirements.txt --no-deps --disable-pip --format=cyclonedx-json --output=sbom-python.json
```

### Local Node.js Audit
```bash
npm ci
npm audit --json --audit-level=moderate > npm-audit-results.json
npm sbom --sbom-format=cyclonedx --json > sbom-npm.json
```

### Run Full Test Suite
```bash
.venv/bin/python -B -m unittest discover -s tests -v
npm run test:auth
```

---

## Next Audit

**Scheduled:** Next Monday 06:00 UTC via GitHub Actions
**Manual trigger:** Available in Actions → Security Dependency Audit → Run workflow

## CI reporting correction (2026-10-09)

The Python scan succeeded, but the workflow then requested the unsupported `text` output format. A jq precedence error and skipped artifact upload caused secondary failures. CI now audits the locked project graph with isolated audit tooling, captures the scanner exit status, retains available reports after failures, and reports missing artifacts explicitly. Python gating does not assume a severity field that pip-audit JSON does not provide. Audit reports retain 30 days; SBOMs retain 90 days.
