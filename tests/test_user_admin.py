"""Offline administrator boundaries, safe projections, and access changes."""

import importlib
import importlib.util
import io
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import g
from plotly.utils import PlotlyJSONEncoder
from test_auth import ENV, USER, AuthTests, token

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))

import auth
import user_admin
from components.sidebar import create_sidebar

OWNER_ID = "11111111-1111-4111-8111-111111111111"
MEMBER_ID = "22222222-2222-4222-8222-222222222222"
ADMIN = dict(USER, id=OWNER_ID, app_metadata={"qe_role": "admin", "qe_owner": True})
MEMBER = dict(USER, id=MEMBER_ID, email="member@example.com", app_metadata={})


class UserAdminTests(unittest.TestCase):
    remote = AuthTests.remote

    def setUp(self):
        AuthTests.setUp(self)
        self.server.add_url_rule(
            "/admin/users", "admin_page_fixture", lambda: self.loader(), methods=["GET"]
        )
        self.network = patch.object(
            user_admin,
            "build_opener",
            side_effect=AssertionError("Live admin access forbidden"),
        )
        self.network.start()
        self.addCleanup(self.network.stop)
        self.client.set_cookie(auth.COOKIE, token())
        self.deletion_guard = patch.object(user_admin, "require_deletion_guard")
        self.deletion_guard_mock = self.deletion_guard.start()
        self.addCleanup(self.deletion_guard.stop)

    def test_member_cannot_view_page_api_or_forge_metadata(self):
        member = dict(MEMBER, user_metadata={"qe_role": "admin", "qe_owner": True})
        with patch.object(user_admin, "_service_request") as service:
            for path in ("/admin/users", "/api/admin/users"):
                with self.remote(member):
                    response = self.client.get(path)
                self.assertEqual(response.status_code, 403)
            with self.remote(member):
                response = self.client.patch(
                    f"/api/admin/users/{MEMBER_ID}",
                    json={"action": "grant_admin"},
                    headers={"Origin": ENV["AUTH_APP_ORIGIN"]},
                )
            self.assertEqual(response.status_code, 403)
            service.assert_not_called()
        self.loader.assert_not_called()

    def test_anonymous_api_is_401_and_page_redirects(self):
        self.client.delete_cookie(auth.COOKIE)
        self.assertEqual(self.client.get("/api/admin/users").status_code, 401)
        self.assertEqual(self.client.get("/admin/users").location, "/login")

    def test_admin_page_and_paginated_safe_directory(self):
        raw = dict(
            MEMBER,
            app_metadata={"secret": "must-not-leak"},
            user_metadata={"secret": "must-not-leak"},
            identities=[{"token": "must-not-leak"}],
        )
        with self.remote(ADMIN):
            self.assertEqual(self.client.get("/admin/users").status_code, 200)
        with (
            self.remote(ADMIN),
            patch.object(
                user_admin, "_service_request", return_value={"users": [raw]}
            ) as service,
        ):
            response = self.client.get("/api/admin/users?page=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.json["users"][0]),
            {
                "id",
                "email",
                "role",
                "owner",
                "verification",
                "access",
                "created_at",
                "last_sign_in_at",
            },
        )
        self.assertNotIn("must-not-leak", response.get_data(as_text=True))
        self.assertFalse(response.json["has_next"])
        service.assert_called_once_with("GET", "?page=2&per_page=25", None)

    def test_page_validation_and_config_fail_closed(self):
        with patch.object(user_admin, "_service_request") as service:
            for page in ("0", "-1", "abc", "100001"):
                with self.remote(ADMIN):
                    self.assertEqual(
                        self.client.get(f"/api/admin/users?page={page}").status_code,
                        400,
                    )
            service.assert_not_called()
        with (
            self.remote(ADMIN),
            patch.dict(os.environ, {"SUPABASE_SERVICE_ROLE_KEY": ""}),
        ):
            response = self.client.get("/api/admin/users")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["error"], "admin_not_configured")

    def test_origin_rejected_before_admin_operation(self):
        with patch.object(user_admin, "_service_request") as service:
            for origin in (None, "https://evil.example.com"):
                response = self.client.patch(
                    f"/api/admin/users/{MEMBER_ID}",
                    json={"action": "suspend"},
                    headers={"Origin": origin} if origin else {},
                )
                self.assertEqual(response.status_code, 403)
            service.assert_not_called()

    def test_suspension_restore_and_roles_use_only_allowed_fields(self):
        expected = {
            "suspend": {
                "ban_duration": "876000h",
                "app_metadata": {"qe_suspended": True},
            },
            "restore": {
                "ban_duration": "none",
                "app_metadata": {"qe_suspended": False},
            },
            "grant_admin": {"app_metadata": {"qe_role": "admin"}},
            "revoke_admin": {"app_metadata": {"qe_role": "member"}},
        }
        for action, body in expected.items():
            with (
                self.subTest(action=action),
                self.remote(ADMIN),
                patch.object(
                    user_admin, "_service_request", side_effect=[MEMBER, MEMBER]
                ) as service,
            ):
                response = self.client.patch(
                    f"/api/admin/users/{MEMBER_ID}",
                    json={"action": action},
                    headers={"Origin": ENV["AUTH_APP_ORIGIN"]},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(service.call_args.args, ("PUT", f"/{MEMBER_ID}", body))

    def test_owner_self_admin_and_unverified_grant_protection(self):
        cases = [
            (ADMIN, "suspend"),
            (
                dict(MEMBER, app_metadata={"qe_role": "admin", "qe_owner": True}),
                "revoke_admin",
            ),
            (dict(MEMBER, app_metadata={"qe_role": "admin"}), "suspend"),
            (dict(MEMBER, email_confirmed_at=None), "grant_admin"),
            (dict(MEMBER, app_metadata={"qe_suspended": True}), "grant_admin"),
        ]
        for target, action in cases:
            with (
                self.subTest(action=action, target=target["id"]),
                self.remote(ADMIN),
                patch.object(
                    user_admin, "_service_request", return_value=target
                ) as service,
            ):
                response = self.client.patch(
                    f"/api/admin/users/{target['id']}",
                    json={"action": action},
                    headers={"Origin": ENV["AUTH_APP_ORIGIN"]},
                )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(service.call_count, 1)
                self.assertEqual(service.call_args.args[0], "GET")

    def test_invalid_action_id_and_extra_fields_cannot_reach_provider(self):
        for user_id, body in [
            (MEMBER_ID, {"action": "delete"}),
            ("../users", {"action": "suspend"}),
            (MEMBER_ID, {"action": "grant_admin", "app_metadata": {"qe_owner": True}}),
        ]:
            with (
                self.remote(ADMIN),
                patch.object(user_admin, "_service_request") as service,
            ):
                response = self.client.patch(
                    f"/api/admin/users/{user_id}",
                    json=body,
                    headers={"Origin": ENV["AUTH_APP_ORIGIN"]},
                )
                self.assertIn(response.status_code, (400, 404))
                service.assert_not_called()

    def test_role_revocation_is_rechecked_with_same_access_cookie(self):
        with (
            self.remote(ADMIN),
            patch.object(user_admin, "_service_request", return_value={"users": []}),
        ):
            self.assertEqual(self.client.get("/api/admin/users").status_code, 200)
        with (
            self.remote(dict(ADMIN, app_metadata={"qe_role": "member"})),
            patch.object(user_admin, "_service_request") as service,
        ):
            self.assertEqual(self.client.get("/api/admin/users").status_code, 403)
            service.assert_not_called()

    def test_suspension_blocks_existing_sessions_and_session_bridge(self):
        suspended = dict(MEMBER, app_metadata={"qe_suspended": True})
        with self.remote(suspended):
            self.assertEqual(self.client.get("/_dash-layout").status_code, 403)
            self.assertEqual(self.client.get("/dashboard").location, "/login")
            response = self.client.post(
                "/auth/session",
                json={"access_token": token()},
                headers={"Origin": ENV["AUTH_APP_ORIGIN"]},
            )
            self.assertEqual(response.status_code, 403)
        self.loader.assert_not_called()

    def test_sidebar_link_only_for_server_verified_admin_role(self):
        for user, visible in [
            (MEMBER, False),
            (ADMIN, True),
            (dict(MEMBER, user_metadata={"qe_role": "admin"}), False),
        ]:
            with self.server.test_request_context():
                g.auth_user = user
                content = json.dumps(create_sidebar(), cls=PlotlyJSONEncoder)
            self.assertEqual("/admin/users" in content, visible)

    def test_service_key_stays_out_of_public_config_and_transport_refuses_redirects(
        self,
    ):
        with patch.dict(
            os.environ, {"SUPABASE_SERVICE_ROLE_KEY": "synthetic-private-key"}
        ):
            response = self.client.get("/auth/config")
            self.assertNotIn("synthetic-private-key", response.get_data(as_text=True))
            with self.server.test_request_context():
                g.auth_user = ADMIN
                transport = Mock()
                transport.open.return_value.__enter__ = Mock(
                    return_value=io.BytesIO(b'{"users": []}')
                )
                transport.open.return_value.__exit__ = Mock(return_value=False)
                with patch.object(
                    user_admin, "build_opener", return_value=transport
                ) as opener:
                    self.assertEqual(user_admin.list_users()["users"], [])
                req = transport.open.call_args.args[0]
                self.assertEqual(
                    req.get_header("Authorization"), "Bearer synthetic-private-key"
                )
                self.assertIsInstance(opener.call_args.args[0], user_admin._NoRedirect)
                self.assertIsNone(
                    opener.call_args.args[0].redirect_request(
                        None, None, 302, "", {}, "https://evil.example.com"
                    )
                )

    def test_provider_failure_is_sanitized(self):
        with self.server.test_request_context():
            g.auth_user = ADMIN
            with (
                patch.dict(
                    os.environ, {"SUPABASE_SERVICE_ROLE_KEY": "synthetic-private-key"}
                ),
                patch.object(
                    user_admin,
                    "build_opener",
                    side_effect=OSError("synthetic-private-key"),
                ),
            ):
                with self.assertRaises(user_admin.AdminError) as error:
                    user_admin.list_users()
            self.assertNotIn("synthetic-private-key", str(error.exception))
            self.assertEqual(error.exception.status, 503)


class UserAdminCallbackTests(unittest.TestCase):
    setUp = AuthTests.setUp
    remote = AuthTests.remote

    @classmethod
    def setUpClass(cls):
        from google.cloud import bigquery

        from utils.cache import cache

        with (
            patch.object(
                bigquery,
                "Client",
                side_effect=AssertionError("Live warehouse forbidden"),
            ),
            patch.object(cache, "init_app"),
        ):
            importlib.import_module("app")
        cls.page = importlib.import_module("pages.user_management")

    def test_layout_is_query_free_and_callbacks_reject_members(self):
        with (
            self.server.test_request_context(),
            patch.object(user_admin, "_service_request") as service,
        ):
            g.auth_user = MEMBER
            content = json.dumps(self.page.layout(), cls=PlotlyJSONEncoder)
            self.assertIn("Admin access required", content)
            rows, _, message, *_ = self.page.load_directory("/admin/users", 1, None, 0)
            self.assertEqual(rows, [])
            self.assertIn("administrators", str(message))
            with self.assertRaises(user_admin.AdminError):
                self.page.selected_account([MEMBER])
            result = self.page.manage_account(
                None,
                None,
                None,
                None,
                None,
                1,
                [],
                {"id": MEMBER_ID, "action": "grant_admin"},
                0,
            )
            self.assertIn("administrators", str(result[5]))
            service.assert_not_called()
        with (
            self.server.test_request_context(),
            patch.object(user_admin, "_service_request") as service,
        ):
            g.auth_user = ADMIN
            self.page.layout()
            service.assert_not_called()

    def test_tampered_callback_target_is_rechecked_before_change(self):
        with (
            self.server.test_request_context(),
            patch.object(
                self.page, "ctx", SimpleNamespace(triggered_id="admin-users-confirm")
            ),
            patch.object(user_admin, "_service_request", return_value=ADMIN) as service,
        ):
            g.auth_user = ADMIN
            result = self.page.manage_account(
                None,
                None,
                None,
                None,
                None,
                1,
                [],
                {"id": OWNER_ID, "action": "revoke_admin"},
                0,
            )
            self.assertFalse(result[0])
            self.assertIn("another administrator", str(result[5]))
            self.assertEqual(service.call_count, 1)


class BootstrapOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "Scripts" / "bootstrap_admin.py"
        spec = importlib.util.spec_from_file_location("bootstrap_admin", path)
        cls.bootstrap_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.bootstrap_module)

    def test_bootstrap_requires_existing_verified_account_and_explicit_apply(self):
        with patch.object(
            self.bootstrap_module, "_service_request", return_value={"users": [MEMBER]}
        ) as service:
            self.bootstrap_module.bootstrap(MEMBER["email"])
            self.assertEqual(service.call_count, 1)
        with patch.object(
            self.bootstrap_module,
            "_service_request",
            side_effect=[{"users": [MEMBER]}, MEMBER],
        ) as service:
            self.bootstrap_module.bootstrap(MEMBER["email"], apply=True)
            self.assertEqual(
                service.call_args.args,
                (
                    "PUT",
                    f"/{MEMBER_ID}",
                    {"app_metadata": {"qe_role": "admin", "qe_owner": True}},
                ),
            )
        for users in ([], [dict(MEMBER, email_confirmed_at=None)], [ADMIN, MEMBER]):
            with patch.object(
                self.bootstrap_module, "_service_request", return_value={"users": users}
            ) as service:
                with self.assertRaises(ValueError):
                    self.bootstrap_module.bootstrap(MEMBER["email"], apply=True)
                self.assertEqual(service.call_count, 1)


