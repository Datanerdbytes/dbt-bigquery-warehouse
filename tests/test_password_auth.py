"""Offline password gateway and real Flask request-boundary regressions."""

import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))

import auth
import password_auth as passwords
import test_auth as auth_fixture

LEASE = "11111111-1111-4111-8111-111111111111"
START = {"allowed": True, "attempt_id": LEASE, "retry_after": 0}
OK = {"allowed": True, "retry_after": 0}
INVALID = {"allowed": False, "error": "invalid_credentials", "retry_after": 0}
LOCKED = {"allowed": False, "error": "account_locked", "retry_after": 900}
TOKENS = {"access_token": "access", "refresh_token": "refresh"}


class PasswordGatewayTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"AUTH_PASSWORD_LOCKOUT_ENABLED": "true"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_valid_password_settles_shared_lease_before_returning_only_tokens(self):
        with patch.object(
            passwords,
            "_request",
            side_effect=[START, dict(TOKENS, user={"secret": "omit"}), OK],
        ) as remote:
            self.assertEqual(
                passwords.password_sign_in(" PERSON@EXAMPLE.COM ", "secret"), TOKENS
            )
            self.assertEqual(
                remote.call_args_list[0].args[1]["p_email"], "person@example.com"
            )
            self.assertEqual(remote.call_args_list[2].args[1]["p_attempt"], LEASE)
            self.assertIs(remote.call_args_list[2].args[1]["p_valid"], True)

    def test_incorrect_password_counts_and_threshold_locks_immediately(self):
        for settled, expected in [(INVALID, 401), (LOCKED, 423)]:
            with (
                self.subTest(expected=expected),
                patch.object(
                    passwords,
                    "_request",
                    side_effect=[
                        START,
                        passwords.PasswordAuthError("invalid_credentials", 401),
                        settled,
                    ],
                ) as remote,
            ):
                with self.assertRaises(passwords.PasswordAuthError) as caught:
                    passwords.password_sign_in("person@example.com", "wrong")
                self.assertEqual(caught.exception.status, expected)
                self.assertIs(remote.call_args_list[-1].args[1]["p_valid"], False)

    def test_locked_or_busy_accounts_never_send_password_to_provider(self):
        for result in [
            LOCKED,
            {"allowed": False, "error": "attempt_in_progress", "retry_after": 20},
        ]:
            with patch.object(passwords, "_request", return_value=result) as remote:
                with self.assertRaises(passwords.PasswordAuthError):
                    passwords.password_sign_in("person@example.com", "secret")
                self.assertEqual(remote.call_count, 1)

    def test_outages_and_provider_throttling_release_without_counting(self):
        for code, status in [
            ("auth_unavailable", 503),
            ("rate_limited", 429),
            ("email_confirmation_required", 403),
            ("account_suspended", 403),
        ]:
            with patch.object(
                passwords,
                "_request",
                side_effect=[
                    START,
                    passwords.PasswordAuthError(code, status),
                    {"allowed": False, "error": "auth_unavailable", "retry_after": 0},
                ],
            ) as remote:
                with self.assertRaises(passwords.PasswordAuthError) as caught:
                    passwords.password_sign_in("person@example.com", "secret")
                self.assertEqual(caught.exception.code, code)
                self.assertIsNone(remote.call_args_list[-1].args[1]["p_valid"])

    def test_expired_lease_or_failed_counter_store_never_returns_session(self):
        for finish in [
            {"allowed": False, "error": "attempt_expired", "retry_after": 1},
            passwords.PasswordAuthError("auth_unavailable"),
        ]:
            with patch.object(
                passwords, "_request", side_effect=[START, TOKENS, finish]
            ):
                with self.assertRaises(passwords.PasswordAuthError):
                    passwords.password_sign_in("person@example.com", "secret")

    def test_invalid_requests_and_disabled_feature_do_not_call_remote(self):
        with patch.object(passwords, "_request") as remote:
            for email, password in [
                (None, "pw"),
                ("bad", "pw"),
                ("a@b", ""),
                ("a@b", "x" * 4097),
            ]:
                with self.assertRaises(passwords.PasswordAuthError):
                    passwords.password_sign_in(email, password)
            with patch.dict(os.environ, {"AUTH_PASSWORD_LOCKOUT_ENABLED": "false"}):
                with self.assertRaises(passwords.PasswordAuthError):
                    passwords.password_sign_in("person@example.com", "secret")
            remote.assert_not_called()

    def test_malformed_counter_responses_fail_closed(self):
        for result in [
            {},
            {"allowed": "true", "retry_after": 0},
            {"allowed": True, "retry_after": -1},
            {"allowed": False, "retry_after": 0, "error": "unexpected"},
        ]:
            with patch.object(passwords, "_request", return_value=result):
                with self.assertRaises(passwords.PasswordAuthError):
                    passwords.attempt("a@b", "start")

    def test_transport_uses_public_key_for_password_and_service_key_only_for_rpc(self):
        opener = Mock()
        response = Mock()
        response.read.return_value = b"{}"
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener.open.return_value = response
        with (
            patch(
                "auth.settings",
                return_value=(
                    "https://test.supabase.co",
                    "public",
                    "https://app.example",
                    True,
                ),
            ),
            patch.dict(os.environ, {"SUPABASE_SERVICE_ROLE_KEY": "server-secret"}),
            patch.object(passwords, "build_opener", return_value=opener),
        ):
            passwords._request(
                "/auth/v1/token?grant_type=password", {"password": "private"}
            )
            req = opener.open.call_args.args[0]
            self.assertEqual(req.get_header("Apikey"), "public")
            self.assertIsNone(req.get_header("Authorization"))
            passwords._request("/rest/v1/rpc/qe_password_attempt", {}, privileged=True)
            req = opener.open.call_args.args[0]
            self.assertEqual(req.get_header("Authorization"), "Bearer server-secret")

    def test_only_explicit_invalid_credentials_errors_count(self):
        for payload, status, expected in [
            (b'{"error_code":"invalid_credentials"}', 400, "invalid_credentials"),
            (
                b'{"error_code":"email_not_confirmed"}',
                400,
                "email_confirmation_required",
            ),
            (b'{"error_code":"user_banned"}', 400, "account_suspended"),
            (b"bad response", 400, "auth_unavailable"),
            (b"{}", 429, "rate_limited"),
            (b"{}", 502, "auth_unavailable"),
        ]:
            error = HTTPError(
                "https://test.supabase.co", status, "Error", {}, io.BytesIO(payload)
            )
            opener = Mock()
            opener.open.side_effect = error
            with (
                patch(
                    "auth.settings",
                    return_value=(
                        "https://test.supabase.co",
                        "public",
                        "https://app.example",
                        True,
                    ),
                ),
                patch.object(passwords, "build_opener", return_value=opener),
            ):
                with self.assertRaises(passwords.PasswordAuthError) as caught:
                    passwords._request("/auth/v1/token?grant_type=password", {})
                self.assertEqual(caught.exception.code, expected)


