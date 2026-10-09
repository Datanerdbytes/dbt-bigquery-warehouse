"""Offline dbt hook preparation never executes a warehouse command."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Scripts import prepare_dbt_checks as checks


class DbtValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        (self.project / "package-lock.yml").write_text(
            "packages:\n  - package: dbt-labs/dbt_utils\n    name: dbt_utils\n    version: 1.4.1\nsha1_hash: dummy\n"
        )
        (self.project / "packages.yml").write_text(
            "packages:\n  - package: dbt-labs/dbt_utils\n    version: 1.4.1\n"
        )
        self.commands = []

    def run_dbt(self, args, **kwargs):
        command = args[5]
        self.commands.append(command)
        self.assertEqual(kwargs["cwd"], Path(args[args.index("--project-dir") + 1]))
        env = kwargs["env"]
        self.assertEqual(env["DBT_SEND_ANONYMOUS_USAGE_STATS"], "false")
        self.assertNotIn("GCP_KEY_PATH", env)
        self.assertNotIn("DBT_ENV_SECRET_PASSWORD", env)
        self.assertNotIn("DBT_PROFILES_DIR", env)
        profiles = Path(args[args.index("--profiles-dir") + 1])
        self.assertNotEqual(profiles, Path.home() / ".dbt")
        self.assertIn("dbt-offline-validation", (profiles / "profiles.yml").read_text())
        if command == "deps":
            package = kwargs["cwd"] / "dbt_packages" / "dbt_utils"
            package.mkdir(parents=True, exist_ok=True)
            (package / "dbt_project.yml").write_text("name: dbt_utils\n")
        elif command == "parse":
            (self.project / "target" / "manifest.json").write_text('{"fresh": true}')
        else:
            self.fail(f"Forbidden dbt command {command}")

    def test_bootstrap_precedes_parse_and_reuses_matching_packages(self):
        with (
            patch.dict(
                os.environ,
                {
                    "GCP_KEY_PATH": "production.json",
                    "DBT_ENV_SECRET_PASSWORD": "secret",
                    "DBT_PROFILES_DIR": "/production",
                },
            ),
            patch.object(checks.subprocess, "run", side_effect=self.run_dbt),
        ):
            checks.prepare(self.project)
            self.assertEqual(self.commands, ["deps", "parse"])
            self.commands.clear()
            checks.prepare(self.project)
            self.assertEqual(self.commands, ["parse"])
            (self.project / "packages.yml").write_text("packages: []\n")
            self.commands.clear()
            checks.prepare(self.project)
            self.assertEqual(self.commands, ["deps", "parse"])

    def test_failed_parse_removes_stale_manifest(self):
        def fail_parse(args, **kwargs):
            if args[5] == "parse":
                raise subprocess.CalledProcessError(1, args)
            return self.run_dbt(args, **kwargs)

        (self.project / "target").mkdir()
        (self.project / "target" / "manifest.json").write_text("stale")
        with (
            patch.object(checks.subprocess, "run", side_effect=fail_parse),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            checks.prepare(self.project)
        self.assertFalse((self.project / "target" / "manifest.json").exists())

    def test_bootstrap_uses_exact_pins_without_touching_repository_lock(self):
        original = (self.project / "package-lock.yml").read_bytes()

        def inspect(args, **kwargs):
            self.run_dbt(args, **kwargs)
            if args[5] == "deps":
                self.assertNotEqual(kwargs["cwd"], self.project)
                contents = (kwargs["cwd"] / "packages.yml").read_text()
                self.assertIn("version: 1.4.1", contents)

        with patch.object(checks.subprocess, "run", side_effect=inspect):
            checks.prepare(self.project)
        self.assertEqual((self.project / "package-lock.yml").read_bytes(), original)

    def test_failed_deps_removes_stale_manifest(self):
        (self.project / "target").mkdir()
        manifest = self.project / "target" / "manifest.json"
        manifest.write_text("stale")
        with (
            patch.object(
                checks.subprocess,
                "run",
                side_effect=subprocess.CalledProcessError(1, "deps"),
            ),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            checks.prepare(self.project)
        self.assertFalse(manifest.exists())

    def test_changed_package_cache_removes_obsolete_files(self):
        with patch.object(checks.subprocess, "run", side_effect=self.run_dbt):
            checks.prepare(self.project)
            obsolete = self.project / "dbt_packages" / "dbt_utils" / "old_macro.sql"
            obsolete.write_text("obsolete")
            (self.project / "dbt_packages" / ".validation-lock.sha256").unlink()
            checks.prepare(self.project)
        self.assertFalse(obsolete.exists())

    def test_main_failure_returns_nonzero(self):
        with (
            patch.object(checks, "prepare", side_effect=RuntimeError("parse failed")),
            patch("sys.stderr"),
        ):
            self.assertEqual(checks.main(), 1)
