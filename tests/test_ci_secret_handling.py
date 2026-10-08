"""Offline regression checks for CI secret-handling hardening.

These tests parse the workflow YAML statically and assert the safe-handling
guardrails documented in docs/security/ci-secret-handling.md. They use only
non-sensitive synthetic marker strings and never touch a real secret, a hosted
runner, or any cloud resource.

Run from the repository root:
    .venv/bin/python -B -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci_pipeline.yml"

# Synthetic marker used to detect accidental interpolation of the secret VALUE
# (as opposed to the secret NAME) into workflow expressions.
_SECRET_VALUE_MARKER = "GCP_SA_KEY_VALUE_PLACEHOLDER"


def _load_workflow():
    with open(WORKFLOW, "r") as f:
        return yaml.safe_load(f)


def _step_runs(job, step_name):
    for step in job.get("steps", []):
        if step.get("name") == step_name:
            return step
    return None


def _all_run_text(workflow):
    """Concatenate every `run:` block in the workflow for pattern scanning."""
    chunks = []
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []):
            run = step.get("run")
            if isinstance(run, str):
                chunks.append(run)
    return "\n".join(chunks)


class CiSecretHandlingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = _load_workflow()
        cls.run_text = _all_run_text(cls.workflow)
        cls.validate_job = cls.workflow["jobs"]["validate-and-test"]
        cls.deploy_job = cls.workflow["jobs"]["deploy-cloud-run"]

    # -- Secret value must never be echoed or derived in logs ----------------

    def test_no_secret_value_echo_in_run_blocks(self):
        # The secret NAME may appear (for the presence check), but the value must
        # never be printed, and no length/derived form of the value may be logged.
        forbidden = (
            'echo "Secret length',
            "✅ GCP Service Account Key written and validated",
            "Secret length check",
        )
        for snippet in forbidden:
            self.assertNotIn(
                snippet,
                self.run_text,
                msg=f"Unsafe secret-derived echo found in workflow run blocks: {snippet!r}",
            )

    def test_secret_is_only_used_as_env_or_action_input(self):
        raw = WORKFLOW.read_text()
        # The secret must only appear as a registered-secret reference
        # (`secrets.GCP`), never interpolated into a command argument or URL.
        self.assertIn("secrets.GCP", raw)
        # No shell interpolation of the secret into a command string.
        self.assertNotIn("$GCP_SA_KEY", raw)

    def test_no_secret_in_docker_image_tag_or_arguments(self):
        raw = WORKFLOW.read_text()
        self.assertNotIn("secrets.GCP", raw.split("docker build")[1])
        # The image tag must reference the commit SHA, not a secret.
        self.assertIn("github.sha", raw)

    # -- Materialization is restricted and cleaned up -------------------------

    def test_temp_keyfile_is_written_with_restrictive_permissions(self):
        setup = _step_runs(self.validate_job, "Setup GCP & dbt Profile")
        self.assertIsNotNone(setup)
        run = setup.get("run", "")
        self.assertIn("umask 077", run)
        self.assertIn("chmod 600 /tmp/gcp_key.json", run)
        self.assertIn("chmod 600 ~/.dbt/profiles.yml", run)

    def test_cleanup_runs_on_both_success_and_failure(self):
        cleanup = _step_runs(self.validate_job, "Cleanup Service Account Key & Profile")
        self.assertIsNotNone(cleanup)
        self.assertEqual(cleanup.get("if"), "always()")
        run = cleanup.get("run", "")
        self.assertIn("rm -f /tmp/gcp_key.json", run)
        self.assertIn("rm -rf ~/.dbt", run)

    def test_no_artifact_upload_can_carry_credentials(self):
        # No step may upload an artifact that could contain the materialized key.
        for job in self.workflow["jobs"].values():
            for step in job.get("steps", []):
                uses = step.get("uses", "")
                self.assertFalse(
                    uses.startswith("actions/upload-artifact"),
                    msg=f"Artifact upload step found: {step.get('name')!r}",
                )

    # -- Deployment gate and auth action preserved ----------------------------

    def test_deployment_gate_requires_push_to_main(self):
        self.assertEqual(
            self.deploy_job.get("if"),
            "(github.ref == 'refs/heads/main' || github.ref == 'refs/heads/master') "
            "&& github.event_name == 'push'",
        )
        self.assertEqual(self.deploy_job.get("needs"), "validate-and-test")

    def test_google_auth_uses_action_credentials_input(self):
        auth_step = _step_runs(self.deploy_job, "Google Auth")
        self.assertIsNotNone(auth_step)
        self.assertEqual(auth_step.get("uses"), "google-github-actions/auth@v2")
        self.assertEqual(
            auth_step.get("with", {}).get("credentials_json"), "${{ secrets.GCP }}"
        )


if __name__ == "__main__":
    unittest.main()