class PasswordRouteTests(unittest.TestCase):
    def setUp(self):
        # Reuse the guarded Flask fixture without inheriting/rerunning unrelated tests.
        self.fixture = auth_fixture.AuthTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.client = self.fixture.client

    def test_origin_rejection_precedes_password_provider(self):
        with patch("auth.password_sign_in") as login:
            response = self.client.post(
                "/auth/password", json={"email": "a@b", "password": "pw"}
            )
            self.assertEqual(response.status_code, 403)
            login.assert_not_called()

    def test_gateway_returns_tokens_without_cookie_and_lockout_has_retry_header(self):
        headers = {"Origin": "https://analytics.example.com"}
        with patch("auth.password_sign_in", return_value=TOKENS):
            response = self.client.post(
                "/auth/password",
                headers=headers,
                json={"email": "a@b", "password": "pw"},
            )
            self.assertEqual(response.json, TOKENS)
            self.assertNotIn("Set-Cookie", response.headers)
            self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        with patch(
            "auth.password_sign_in",
            side_effect=passwords.PasswordAuthError("account_locked", 423, 900),
        ):
            response = self.client.post(
                "/auth/password",
                headers=headers,
                json={"email": "a@b", "password": "pw"},
            )
            self.assertEqual(response.status_code, 423)
            self.assertEqual(response.headers["Retry-After"], "900")

    def test_oversized_and_extra_fields_rejected(self):
        with patch("auth.password_sign_in") as login:
            for body in [
                {"email": "a@b", "password": "pw", "valid": True},
                {"email": "a@b", "password": "x" * 9000},
                [],
            ]:
                response = self.client.post(
                    "/auth/password",
                    headers={"Origin": "https://analytics.example.com"},
                    json=body,
                )
                self.assertEqual(response.status_code, 400)
            login.assert_not_called()

    def test_locked_and_store_unavailable_accounts_cannot_bypass_with_direct_token(
        self,
    ):
        for code, expected in [("account_locked", 403), ("auth_unavailable", 503)]:
            with (
                patch.dict(os.environ, {"AUTH_PASSWORD_LOCKOUT_ENABLED": "true"}),
                self.fixture.remote(auth_fixture.USER),
                patch.object(
                    passwords, "attempt", side_effect=passwords.PasswordAuthError(code)
                ),
            ):
                self.client.set_cookie(auth.COOKIE, auth_fixture.token())
                self.assertEqual(self.client.get("/_dash-layout").status_code, expected)
                self.fixture.loader.assert_not_called()
