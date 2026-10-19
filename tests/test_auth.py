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
    "AUTH_PASSWORD_LOCKOUT_ENABLED": "false",
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
        response.__enter__ = Mock(side_effect=lambda: io.StringIO(json.dumps(user)))
        response.__exit__ = Mock(return_value=False)
        return patch.object(auth, "urlopen", return_value=response)

    def test_public_pages_and_config(self):
        with patch.object(auth, "urlopen") as remote:
            for path in [
                "/login",
                "/signup",
                "/forgot-password",
                "/reset-password",
                "/auth/callback",
                "/healthz",
            ]:
                self.assertEqual(self.client.get(path).status_code, 200)
            self.assertEqual(
                set(self.client.get("/auth/config").json),
                {"url", "anonKey", "passwordLockoutEnabled"},
            )
            remote.assert_not_called()
        self.loader.assert_not_called()

    def test_password_recovery_pages_use_scoped_forms(self):
        login = self.client.get("/login").get_data(as_text=True)
        forgot = self.client.get("/forgot-password").get_data(as_text=True)
        reset = self.client.get("/reset-password").get_data(as_text=True)
        self.assertIn('href="/forgot-password"', login)
        self.assertIn('data-auth-page="forgot"', forgot)
        self.assertIn('id="auth-email"', forgot)
        self.assertNotIn('id="auth-password"', forgot)
        self.assertNotIn("data-provider=", forgot)
        self.assertIn('data-auth-page="reset"', reset)
        self.assertIn('id="auth-confirm-password"', reset)
        self.assertIn('autocomplete="new-password"', reset)
        self.assertNotIn('id="auth-email"', reset)
        self.assertNotIn("data-provider=", reset)
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
            self.assertIn('data-carousel="rotation"', html)
            self.assertNotIn('data-carousel="previous"', html)
            self.assertNotIn('data-carousel="next"', html)
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

    def test_forged_expired_and_unconfirmed_tokens(self):
        self.client.set_cookie(auth.COOKIE, token())
        with patch.object(
            auth, "urlopen", side_effect=HTTPError("url", 401, "", {}, None)
        ):
            self.assertEqual(self.client.get("/_dash-layout").status_code, 401)
        for user in [
            dict(USER, email_confirmed_at=None),
        ]:
            with self.remote(user):
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

    def test_auth_page_navigation_does_not_consume_attempt_budget(self):
        with patch.object(auth, "verify_access") as verify:
            for _ in range(12):
                for path in ("/login", "/signup", "/auth/callback"):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("Content-Security-Policy", response.headers)
            verify.assert_not_called()
        self.loader.assert_not_called()

    def test_successful_session_sync_does_not_consume_attempt_budget(self):
        headers = {"Origin": ENV["AUTH_APP_ORIGIN"]}
        for _ in range(15):
            with self.remote() as remote:
                response = self.client.post(
                    "/auth/session", json={"access_token": token()}, headers=headers
                )
            self.assertEqual(response.status_code, 200)
            # Every accepted synchronization still verifies identity remotely.
            remote.assert_called_once()
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

    def test_public_config_reads_do_not_consume_attempt_budget(self):
        for _ in range(40):
            response = self.client.get("/auth/config")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                set(response.json), {"url", "anonKey", "passwordLockoutEnabled"}
            )
            self.assertIn("no-store", response.headers["Cache-Control"])

    def test_account_enumeration_protection_generic_error(self):
        """Test that auth errors return generic messages to prevent account enumeration."""
        # Test with expired token
        self.client.set_cookie(auth.COOKIE, token(int(time.time()) - 5))
        with self.remote():
            response = self.client.get("/_dash-layout")
        self.assertEqual(response.status_code, 401)
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


class VerifiedEmailAccessTests(AuthTests):
    """Verified Supabase identities no longer need manual email approval."""

    def test_verified_email_can_sync_and_load_data_without_manual_approval(self):
        for legacy_allowlist in (None, "", "someone-else@example.com"):
            with self.subTest(legacy_allowlist=legacy_allowlist):
                self.client.delete_cookie(auth.COOKIE)
                with patch.dict(os.environ):
                    os.environ.pop("AUTH_ALLOWED_EMAILS", None)
                    if legacy_allowlist is not None:
                        os.environ["AUTH_ALLOWED_EMAILS"] = legacy_allowlist
                    with self.remote(dict(USER, email="new-user@example.net")):
                        response = self.client.post(
                            "/auth/session",
                            json={"access_token": token()},
                            headers={"Origin": ENV["AUTH_APP_ORIGIN"]},
                        )
                        self.assertEqual(response.status_code, 200)
                        self.assertIn(auth.COOKIE, response.headers["Set-Cookie"])
                        self.assertEqual(
                            self.client.get("/_dash-layout").status_code, 200
                        )
                        self.assertEqual(self.client.get("/dashboard").status_code, 200)

    def test_missing_or_unconfirmed_email_cannot_sync_or_load_data(self):
        for changes in (
            {"email": None},
            {"email": ""},
            {"email": "  "},
            {"email": 123},
            {"email_confirmed_at": None},
        ):
            with self.subTest(changes=changes), self.remote(dict(USER, **changes)):
                self.client.delete_cookie(auth.COOKIE)
                response = self.client.post(
                    "/auth/session",
                    json={"access_token": token()},
                    headers={"Origin": ENV["AUTH_APP_ORIGIN"]},
                )
                self.assertEqual(response.status_code, 403)
                self.assertIn("Max-Age=0", response.headers.get("Set-Cookie", ""))
                self.client.set_cookie(auth.COOKIE, token())
                self.assertEqual(self.client.get("/_dash-layout").status_code, 403)
                self.assertEqual(self.client.get("/dashboard").location, "/login")
        self.loader.assert_not_called()

    def test_unconfirmed_account_gains_access_after_remote_confirmation(self):
        self.client.set_cookie(auth.COOKIE, token())
        with self.remote(dict(USER, email_confirmed_at=None)):
            self.assertEqual(self.client.get("/_dash-layout").status_code, 403)
        self.loader.assert_not_called()
        with self.remote(dict(USER, email="new-user@example.net")):
            self.assertEqual(self.client.get("/_dash-layout").status_code, 200)
        self.loader.assert_called_once()
