"""Offline lifecycle logging and runner regressions."""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from utils.audit_logger import AuditLogger

ROOT = Path(__file__).resolve().parents[1]


class AuditLoggerTests(unittest.TestCase):
    def test_json_events_redact_nested_secrets_and_preserve_types(self):
        stream = io.StringIO()
        logger = AuditLogger(stream)
        with patch(
            "utils.audit_logger.bigquery.Client", side_effect=AssertionError("offline")
        ):
            logger.log_start(
                "ingestion",
                {"connection_string": "private", "nested": {"token": "private"}},
            )
            logger.log_success("ingestion", {"rows": 3})
            logger.log_failure("ingestion", ValueError("password=privatepassword"), {})
        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(
            [row["event"] for row in records], ["start", "success", "failure"]
        )
        self.assertEqual(records[1]["details"]["rows"], 3)
        self.assertNotIn("private", stream.getvalue())
        for row in records:
            self.assertEqual(set(row), {"timestamp", "script", "event", "details"})
            self.assertIsNotNone(datetime.fromisoformat(row["timestamp"]).tzinfo)


class PipelineRunnerTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        shutil.copy(ROOT / "run_pipeline.sh", self.root / "run_pipeline.sh")
        (self.root / "analytics_layer").mkdir()
        # Never dispatch ingestion even if a runner regression reaches uv.
        self.marker = self.root / "unexpected-command"
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        uv = bin_dir / "uv"
        uv.write_text(f'#!/bin/sh\ntouch "{self.marker}"\nexit 99\n')
        uv.chmod(0o755)
        self.path = str(bin_dir) + os.pathsep + os.environ["PATH"]

    def test_dry_run_from_another_directory_does_not_execute_commands(self):
        env = {
            "PATH": self.path,
            "SOURCE_FOLDER": "/tmp/source folder",
            "DB_CONNECTION_STRING": "unused",
            "TARGET_PROJECT": "offline-project",
            "PIPELINE_DRY_RUN": "1",
        }
        result = subprocess.run(
            ["bash", str(self.root / "run_pipeline.sh")],
            cwd="/tmp",
            env=env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("DRY RUN:"), 5)
        self.assertFalse(self.marker.exists())
        self.assertIn("Scripts/ingest_bronze.py", result.stdout)
        self.assertNotIn("/Users/roelsomido/Source", result.stdout)

    def test_dotenv_loaded_before_validation_and_external_values_win(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copy(ROOT / "run_pipeline.sh", root / "run_pipeline.sh")
            (root / "analytics_layer").mkdir()
            (root / ".venv").symlink_to(sys.prefix, target_is_directory=True)
            (root / ".env").write_text(
                "SOURCE_FOLDER='/tmp/source with spaces'\n"
                "DB_CONNECTION_STRING=unused\n"
                "TARGET_PROJECT=dotenv-project\n"
                "PIPELINE_DRY_RUN=1\n"
                "DBT_PROJECT_DIR=./analytics_layer\n"
            )
            env = {"PATH": self.path, "SOURCE_FOLDER": "/tmp/external-source"}
            result = subprocess.run(
                ["bash", str(root / "run_pipeline.sh")],
                cwd="/tmp",
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.count("DRY RUN:"), 5)
            # Prove external variables survive dotenv parsing.
            helper = root / "inspect.py"
            helper.write_text("import os; print(os.environ['SOURCE_FOLDER'])")
            runner = (
                (root / "run_pipeline.sh")
                .read_text()
                .replace(
                    "run uv run Scripts/ingest_bronze.py",
                    f'"{sys.executable}" "{helper}"',
                )
            )
            (root / "run_pipeline.sh").write_text(runner)
            result = subprocess.run(
                ["bash", str(root / "run_pipeline.sh")],
                cwd="/tmp",
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("/tmp/external-source", result.stdout)

    def test_missing_configuration_fails_before_execution(self):
        env = {"PATH": self.path}
        for missing, value in (
            ("SOURCE_FOLDER", "/tmp/offline-source"),
            ("DB_CONNECTION_STRING", "unused"),
            ("TARGET_PROJECT", "offline-project"),
        ):
            with self.subTest(missing=missing):
                result = subprocess.run(
                    ["bash", str(self.root / "run_pipeline.sh")],
                    env=env,
                    text=True,
                    capture_output=True,
                    timeout=10,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(missing, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertFalse(self.marker.exists())
            env[missing] = value
