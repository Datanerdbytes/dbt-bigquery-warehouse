"""Offline checks for the Supabase deployment contract.

The keep-wake route keeps a free Supabase project from pausing, and the SQL
migrations hold the guards the app relies on. Both are easy to break without
any test failing, so the pairing between the code and the migrations is
checked here.
"""

import io
import json
import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "my-dash-app"))
import auth  # noqa: E402
import keepawake  # noqa: E402

ENV = {
    "NEXT_PUBLIC_SUPABASE_URL": "https://example.supabase.co",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY": "anon-key",  # pragma: allowlist secret (fixture)
    "AUTH_APP_ORIGIN": "https://analytics.example.com",
    "AUTH_PASSWORD_LOCKOUT_ENABLED": "false",  # pragma: allowlist secret (fixture)
}
SERVICE_ROLE_KEY = "service-role-key"  # pragma: allowlist secret (fixture)
CRON_SECRET = "cron-secret-value"  # pragma: allowlist secret (fixture)


def response(payload, status=200):
    """Build a urlopen result that carries a JSON body."""
    result = Mock()
    result.status = status
    result.__enter__ = Mock(side_effect=lambda: io.StringIO(json.dumps(payload)))
    result.__exit__ = Mock(return_value=False)
    return result


class KeepAwakeTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(
            os.environ,
            {
                **ENV,
                "SUPABASE_SERVICE_ROLE_KEY": SERVICE_ROLE_KEY,
                "CRON_SECRET": CRON_SECRET,
            },
        )
        env.start()
        self.addCleanup(env.stop)
        self.server = Flask(__name__)
        auth.install_auth(self.server)
        keepawake.install_keepawake(self.server)
        self.client = self.server.test_client()

    def get(self, secret=CRON_SECRET):
        headers = {"Authorization": f"Bearer {secret}"} if secret else {}
        return self.client.get("/keepawake", headers=headers)

    def test_the_route_is_public_and_never_redirects(self):
        # A cron request has no session cookie. A redirect would end the
        # invocation without reaching Supabase.
        unauthenticated = self.get(secret=None)
        self.assertEqual(unauthenticated.status_code, 401)
        self.assertNotIn(unauthenticated.status_code, (301, 302, 307, 308))
        self.assertIn("/keepawake", auth.PUBLIC)

    def test_a_wrong_secret_is_rejected_before_any_query(self):
        with patch.object(keepawake, "urlopen") as remote:
            response = self.get(secret="not-the-secret")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "unauthorized")
        remote.assert_not_called()

    def test_an_unset_secret_fails_closed(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CRON_SECRET", None)
            with patch.object(keepawake, "urlopen") as remote:
                response = self.get(secret=None)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"], "keepawake_not_configured")
        remote.assert_not_called()

    def test_the_query_uses_the_service_role_key(self):
        with patch.object(keepawake, "urlopen", return_value=response([])) as remote:
            result = self.get()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json(), {"status": "ok", "rows": 0})
        request = remote.call_args.args[0]
        self.assertEqual(
            request.full_url.split("?")[0],
            f"{ENV['NEXT_PUBLIC_SUPABASE_URL']}/rest/v1/qe_password_attempts",
        )
        self.assertEqual(
            request.get_header("Authorization"), f"Bearer {SERVICE_ROLE_KEY}"
        )
        self.assertNotIn(
            ENV["NEXT_PUBLIC_SUPABASE_ANON_KEY"], request.get_header("Authorization")
        )

    def test_a_missing_table_reports_the_migrations(self):
        error = HTTPError(
            "https://example.supabase.co/rest/v1/qe_password_attempts",
            404,
            "Not Found",
            {},
            None,
        )
        with patch.object(keepawake, "urlopen", side_effect=error):
            result = self.get()
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.get_json()["error"], "migrations_missing")

    def test_a_rejected_service_role_key_is_reported(self):
        error = HTTPError(
            "https://example.supabase.co/rest/v1/qe_password_attempts",
            401,
            "Unauthorized",
            {},
            None,
        )
        with patch.object(keepawake, "urlopen", side_effect=error):
            result = self.get()
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.get_json()["error"], "service_role_rejected")

    def test_an_unreachable_project_is_reported(self):
        with patch.object(keepawake, "urlopen", side_effect=OSError("no route")):
            result = self.get()
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.get_json()["error"], "supabase_unreachable")

    def test_a_missing_service_role_key_stops_the_query(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)
            with patch.object(keepawake, "urlopen") as remote:
                result = self.get()
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.get_json()["error"], "service_role_not_configured")
        remote.assert_not_called()


class CronConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))

    def test_the_cron_targets_the_keep_wake_route(self):
        crons = self.config.get("crons")
        self.assertTrue(crons, "no cron job is configured")
        paths = [cron["path"] for cron in crons]
        self.assertIn("/keepawake", paths)
        self.assertIn("/keepawake", auth.PUBLIC)

    def test_the_schedule_runs_once_a_day(self):
        # The Hobby plan only accepts daily schedules, and one run a day is
        # what keeps the free project inside the seven-day idle window.
        for cron in self.config["crons"]:
            self.assertRegex(cron["schedule"], r"^\d+ \d+ \* \* \*$")


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.migrations = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
        self.sources = {
            "password_auth.py": (ROOT / "my-dash-app" / "password_auth.py").read_text(
                encoding="utf-8"
            ),
            "user_admin.py": (ROOT / "my-dash-app" / "user_admin.py").read_text(
                encoding="utf-8"
            ),
        }
        self.script = (ROOT / "Scripts" / "verify_supabase_setup.py").read_text(
            encoding="utf-8"
        )

    def defined_functions(self):
        names = set()
        for migration in self.migrations:
            text = migration.read_text(encoding="utf-8")
            names.update(
                re.findall(r"create function public\.(\w+)\s*\(", text, re.IGNORECASE)
            )
        return names

    def called_functions(self):
        names = set()
        for text in list(self.sources.values()) + [self.script]:
            names.update(re.findall(r"/rest/v1/rpc/(\w+)", text))
            names.update(re.findall(r'"(\w+_ready)"\s*:', text))
        return names

    def test_every_called_rpc_is_defined_by_a_migration(self):
        defined = self.defined_functions()
        called = self.called_functions()
        self.assertTrue(called, "no RPC call was found to check")
        self.assertEqual(called - defined, set())

    def test_every_called_rpc_is_granted_to_the_service_role(self):
        for name in self.called_functions():
            grants = [
                migration
                for migration in self.migrations
                if f"grant execute on function public.{name}"
                in migration.read_text(encoding="utf-8")
            ]
            self.assertTrue(
                grants, f"{name} is not granted to the service role by a migration"
            )

    def test_the_migrations_are_ordered_and_committed(self):
        self.assertEqual(len(self.migrations), 3)
        for migration in self.migrations:
            text = migration.read_text(encoding="utf-8")
            self.assertTrue(text.rstrip().endswith("commit;"), migration.name)
            self.assertIn("revoke all on", text)

    def test_the_lockout_table_backs_the_keep_wake_query(self):
        text = (self.migrations[0]).read_text(encoding="utf-8")
        self.assertIn("create table public.qe_password_attempts", text)
        self.assertIn(keepawake.LOCKOUT_TABLE, text)


if __name__ == "__main__":
    unittest.main()
