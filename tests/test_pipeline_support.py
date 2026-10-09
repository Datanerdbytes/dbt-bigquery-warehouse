"""Offline lifecycle logging and runner regressions."""

import io
import json
import os
import subprocess
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
    def test_dry_run_from_another_directory_does_not_execute_commands(self):
        env = {
            "PATH": os.environ["PATH"],
            "SOURCE_FOLDER": "/tmp/source folder",
            "DB_CONNECTION_STRING": "unused",
            "TARGET_PROJECT": "offline-project",
            "PIPELINE_DRY_RUN": "1",
        }
        result = subprocess.run(
            ["bash", str(ROOT / "run_pipeline.sh")],
            cwd="/tmp",
            env=env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("DRY RUN:"), 5)
        self.assertIn("Scripts/ingest_bronze.py", result.stdout)
        self.assertNotIn("/Users/roelsomido/Source", result.stdout)

    def test_missing_configuration_fails_before_execution(self):
        result = subprocess.run(
            ["bash", str(ROOT / "run_pipeline.sh")],
            env={"PATH": os.environ["PATH"]},
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SOURCE_FOLDER", result.stderr)
        self.assertEqual(result.stdout, "")
