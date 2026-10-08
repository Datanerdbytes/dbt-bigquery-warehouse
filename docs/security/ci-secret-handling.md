# CI Secret Handling

This document describes how the CI/CD pipeline (`.github/workflows/ci_pipeline.yml`)
handles sensitive credentials, the limits of GitHub's automatic secret masking, and
the guardrails that keep derived or transformed secret values out of logs, artifacts,
caches, step summaries, and debug bundles.

## Credential Sources

The only credential-bearing input in this pipeline is the repository secret
`secrets.GCP` (a GCP service-account JSON key). It is injected in two places:

1. `validate-and-test` → `Setup GCP & dbt Profile` step, as the `GCP_SA_KEY`
   environment variable, used to materialize a temporary keyfile for dbt.
2. `deploy-cloud-run` → `Google Auth` step, passed as `credentials_json` to the
   `google-github-actions/auth@v2` action.

No other secret, API key, token, or password is referenced by the workflow. The
Supabase configuration used by the dashboard is public (anon key only) and is not
injected as a secret here.

## Safe Handling Rules

- **Never echo the secret.** The workflow no longer prints the key length, a
  success banner that includes the value, or any derived/transformed form of the
  key. Only the boolean outcome of the presence check and the existence of the
  materialized file can appear in logs.
- **Materialize to a single restricted file.** The key is written to
  `/tmp/gcp_key.json` (and the dbt profile to `~/.dbt/profiles.yml`) with `umask 077`
  and an explicit `chmod 600`. The file path is logged; the file contents are not.
- **Keep credentials out of command arguments.** The key is never passed on a
  command line. It reaches dbt through the `keyfile:` field of the profile YAML, and
  it reaches the deploy action through the action's own `credentials_json` input.
- **Cleanup runs on both success and failure.** The `Cleanup Service Account Key &
  Profile` step uses `if: always()` and removes `/tmp/gcp_key.json` and
  `~/.dbt/profiles.yml`, so no secret-bearing file survives a failed job.
- **No secret-bearing artifacts or caches.** The workflow produces no uploaded
  artifacts, caches, or debug bundles that could contain the key. The dbt compile
  output and test results are text reports; the Docker image is built from the
  checked-out source, not from the credential materialization.

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

For these reasons this pipeline avoids relying on masking alone: it does not print
the secret or any derived form of it at all.

## Verification

Local verification uses only non-sensitive synthetic marker strings in an
isolated harness. A local harness **cannot** prove that GitHub masks secrets on a
hosted runner, and this document makes no such claim. The CI job must be reviewed
in GitHub Actions with a registered secret to confirm masking behavior there.

## Related

- [GitHub secret redaction and its limits](https://docs.github.com/en/actions/concepts/security/secrets)
- [GitHub Actions secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)