class DeleteAccountTests(UserAdminTests):
    def test_suspended_member_requires_email_then_hard_deletes(self):
        target = dict(MEMBER, app_metadata={"qe_suspended": True})
        with (
            self.remote(ADMIN),
            patch.object(
                user_admin, "_service_request", side_effect=[target, {}]
            ) as service,
        ):
            response = self.client.delete(
                f"/api/admin/users/{MEMBER_ID}",
                json={"confirmation_email": MEMBER["email"]},
                headers={"Origin": ENV["AUTH_APP_ORIGIN"]},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["message"], "Account deleted.")
        self.assertEqual(
            service.call_args.args,
            ("DELETE", f"/{MEMBER_ID}", {"should_soft_delete": False}),
        )

    def test_admin_without_owner_flag_cannot_delete(self):
        for actor in (
            MEMBER,
            dict(ADMIN, app_metadata={"qe_role": "admin"}),
            dict(MEMBER, user_metadata={"qe_owner": True, "qe_role": "admin"}),
        ):
            with (
                self.remote(actor),
                patch.object(user_admin, "_service_request") as service,
            ):
                response = self.client.delete(
                    f"/api/admin/users/{MEMBER_ID}",
                    json={"confirmation_email": MEMBER["email"]},
                    headers={"Origin": ENV["AUTH_APP_ORIGIN"]},
                )
            self.assertEqual(response.status_code, 403)
            service.assert_not_called()

    def test_active_owner_self_and_admin_targets_are_protected(self):
        targets = [
            ADMIN,
            dict(MEMBER, app_metadata={"qe_owner": True, "qe_suspended": True}),
            dict(MEMBER, app_metadata={"qe_role": "admin", "qe_suspended": True}),
            MEMBER,
            dict(MEMBER, banned_until="malformed"),
        ]
        for target in targets:
            with (
                self.subTest(target=target),
                self.remote(ADMIN),
                patch.object(
                    user_admin, "_service_request", return_value=target
                ) as service,
            ):
                response = self.client.delete(
                    f"/api/admin/users/{target['id']}",
                    json={"confirmation_email": target["email"]},
                    headers={"Origin": ENV["AUTH_APP_ORIGIN"]},
                )
                self.assertIn(response.status_code, (403, 409))
                self.assertFalse(
                    any(c.args[0] == "DELETE" for c in service.call_args_list)
                )

    def test_mismatched_email_and_invalid_bodies_never_delete(self):
        target = dict(MEMBER, app_metadata={"qe_suspended": True})
        bodies = [
            None,
            {},
            {"confirmation_email": None},
            {"confirmation_email": "wrong@example.com"},
            {"confirmation_email": MEMBER["email"], "should_soft_delete": False},
        ]
        for body in bodies:
            with (
                self.subTest(body=body),
                self.remote(ADMIN),
                patch.object(
                    user_admin, "_service_request", return_value=target
                ) as service,
            ):
                response = self.client.delete(
                    f"/api/admin/users/{MEMBER_ID}",
                    json=body,
                    headers={"Origin": ENV["AUTH_APP_ORIGIN"]},
                )
                self.assertEqual(response.status_code, 400)
                self.assertFalse(
                    any(c.args[0] == "DELETE" for c in service.call_args_list)
                )

    def test_delete_requires_exact_origin_before_any_provider_call(self):
        with patch.object(user_admin, "_service_request") as service:
            for origin in (None, "https://evil.example.com"):
                response = self.client.delete(
                    f"/api/admin/users/{MEMBER_ID}",
                    json={"confirmation_email": MEMBER["email"]},
                    headers={"Origin": origin} if origin else {},
                )
                self.assertEqual(response.status_code, 403)
            service.assert_not_called()

    def test_deleted_or_changed_target_is_rechecked_at_confirmation(self):
        # A target restored or renamed after the dialog opened is not deletable.
        for target in (
            MEMBER,
            dict(
                MEMBER, email="renamed@example.com", app_metadata={"qe_suspended": True}
            ),
        ):
            with (
                self.remote(ADMIN),
                patch.object(
                    user_admin, "_service_request", return_value=target
                ) as service,
            ):
                response = self.client.delete(
                    f"/api/admin/users/{MEMBER_ID}",
                    json={"confirmation_email": MEMBER["email"]},
                    headers={"Origin": ENV["AUTH_APP_ORIGIN"]},
                )
                self.assertIn(response.status_code, (400, 409))
                self.assertEqual(service.call_count, 1)
        with (
            self.remote(ADMIN),
            patch.object(
                user_admin,
                "_service_request",
                side_effect=user_admin.AdminError("user_not_found", 404),
            ) as service,
        ):
            response = self.client.delete(
                f"/api/admin/users/{MEMBER_ID}",
                json={"confirmation_email": MEMBER["email"]},
                headers={"Origin": ENV["AUTH_APP_ORIGIN"]},
            )
            self.assertEqual(response.status_code, 404)
            self.assertEqual(service.call_count, 1)

    def test_empty_delete_response_and_timeout_do_not_retry(self):
        with (
            self.server.test_request_context(),
            patch.dict(
                os.environ, {"SUPABASE_SERVICE_ROLE_KEY": "synthetic-private-key"}
            ),
        ):
            g.auth_user = ADMIN
            transport = Mock()
            transport.open.return_value.__enter__ = Mock(return_value=io.BytesIO(b""))
            transport.open.return_value.__exit__ = Mock(return_value=False)
            with patch.object(user_admin, "build_opener", return_value=transport):
                self.assertEqual(
                    user_admin._admin_request(
                        "DELETE", f"/{MEMBER_ID}", {"should_soft_delete": False}
                    ),
                    {},
                )
            transport.open.side_effect = TimeoutError("synthetic-private-key")
            transport.open.reset_mock()
            with (
                patch.object(user_admin, "build_opener", return_value=transport),
                self.assertRaises(user_admin.AdminError) as error,
            ):
                user_admin._admin_request(
                    "DELETE", f"/{MEMBER_ID}", {"should_soft_delete": False}
                )
            self.assertEqual(error.exception.code, "delete_unconfirmed")
            self.assertNotIn("synthetic-private-key", str(error.exception))
            transport.open.assert_called_once()

    def test_provider_blocked_delete_is_actionable_without_cleanup(self):
        from urllib.error import HTTPError

        for status, expected in ((409, "delete_blocked"), (500, "delete_unconfirmed")):
            with (
                self.subTest(status=status),
                self.server.test_request_context(),
                patch.dict(
                    os.environ, {"SUPABASE_SERVICE_ROLE_KEY": "synthetic-private-key"}
                ),
            ):
                g.auth_user = ADMIN
                transport = Mock()
                transport.open.side_effect = HTTPError(
                    "synthetic", status, "foreign key details", {}, None
                )
                with (
                    patch.object(user_admin, "build_opener", return_value=transport),
                    self.assertRaises(user_admin.AdminError) as error,
                ):
                    user_admin._admin_request(
                        "DELETE", f"/{MEMBER_ID}", {"should_soft_delete": False}
                    )
                self.assertEqual(error.exception.code, expected)
                self.assertNotIn("foreign key details", str(error.exception))
                transport.open.assert_called_once()


