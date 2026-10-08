"""Offline checks for the full authorization boundary."""

import base64
import io
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
import auth

ENV = {
    "NEXT_PUBLIC_SUPABASE_URL": "https://example.supabase.co",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY": "test-key",
    "AUTH_APP_ORIGIN": "https://analytics.example.com",
    "AUTH_ALLOWED_EMAILS": "Analyst@Example.com",
}
USER = {
    "id": "user-1",
    "email": "analyst@example.com",
    "email_confirmed_at": "2026-01-01",
}


def token(exp=None):
    payload = (
        base64.urlsafe_b64encode(
            json.dumps({"exp": exp or int(time.time()) + 3600}).encode()
        )
        .decode()
        .rstrip("=")
    )
    return f"header.{payload}.signature"


class AuthTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, ENV)
        env.start()
        self.addCleanup(env.stop)
        self.server = Flask(__name__)
        auth.install_auth(self.server)
        self.loader = Mock(return_value={"data": "private"})
        for path in [
            "/dashboard",
            "/customers",
            "/pipeline-health",
            "/_dash-layout",
            "/_dash-dependencies",
            "/_dash-update-component",
            "/export",
        ]:
            self.server.add_url_rule(
                path, path, lambda: self.loader(), methods=["GET", "POST"]
            )
        self.client = self.server.test_client()

    def remote(self, user=USER):
        response = Mock()
        response.__enter__ = Mock(return_value=io.StringIO(json.dumps(user)))
        response.__exit__ = Mock(return_value=False)
        return patch.object(auth, "urlopen", return_value=response)

    def test_public_pages_and_config(self):
        with patch.object(auth, "urlopen") as remote:
            for path in ["/login", "/signup", "/auth/callback", "/healthz"]:
                self.assertEqual(self.client.get(path).status_code, 200)
            self.assertEqual(
                set(self.client.get("/auth/config").json), {"url", "anonKey"}
            )
            remote.assert_not_called()
        self.loader.assert_not_called()

    def test_public_landing_is_separate_from_signin(self):
        with patch.object(auth, "urlopen") as remote:
            page = self.client.get("/")
            self.assertEqual(page.status_code, 200)
            html = page.get_data(as_text=True)
            self.assertIn('href="/login"', html)
            self.assertIn('id="auth-showcase"', html)
            self.assertIn('src="/assets/showcase.bundle.js"', html)
            self.assertNotIn('id="auth-form"', html)
            self.assertNotIn('src="/assets/auth.bundle.js"', html)
            login = self.client.get("/login").get_data(as_text=True)
            self.assertIn('id="auth-form"', login)
            self.assertNotIn('id="auth-showcase"', login)
            remote.assert_not_called()
        self.loader.assert_not_called()

    def test_landing_remains_public_with_stale_cookie_or_auth_outage(self):
        self.client.set_cookie(auth.COOKIE, "stale")
        for status in (401, 403, 503):
            with patch.object(
                auth, "verify_access", side_effect=auth.AuthError("unavailable", status)
            ):
                self.assertEqual(self.client.get("/").status_code, 200)
                self.assertEqual(self.client.get("/_dash-layout").status_code, status)
        self.loader.assert_not_called()

    def test_unauthenticated_requests_never_load_data(self):
        for path in ["/dashboard", "/customers", "/pipeline-health", "/export"]:
            self.assertEqual(self.client.get(path).location, "/login")
        for path in ["/_dash-layout", "/_dash-dependencies"]:
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(
            self.client.post(
                "/_dash-update-component", headers={"Origin": ENV["AUTH_APP_ORIGIN"]}
            ).status_code,
            401,
        )
        self.loader.assert_not_called()

    def test_cookie_flags_and_success(self):
        with self.remote():
            response = self.client.post(
                "/auth/session",
                json={"access_token": token()},
                headers={"Origin": ENV["AUTH_APP_ORIGIN"]},
            )
        self.assertEqual(response.status_code, 200)
        for flag in ["Secure", "HttpOnly", "SameSite=Lax", "Path=/"]:
            self.assertIn(flag, response.headers["Set-Cookie"])
        with self.remote():
            self.assertEqual(self.client.get("/dashboard").status_code, 200)
        with self.remote():
            self.assertEqual(self.client.get("/").location, "/dashboard")

    def test_forged_expired_and_unapproved_tokens(self):
        self.client.set_cookie(auth.COOKIE, token())
        with patch.object(
            auth, "urlopen", side_effect=HTTPError("url", 401, "", {}, None)
        ):
            self.assertEqual(self.client.get("/_dash-layout").status_code, 401)
        for user in [
            dict(USER, email_confirmed_at=None),
            dict(USER, email="other@example.com"),
        ]:
            with self.remote(user):
                self.assertEqual(self.client.get("/_dash-layout").status_code, 403)
        with patch.dict(os.environ, {"AUTH_ALLOWED_EMAILS": ""}), self.remote():
            self.assertEqual(self.client.get("/_dash-layout").status_code, 403)
        self.client.set_cookie(auth.COOKIE, token(int(time.time()) - 5))
        with self.remote():
            self.assertEqual(self.client.get("/_dash-layout").status_code, 401)
        self.loader.assert_not_called()

    def test_outage_and_missing_config_fail_closed(self):
        self.client.set_cookie(auth.COOKIE, token())
        with patch.object(auth, "urlopen", side_effect=URLError("offline")):
            self.assertEqual(self.client.get("/_dash-layout").status_code, 503)
        with patch.dict(os.environ, {"NEXT_PUBLIC_SUPABASE_URL": ""}):
            self.assertEqual(self.client.get("/auth/config").status_code, 503)
            self.assertEqual(self.client.get("/dashboard").status_code, 503)
        self.loader.assert_not_called()

    def test_csrf_logout_and_malformed_body(self):
        for origin in [None, "null", "https://evil.example.com"]:
            headers = {"Origin": origin} if origin else {}
            self.assertEqual(
                self.client.post("/auth/session", headers=headers).status_code, 403
            )
        headers = {"Origin": ENV["AUTH_APP_ORIGIN"]}
        for body in [[], {}, {"access_token": []}]:
            self.assertEqual(
                self.client.post(
                    "/auth/session", json=body, headers=headers
                ).status_code,
                401,
            )
        response = self.client.delete("/auth/session", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Max-Age=0", response.headers["Set-Cookie"])
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_rate_limiting_on_auth_page(self):
        """Test that auth pages are rate limited (5 per minute)."""
        # Make 5 requests - should all succeed
        for _ in range(5):
            response = self.client.get("/login")
            self.assertEqual(response.status_code, 200)
        # 6th request should be rate limited
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.mimetype, "text/html")
        self.assertIn('data-auth-page="rate_limited"', response.get_data(as_text=True))
        self.assertIn("Content-Security-Policy", response.headers)

    def test_rate_limiting_on_session_bridge(self):
        """Test that session bridge is rate limited (10 per minute)."""
        # Mock Supabase to return 401 for invalid tokens
        with patch.object(
            auth, "urlopen", side_effect=HTTPError("url", 401, "", {}, None)
        ):
            # Make 10 requests - should all return 401 (not rate limited)
            for _ in range(10):
                response = self.client.post(
                    "/auth/session",
                    json={"access_token": "invalid"},
                    headers={"Origin": ENV["AUTH_APP_ORIGIN"]},
                )
                self.assertEqual(response.status_code, 401)
            # 11th request should be rate limited (429)
            response = self.client.post(
                "/auth/session",
                json={"access_token": "invalid"},
                headers={"Origin": ENV["AUTH_APP_ORIGIN"]},
            )
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.json["error"], "rate_limited")

    def test_logout_remains_available_after_session_rate_limit(self):
        headers = {"Origin": ENV["AUTH_APP_ORIGIN"]}
        with patch.object(
            auth, "verify_access", side_effect=auth.AuthError("session_expired", 401)
        ):
            for _ in range(10):
                self.assertEqual(
                    self.client.post(
                        "/auth/session", json={}, headers=headers
                    ).status_code,
                    401,
                )
            self.assertEqual(
                self.client.post("/auth/session", json={}, headers=headers).status_code,
                429,
            )
        self.client.set_cookie(auth.COOKIE, "expired-cookie")
        with patch.object(auth, "verify_access") as verify:
            # Deleting an existing cookie is idempotent and must not verify it.
            for _ in range(12):
                response = self.client.delete("/auth/session", headers=headers)
                self.assertEqual(response.status_code, 200)
                self.assertIn("Max-Age=0", response.headers["Set-Cookie"])
            verify.assert_not_called()
        self.assertIsNone(self.client.get_cookie(auth.COOKIE))
        self.assertEqual(self.client.get("/_dash-layout").status_code, 401)
        self.loader.assert_not_called()

    def test_logout_still_requires_matching_origin(self):
        self.client.set_cookie(auth.COOKIE, "existing-cookie")
        for origin in [None, "null", "https://evil.example.com"]:
            headers = {"Origin": origin} if origin else {}
            self.assertEqual(
                self.client.delete("/auth/session", headers=headers).status_code, 403
            )
            self.assertEqual(
                self.client.get_cookie(auth.COOKIE).value, "existing-cookie"
            )

    def test_rate_limiting_on_config(self):
        """Test that config endpoint is rate limited (30 per minute)."""
        # Make 30 requests - should all succeed
        for _ in range(30):
            response = self.client.get("/auth/config")
            self.assertEqual(response.status_code, 200)
        # 31st request should be rate limited
        response = self.client.get("/auth/config")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json["error"], "rate_limited")

    def test_account_enumeration_protection_generic_error(self):
        """Test that auth errors return generic messages to prevent account enumeration."""
        # Test with expired token
        self.client.set_cookie(auth.COOKIE, token(int(time.time()) - 5))
        with self.remote():
            response = self.client.get("/_dash-layout")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json["error"], auth.GENERIC_AUTH_ERROR)

        # Test with unapproved email
        with self.remote(dict(USER, email="other@example.com")):
            response = self.client.get("/_dash-layout")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json["error"], auth.GENERIC_AUTH_ERROR)

        # Test with unconfirmed email
        with self.remote(dict(USER, email_confirmed_at=None)):
            response = self.client.get("/_dash-layout")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json["error"], auth.GENERIC_AUTH_ERROR)

        # Test with invalid token
        with patch.object(
            auth, "urlopen", side_effect=HTTPError("url", 401, "", {}, None)
        ):
            response = self.client.get("/_dash-layout")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json["error"], auth.GENERIC_AUTH_ERROR)

    def test_session_bridge_returns_generic_error_on_invalid_token(self):
        """Test that session bridge returns generic error for invalid tokens."""
        with patch.object(
            auth, "urlopen", side_effect=HTTPError("url", 401, "", {}, None)
        ):
            response = self.client.post(
                "/auth/session",
                json={"access_token": "invalid"},
                headers={"Origin": ENV["AUTH_APP_ORIGIN"]},
            )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json["error"], auth.GENERIC_AUTH_ERROR)


