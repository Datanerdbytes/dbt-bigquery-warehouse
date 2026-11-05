"""Offline regression checks for CI credential handling.

The warehouse this project used to build against is gone, so CI no longer
holds any cloud credential: the dbt build runs against a local DuckDB file
loaded from the versioned source CSVs. These tests pin that posture — they
parse the workflow YAML statically and assert that no service-account secret
can creep back in, that no credential file is materialized in the workspace,
and that nothing uploads an artifact that could carry one.

Run from the repository root:
    .venv/bin/python -B -m unittest discover -s tests -v
"""

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci_pipeline.yml"
DBT_PROFILES = ROOT / "analytics_layer" / "profiles.yml"

# Any of these appearing in the workflow would reintroduce a cloud credential.
_FORBIDDEN_CREDENTIAL_REFERENCES = (
    "secrets.GCP",
    "secrets.GCP_SA_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "credentials_json",
    "gcp_key.json",
    "GCP_SA_KEY",
)

# Commands that would authenticate to a cloud API using ambient credentials.
_FORBIDDEN_COMMANDS = ("gcloud ", "bq ", "gsutil ")


def _load_workflow():
    with open(WORKFLOW) as f:
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


class CiCredentialHandlingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = _load_workflow()
        cls.raw = WORKFLOW.read_text()
        cls.run_text = _all_run_text(cls.workflow)
        cls.validate_job = cls.workflow["jobs"]["validate-and-test"]

    # -- No cloud credential may exist in CI ---------------------------------

    def test_workflow_references_no_cloud_credential(self):
        for reference in _FORBIDDEN_CREDENTIAL_REFERENCES:
            self.assertNotIn(
                reference,
                self.raw,
                msg=f"Cloud credential reference found in workflow: {reference!r}",
            )

    def test_workflow_runs_no_cloud_cli(self):
        for command in _FORBIDDEN_COMMANDS:
            self.assertNotIn(
                command,
                self.run_text,
                msg=f"Cloud CLI invocation found in workflow: {command!r}",
            )

    def test_no_credential_file_is_materialized(self):
        # A keyfile written into the workspace would survive a failed job and
        # could be picked up by a later step or an uploaded artifact.
        for pattern in (r"/tmp/\S*\.json", r"\.dbt/profiles\.yml"):
            self.assertIsNone(
                re.search(pattern, self.run_text),
                msg=f"Credential materialization pattern found: {pattern!r}",
            )

    def test_no_artifact_upload_can_carry_credentials(self):
        for job in self.workflow["jobs"].values():
            for step in job.get("steps", []):
                uses = step.get("uses", "")
                self.assertFalse(
                    uses.startswith("actions/upload-artifact"),
                    msg=f"Artifact upload step found: {step.get('name')!r}",
                )

    def test_no_ambient_cloud_authentication_is_configured(self):
        for step in self.validate_job.get("steps", []):
            self.assertNotIn(
                "google-github-actions/auth",
                step.get("uses", ""),
                msg=f"Google auth action found in: {step.get('name')!r}",
            )

    # -- The dbt build must stay offline -------------------------------------

    def test_dbt_build_uses_the_duckdb_target(self):
        step = _step_runs(
            self.validate_job, "Build bronze and run the dbt pipeline offline"
        )
        self.assertIsNotNone(step)
        run = step.get("run", "")
        self.assertIn("load_bronze_duckdb.py", run)
        self.assertIn("dbt build", run)
        self.assertIn("--profiles-dir .", run)

    def test_committed_dbt_profile_holds_no_key_material(self):
        profiles = DBT_PROFILES.read_text()
        self.assertNotIn("-----BEGIN", profiles)
        self.assertNotIn("private_key", profiles)
        # Every credential path is an environment reference, never a literal.
        self.assertNotRegex(profiles, r"keyfile:(?!\s*\"\{\{)")


if __name__ == "__main__":
    unittest.main()
