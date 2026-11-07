# CI Credential Handling

This document describes the credential posture of the CI/CD pipeline
(`.github/workflows/ci_pipeline.yml`) and the guardrails that keep sensitive
values out of logs, artifacts, caches, step summaries, and debug bundles.

## Credential Sources

**There are none.** The BigQuery warehouse this project built against was
deleted, so the pipeline no longer holds, references, or needs any cloud
credential:

- The dbt build runs against a local DuckDB file. The bronze tables are
  loaded from the versioned source CSVs in `data/raw/`, and the profile in
  `analytics_layer/profiles.yml` resolves every path from an environment
  variable — it contains no key material.
- The `deploy-cloud-run` job and the `google-github-actions/auth` step were
  removed along with the deleted GCP project.
- The Vercel `deploy` job was removed on 2026-11-07. The repository's Vercel
  Git integration owns production, so CI no longer reads the `VERCEL_TOKEN`
  secret and holds no deployment credential.
- The Supabase configuration used by the dashboard is public (anon key only)
  and is never injected as a CI secret.

## Guardrails

These are enforced by `tests/test_ci_secret_handling.py`, which parses the
workflow YAML statically and never touches a real secret or a hosted runner:

- **No cloud credential reference.** The workflow must not mention
  `secrets.GCP`, `GOOGLE_APPLICATION_CREDENTIALS`, a `credentials_json` action
  input, or any materialized keyfile path.
- **No ambient cloud authentication.** No step may configure a cloud auth
  action, and no step may invoke `gcloud`, `bq`, or `gsutil` — those would
  authenticate with whatever credentials the runner happened to have.
- **No credential file is materialized.** Nothing may write a keyfile into the
  workspace or into `~/.dbt/`, so a failed job cannot leave credential
  material behind for a later step.
- **No secret-bearing artifacts.** The workflow uploads no artifacts and
  configures no caches, so nothing can carry credential material off the
  runner.
- **The committed dbt profile holds no key material.** Its `keyfile` entry —
  in the retained BigQuery target, which is not used by CI — must resolve
  through an environment variable, never a literal path or key.

## Limits of GitHub Secret Masking

GitHub Actions automatically masks registered secrets (`***`) in job logs, but
this protection has well-known limits:

- Masking applies to the **exact secret string**. A transformed or derived value
  (base64-encoded, JSON-parsed, substring, checksum, or wrapped form) is **not**
  masked and can leak if printed.
- Masking is applied to log output, not to artifacts, caches, step summaries, or
  files written to the workspace. A secret written to a file that is later
  archived or uploaded is still exposed.
- Masking does not prevent a job from failing in a way that prints surrounding
  context, or from printing the secret inside a larger string where the exact
  match is broken by escaping or concatenation.

The current posture sidesteps all of this by holding no secret at all. If a
credential is ever reintroduced — for example a Vercel deploy token or a
registry login — these limits apply again, and the pipeline should avoid
relying on masking alone: it must not print the secret or any derived form of
it.

## Verification

Local verification uses only the static workflow parse described above. A local
harness **cannot** prove that GitHub masks secrets on a hosted runner, and this
document makes no such claim. Any reintroduced secret must be reviewed in
GitHub Actions to confirm masking behavior there.

## Related

- [GitHub secret redaction and its limits](https://docs.github.com/en/actions/concepts/security/secrets)
- [GitHub Actions secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)
