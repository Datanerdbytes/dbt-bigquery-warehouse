"""Verify that a Supabase project is configured for this app.

The auth stack reads four environment variables and expects three SQL
migrations. This script checks a live project against that contract so a
misconfigured project is found here instead of in the browser.

Run it against the project created for this deployment:

    python Scripts/verify_supabase_setup.py

The keys are read from the environment, so nothing sensitive is passed on the
command line. `--url`, `--anon-key` and `--service-role-key` exist for one-off
checks, but the environment is the safer route.

Usage:
    python Scripts/verify_supabase_setup.py
    python Scripts/verify_supabase_setup.py --skip-password-grant
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

READY_RPCS = {
    "qe_account_deletion_guard_ready": "account deletion guard",
    "qe_administrator_access_guard_ready": "administrator access guard",
}


def _request(
    method: str,
    url: str,
    key: str,
    body: dict | None = None,
    timeout: int = 15,
) -> tuple[int, dict]:
    """Call the Supabase API and return the status code and parsed body."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"apikey": key, "Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(1_000_001)
            status = response.status
    except urllib.error.HTTPError as error:
        raw = error.read(1_000_001)
        status = error.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, {"message": "the project could not be reached"}
    try:
        parsed = json.loads(raw) if raw.strip() else {}
    except ValueError:
        parsed = {"message": raw[:200].decode("utf-8", "replace")}
    if not isinstance(parsed, dict):
        parsed = {"data": parsed}
    return status, parsed


class Report:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, ok: bool, label: str, detail: str = "") -> bool:
        status = "PASS" if ok else "FAIL"
        if not ok:
            self.failures += 1
        suffix = f" — {detail}" if detail else ""
        print(f"[{status}] {label}{suffix}")
        return ok


def _base(url: str) -> str:
    return url.rstrip("/")


def _check_settings(report: Report, url: str, anon: str) -> None:
    status, body = _request("GET", f"{_base(url)}/auth/v1/settings", anon)
    if not report.check(status == 200, "auth settings readable", f"HTTP {status}"):
        return
    external = body.get("external") if isinstance(body.get("external"), dict) else {}
    for provider in ("google", "github"):
        enabled = external.get(provider) is True
        report.check(
            enabled,
            f"{provider} OAuth provider enabled",
            "enable it in Authentication → Providers" if not enabled else "",
        )
    report.check(
        external.get("email") is True,
        "email provider enabled",
        "enable it in Authentication → Providers"
        if external.get("email") is not True
        else "",
    )
    report.check(
        body.get("disable_signup") is not True,
        "sign-ups allowed",
        "sign-ups are disabled on this project",
    )


def _check_anon_key(report: Report, url: str, anon: str) -> None:
    status, body = _request("GET", f"{_base(url)}/auth/v1/user", anon)
    message = str(body.get("message", body.get("msg", ""))).lower()
    rejected = "invalid api key" in message or "no api key" in message
    report.check(
        not rejected,
        "anonymous key accepted",
        f"HTTP {status} {body.get('message', '')}".strip() if rejected else "",
    )


def _check_service_role(report: Report, url: str, service_role: str) -> None:
    status, body = _request(
        "GET",
        f"{_base(url)}/rest/v1/qe_password_attempts?select=email&limit=1",
        service_role,
    )
    if status == 200:
        report.check(True, "service-role key reads the database")
        report.check(True, "password lockout migration applied")
        return
    if status == 404:
        report.check(
            False,
            "service-role key reads the database",
            "the qe_password_attempts table is missing; apply migration 1",
        )
        return
    report.check(
        False,
        "service-role key reads the database",
        f"HTTP {status} {body.get('message', '')}".strip(),
    )


def _check_ready_rpcs(report: Report, url: str, service_role: str) -> None:
    for name, label in READY_RPCS.items():
        status, body = _request(
            "POST", f"{_base(url)}/rest/v1/rpc/{name}", service_role, body={}
        )
        ready = body.get("ready") is True
        report.check(
            ready,
            f"{label} installed",
            f"HTTP {status} {body.get('message', '')}".strip() if not ready else "",
        )


def _check_password_grant(report: Report, url: str, anon: str) -> None:
    status, body = _request(
        "POST",
        f"{_base(url)}/auth/v1/token?grant_type=password",
        anon,
        body={
            "email": "keepawake-check@example.invalid",
            "password": "not-a-password",  # pragma: allowlist secret (dummy credential)
        },
    )
    code = str(body.get("error_code", ""))
    report.check(
        status == 400 and code == "invalid_credentials",
        "email and password sign-in enabled",
        f"HTTP {status} {code or body.get('msg', body.get('message', ''))}".strip(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a Supabase project setup")
    parser.add_argument("--url", default=os.getenv("NEXT_PUBLIC_SUPABASE_URL", ""))
    parser.add_argument(
        "--anon-key", default=os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
    )
    parser.add_argument(
        "--service-role-key", default=os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    )
    parser.add_argument(
        "--origin", default=os.getenv("AUTH_APP_ORIGIN", ""), help="deployment origin"
    )
    parser.add_argument("--skip-password-grant", action="store_true")
    args = parser.parse_args(argv)

    url = (args.url or "").strip().rstrip("/")
    anon = (args.anon_key or "").strip()
    service_role = (args.service_role_key or "").strip()

    report = Report()
    if not report.check(
        bool(url) and url.startswith("https://"),
        "project URL configured",
        "set NEXT_PUBLIC_SUPABASE_URL",
    ):
        return 1
    if not report.check(
        bool(anon), "anonymous key configured", "set NEXT_PUBLIC_SUPABASE_ANON_KEY"
    ):
        return 1
    if not report.check(
        bool(service_role),
        "service-role key configured",
        "set SUPABASE_SERVICE_ROLE_KEY",
    ):
        return 1

    print(f"\nProject: {url}\n")

    _check_settings(report, url, anon)
    _check_anon_key(report, url, anon)
    _check_service_role(report, url, service_role)
    _check_ready_rpcs(report, url, service_role)
    if not args.skip_password_grant:
        _check_password_grant(report, url, anon)

    origin = (args.origin or "").strip().rstrip("/")
    print("\nManual steps that cannot be checked through the API:")
    print(f"  - Set AUTH_APP_ORIGIN to {origin or 'the deployment origin'}")
    print("  - Add that origin and <origin>/auth/callback to the redirect URLs")
    print("  - Promote the first account to qe_owner in app_metadata")
    print("  - Set AUTH_PASSWORD_LOCKOUT_ENABLED=true in the deployment")
    print("  - Set CRON_SECRET in the deployment so the keep-wake cron can run")

    if report.failures:
        print(f"\n{report.failures} check(s) failed.")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