class DeleteAccountCallbackTests(UserAdminCallbackTests):
    def test_forged_delete_callback_cannot_promote_owner(self):
        with (
            self.server.test_request_context(),
            patch.object(user_admin, "_service_request") as service,
        ):
            g.auth_user = dict(ADMIN, app_metadata={"qe_role": "admin"})
            self.assertTrue(
                self.page.deletion_available([dict(MEMBER, access="Suspended")])
            )
            result = self.page.manage_deletion(
                None,
                None,
                1,
                [],
                {"id": MEMBER_ID, "email": MEMBER["email"]},
                MEMBER["email"],
                0,
            )
            self.assertFalse(result[0])
            self.assertIn("owner", str(result[5]))
            service.assert_not_called()

    def test_cancel_delete_does_not_call_provider(self):
        with (
            self.server.test_request_context(),
            patch.object(
                self.page,
                "ctx",
                SimpleNamespace(triggered_id="admin-users-delete-cancel"),
            ),
            patch.object(user_admin, "_service_request") as service,
        ):
            g.auth_user = ADMIN
            result = self.page.manage_deletion(
                None,
                1,
                None,
                [],
                {"id": MEMBER_ID, "email": MEMBER["email"]},
                MEMBER["email"],
                0,
            )
            self.assertFalse(result[0])
            self.assertIsNone(result[1])
            service.assert_not_called()