class EmailAllowlistAuditTests(AuthTests):
    """Regression coverage for case-insensitive exact-email allowlist matching.

    The allowlist in auth.verify_access casefolds both the allowlist
    entries and the Supabase-returned email, then performs an exact
    set-membership test.  These tests prove that behaviour so that
    the "proposed bypass" (case-sensitive or partial match) is not
    confirmed.
    """

    # ------------------------------------------------------------------ #
    # Positive: full-address case-insensitive matching
    # ------------------------------------------------------------------ #

    def test_allowlist_match_mixed_case_local_part(self):
        """Mixed-case local part in the allowlist matches any-casing email."""
        with patch.dict(os.environ, {"AUTH_ALLOWED_EMAILS": "Analyst@Example.com"}):
            user = dict(USER, email="ANALYST@example.com")
            with self.remote(user):
                result = auth.verify_access(token())
        self.assertEqual(result[0]["email"], "ANALYST@example.com")

    def test_allowlist_match_mixed_case_domain(self):
        """Mixed-case domain in the allowlist matches lowercase user email."""
        with patch.dict(os.environ, {"AUTH_ALLOWED_EMAILS": "user@DOMAIN.COM"}):
            user = dict(USER, email="user@domain.com")
            with self.remote(user):
                result = auth.verify_access(token())
        self.assertEqual(result[0]["email"], "user@domain.com")

    def test_allowlist_match_both_sides_mixed_case(self):
        """Both allowlist and returned email have mixed case in local+domain."""
        with patch.dict(os.environ, {"AUTH_ALLOWED_EMAILS": "Admin@Corp.IO"}):
            user = dict(USER, email="ADMIN@corp.io")
            with self.remote(user):
                result = auth.verify_access(token())
        self.assertEqual(result[0]["email"], "ADMIN@corp.io")

    def test_allowlist_match_uppercase_returned_email(self):
        """Supabase may return an all-uppercase email; casefold normalises it."""
        with patch.dict(os.environ, {"AUTH_ALLOWED_EMAILS": "analyst@example.com"}):
            user = dict(USER, email="ANALYST@EXAMPLE.COM")
            with self.remote(user):
                result = auth.verify_access(token())
        self.assertEqual(result[0]["email"], "ANALYST@EXAMPLE.COM")

    def test_allowlist_whitespace_trimmed(self):
        """Surrounding whitespace in allowlist entries is stripped before matching."""
        with patch.dict(os.environ, {"AUTH_ALLOWED_EMAILS": " analyst@example.com , "}):
            user = dict(USER, email="analyst@example.com")
            with self.remote(user):
                result = auth.verify_access(token())
        self.assertEqual(result[0]["email"], "analyst@example.com")

    def test_allowlist_multiple_entries_match_listed(self):
        """Multiple comma-separated entries: only explicitly listed addresses match."""
        with patch.dict(
            os.environ,
            {"AUTH_ALLOWED_EMAILS": "admin@example.com,Analyst@Example.com"},
        ):
            for email in ("admin@example.com", "analyst@example.com"):
                user = dict(USER, email=email)
                with self.remote(user):
                    result = auth.verify_access(token())
                self.assertEqual(result[0]["email"], email)

    # ------------------------------------------------------------------ #
    # Negative: partial / domain-only / lookalike rejection
    # ------------------------------------------------------------------ #

    def test_allowlist_rejects_different_local_part(self):
        """A different local part on the same domain is rejected (403)."""
        with patch.dict(os.environ, {"AUTH_ALLOWED_EMAILS": "analyst@example.com"}):
            user = dict(USER, email="attacker@example.com")
            with self.remote(user):
                with self.assertRaises(auth.AuthError) as ctx:
                    auth.verify_access(token())
        self.assertEqual(ctx.exception.code, "approval_required")
        self.assertEqual(ctx.exception.status, 403)

    def test_allowlist_rejects_suffix_lookalike(self):
        """Suffix lookalike: analyst@example.com.evil.com is rejected."""
        with patch.dict(os.environ, {"AUTH_ALLOWED_EMAILS": "analyst@example.com"}):
            user = dict(USER, email="analyst@example.com.evil.com")
            with self.remote(user):
                with self.assertRaises(auth.AuthError) as ctx:
                    auth.verify_access(token())
        self.assertEqual(ctx.exception.code, "approval_required")

    def test_allowlist_rejects_prefix_lookalike(self):
        """Prefix lookalike: analyst@evil.example.com is rejected."""
        with patch.dict(os.environ, {"AUTH_ALLOWED_EMAILS": "analyst@example.com"}):
            user = dict(USER, email="analyst@evil.example.com")
            with self.remote(user):
                with self.assertRaises(auth.AuthError) as ctx:
                    auth.verify_access(token())
        self.assertEqual(ctx.exception.code, "approval_required")

    def test_allowlist_rejects_attacker_subdomain(self):
        """Attacker-controlled subdomain suffix is rejected."""
        with patch.dict(os.environ, {"AUTH_ALLOWED_EMAILS": "user@victim.example.com"}):
            user = dict(USER, email="user@victim.example.com.attacker.example.com")
            with self.remote(user):
                with self.assertRaises(auth.AuthError) as ctx:
                    auth.verify_access(token())
        self.assertEqual(ctx.exception.code, "approval_required")

    def test_allowlist_rejects_plus_address_variant(self):
        """Plus-address variant is rejected unless explicitly listed."""
        with patch.dict(os.environ, {"AUTH_ALLOWED_EMAILS": "analyst@example.com"}):
            user = dict(USER, email="analyst+tag@example.com")
            with self.remote(user):
                with self.assertRaises(auth.AuthError) as ctx:
                    auth.verify_access(token())
        self.assertEqual(ctx.exception.code, "approval_required")

    def test_allowlist_accepts_explicitly_listed_plus_address(self):
        """A plus-address that IS explicitly listed in the allowlist matches."""
        with patch.dict(os.environ, {"AUTH_ALLOWED_EMAILS": "analyst+tag@example.com"}):
            user = dict(USER, email="analyst+tag@example.com")
            with self.remote(user):
                result = auth.verify_access(token())
        self.assertEqual(result[0]["email"], "analyst+tag@example.com")

    # ------------------------------------------------------------------ #
    # Empty / whitespace-only allowlist
    # ------------------------------------------------------------------ #

    def test_allowlist_empty_denies_everyone(self):
        """An empty allowlist denies every verified email (403)."""
        with patch.dict(os.environ, {"AUTH_ALLOWED_EMAILS": ""}):
            user = dict(USER, email="analyst@example.com")
            with self.remote(user):
                with self.assertRaises(auth.AuthError) as ctx:
                    auth.verify_access(token())
        self.assertEqual(ctx.exception.code, "approval_required")
        self.assertEqual(ctx.exception.status, 403)

    def test_allowlist_whitespace_only_denies_everyone(self):
        """A whitespace-only allowlist denies every verified email (403)."""
        with patch.dict(os.environ, {"AUTH_ALLOWED_EMAILS": "   ,  \t  "}):
            user = dict(USER, email="analyst@example.com")
            with self.remote(user):
                with self.assertRaises(auth.AuthError) as ctx:
                    auth.verify_access(token())
        self.assertEqual(ctx.exception.code, "approval_required")
        self.assertEqual(ctx.exception.status, 403)

    # ------------------------------------------------------------------ #
    # Missing / unconfirmed email
    # ------------------------------------------------------------------ #

    def test_allowlist_missing_email_rejected(self):
        """A user dict without an email key is rejected (403)."""
        user = {k: v for k, v in USER.items() if k != "email"}
        with self.remote(user):
            with self.assertRaises(auth.AuthError) as ctx:
                auth.verify_access(token())
        self.assertEqual(ctx.exception.code, "approval_required")
        self.assertEqual(ctx.exception.status, 403)

    def test_confirmation_required_before_allowlist(self):
        """Unconfirmed email is rejected (403) even if on the allowlist."""
        with patch.dict(os.environ, {"AUTH_ALLOWED_EMAILS": "analyst@example.com"}):
            user = dict(USER, email_confirmed_at=None)
            with self.remote(user):
                with self.assertRaises(auth.AuthError) as ctx:
                    auth.verify_access(token())
        self.assertEqual(ctx.exception.code, "email_confirmation_required")
        self.assertEqual(ctx.exception.status, 403)

    # ------------------------------------------------------------------ #
    # Fail-closed: denied identity must not invoke data loaders
    # ------------------------------------------------------------------ #

    def test_allowlist_denial_blocks_data_loader_via_flask(self):
        """A denied identity does not invoke the protected data loader."""
        self.client.set_cookie(auth.COOKIE, token())
        with self.remote(dict(USER, email="disallowed@example.com")):
            response = self.client.get("/_dash-layout")
        self.assertEqual(response.status_code, 403)
        self.loader.assert_not_called()

    def test_allowlist_denial_blocks_data_loader_dashboard_redirect(self):
        """A denied identity is redirected to /login and never loads data."""
        self.client.set_cookie(auth.COOKIE, token())
        with self.remote(dict(USER, email="disallowed@example.com")):
            response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")
        self.loader.assert_not_called()
