"""Exercise CI's actual shell gates with scanner failures and findings."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github/workflows/security_dependency_audit.yml"
)


class DependencyAuditWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]

    def step(self, job, name):
        return next(s for s in self.jobs[job]["steps"] if s["name"] == name)

    def run_shell(self, script, cwd, **env):
        return subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", script],
            cwd=cwd,
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            check=False,
        )

    def test_python_gate_accepts_clean_and_rejects_findings_or_errors(self):
        script = self.step("python-audit", "Enforce Python audit result")["run"]
        cases = [
            ("0", {"dependencies": [{"name": "safe", "vulns": []}]}, True),
            (
                "0",
                {"dependencies": [{"name": "unsafe", "vulns": [{"id": "example"}]}]},
                False,
            ),
            ("1", {"dependencies": [{"vulns": [{"id": "example"}]}]}, False),
            ("2", None, False),
            ("", None, False),
            ("0", None, False),
            ("0", {"error": "scanner failed"}, False),
        ]
        for status, report, passes in cases:
            with (
                self.subTest(status=status, report=report),
                tempfile.TemporaryDirectory() as tmp,
            ):
                if report is not None:
                    Path(tmp, "pip-audit-results.json").write_text(json.dumps(report))
                result = self.run_shell(script, tmp, AUDIT_STATUS=status)
                self.assertEqual(result.returncode == 0, passes, result.stderr)

    def test_scan_preserves_exit_status_and_upload_runs_after_failure(self):
        script = self.step("python-audit", "Run pip-audit")["run"]
        for status in (0, 1, 2):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                executable = Path(tmp, "uv")
                executable.write_text(f"#!/bin/bash\nexit {status}\n")
                executable.chmod(0o755)
                output = Path(tmp, "output")
                result = self.run_shell(
                    script,
                    tmp,
                    PATH=f"{tmp}:{os.environ['PATH']}",
                    GITHUB_OUTPUT=str(output),
                )
                self.assertEqual(result.returncode, 0)
                self.assertEqual(output.read_text().strip(), f"status={status}")
        self.assertEqual(
            self.step("python-audit", "Upload pip-audit results")["if"], "always()"
        )
        self.assertEqual(
            self.step("npm-audit", "Upload npm audit results")["if"], "always()"
        )

    def test_summary_reports_missing_artifacts_and_failed_jobs(self):
        script = self.step("summary", "Print summary")["run"]
        for missing, python_result, passes in [
            (False, "success", True),
            (True, "failure", False),
            (False, "failure", False),
        ]:
            with (
                self.subTest(missing=missing, result=python_result),
                tempfile.TemporaryDirectory() as tmp,
            ):
                npm_dir = Path(tmp, "npm-audit")
                npm_dir.mkdir()
                (npm_dir / "npm-audit-results.json").write_text(
                    '{"vulnerabilities":{}}'
                )
                if not missing:
                    python_dir = Path(tmp, "python-audit")
                    python_dir.mkdir()
                    (python_dir / "pip-audit-results.json").write_text(
                        '{"dependencies":[{"vulns":[]}]}'
                    )
                result = self.run_shell(
                    script, tmp, PYTHON_RESULT=python_result, NPM_RESULT="success"
                )
                self.assertEqual(result.returncode == 0, passes, result.stderr)
                self.assertIn("npm vulnerable packages: 0", result.stdout)
                if missing:
                    self.assertIn("Python audit report unavailable", result.stdout)


if __name__ == "__main__":
    unittest.main()