class DeletionGuardTests(unittest.TestCase):
    def test_missing_disabled_or_unavailable_guard_fails_closed(self):
        from password_auth import PasswordAuthError

        for status in [{"ready": False}, {}, PasswordAuthError("auth_unavailable")]:
            with (
                patch.object(user_admin, "require_owner"),
                patch(
                    "password_auth._request",
                    side_effect=status if isinstance(status, Exception) else None,
                    return_value=status,
                ),
            ):
                with self.assertRaises(user_admin.AdminError) as caught:
                    user_admin.require_deletion_guard()
                self.assertEqual(caught.exception.code, "delete_guard_required")

    def test_guard_readiness_requires_owner_and_exact_true(self):
        with (
            patch.object(user_admin, "require_owner") as owner,
            patch("password_auth._request", return_value={"ready": True}) as service,
        ):
            user_admin.require_deletion_guard()
            owner.assert_called_once()
            service.assert_called_once_with(
                "/rest/v1/rpc/qe_account_deletion_guard_ready", {}, privileged=True
            )

    def test_delete_never_reaches_provider_when_guard_is_missing(self):
        with (
            patch.object(user_admin, "deletion_target", return_value=MEMBER),
            patch.object(
                user_admin,
                "require_deletion_guard",
                side_effect=user_admin.AdminError("delete_guard_required", 503),
            ),
            patch.object(user_admin, "_admin_request") as service,
        ):
            with self.assertRaises(user_admin.AdminError):
                user_admin.delete_account(MEMBER_ID, MEMBER["email"])
            service.assert_not_called()
