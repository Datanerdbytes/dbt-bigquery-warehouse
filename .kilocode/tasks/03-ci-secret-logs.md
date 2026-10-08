# Task: Audit and Harden CI Secret Handling

## Project Rules and Worker Role
- Read the current repository `AGENTS.md` and applicable directory instructions. Its architecture, production safety, credentials, tests, and auth rules remain in force.
- Work only in this task's assigned Agent Manager worktree. The base is `integration`; verify the actual branch, upstream, base SHA, and clean starting state. Set the Agent Manager base explicitly rather than assuming it.
- Do not merge into `integration` or `main`, push, deploy, delete worktrees/branches, or change production settings. Commit reviewed task files and report ready for review.
- These are suspected issues to audit, not confirmed findings. Inspect actual source/configuration first. No-op findings need evidence and a report; do not invent a vulnerability or manufacture a fix.
- Ownership is a batch agreement, not a filesystem lock. Coordinate any out-of-scope edit before making it. Preserve unrelated edits; avoid repository-wide formatting.
- Never query production BigQuery, run ingestion/deployment, create real accounts, or expose credentials in verification. Use local fixtures/mocks and isolated outputs.

## Assignment and Ownership
- Task ID: `ci-secret-logs`
- Suggested branch: `agent/security-ci-secret-logs`
- Wave: 1; may run alongside email and dependency tasks.
- Own: `.github/workflows/ci_pipeline.yml`, `docs/security/ci-secret-handling.md`; a dedicated offline workflow regression file under `tests/` only if meaningful and necessary.
- Read-only: dependency manifests/locks, new `security_dependency_audit.yml`, deployment/build scripts, Docker and application source.
- The dependency worker owns the separate audit workflow. Coordinate job/trigger conventions, but do not both edit the existing CI file.
- If the existing workflow calls a script that leaks credentials, report the path and coordinate an explicit scope assignment before editing it.

## Issue to Verify
The supplied issue is conditional: determine whether `GCP_SA_KEY` or other sensitive values can actually reach logs/artifacts. Do not assert a leak without evidence and never inspect, reproduce, or print a real secret to confirm it.

## Requirements
1. Read the workflow and called scripts statically. Inspect credential injection, secret-to-file handling, debug modes, shell tracing, environment dumps, exception output, command arguments, outputs, artifacts, and cache contents.
2. Remove or prevent unnecessary secret logging and shell tracing around sensitive operations. Keep credentials out of command arguments when supported. Use supported action inputs or safely handled environment variables/files, preserving intended existing behavior without running deployments.
3. GitHub masks registered secrets automatically, but transformed/derived values may not be covered. Register sensitive derived values with the supported masking mechanism before any possible output. Do not print a secret as a test or treat masking as permission to log it.
4. Prevent credentials from entering uploaded artifacts, caches, step summaries, job outputs, or debug bundles. Keep temporary credential files restricted and arrange cleanup on failure as well as success. Preserve the existing auth/build/test commands and deployment gates.
5. Inspect whether untrusted PR code could execute in a credential-bearing job. Preserve or tighten secret availability and permissions without changing release behavior casually. Report larger trigger/authentication redesigns as follow-up decisions; do not rotate credentials or migrate production IAM as part of this task.
6. If there is evidence suggesting an existing exposure, report only the location and nature of the suspected exposure. Do not fetch secret-bearing historical logs or perform credential rotation without separate authorization.
7. Document safe handling and limits of masking. Validate with non-sensitive synthetic marker strings only in an isolated local harness. A local harness cannot prove actual GitHub runner masking.

## Acceptance Criteria
- Static evidence identifies confirmed weaknesses or explains why the suspected issue was not found.
- No unnecessary credential output, unsafe tracing, or credential-bearing artifact path remains in the edited workflow.
- Existing required checks and deployment restrictions are preserved.
- Local verification is clearly distinguished from a hosted CI run; no cloud operations or real-secret tests occur.

## References
- [GitHub secret redaction and its limits](https://docs.github.com/en/actions/concepts/security/secrets)
- [GitHub Actions secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)

## Verification
Run from the repository root after safe dependency setup:

```bash
.venv/bin/python -B -m unittest discover -s tests -v
npm run build:auth
npm run test:auth
```

- Preserve offline BigQuery-client guards and existing auth regressions. Do not disable tests or authorization to obtain a pass.
- Build before browser tests. Inspect tracked bundle changes; only commit generated outputs assigned to this task. Report unexpected out-of-scope output and coordinate its owner.
- Follow additional task checks below and applicable existing CI checks, excluding cloud writes and deployment. Missing runtime, network failure, unavailable browser, or skipped verification is not a pass.

## Additional Checks
Validate YAML and workflow expressions using an existing suitable validator when available. Check the final diff for printed/interpolated credential expressions and unsafe artifact/cache paths. Do not launch the deployment workflow locally or push merely to test masking. Add a focused regression only where it tests meaningful behavior rather than reproducing YAML text.

## Completion Handoff
Send the integration session:
- Task ID/title, Agent Manager session, actual branch, worktree path, base SHA, and submitted head SHA.
- Acceptance criteria addressed and source/configuration evidence; changed paths and their purpose.
- Dependency, shared-interface, generated-file, or configuration changes; required predecessor commits.
- Exact commands/results and tested SHA; skipped/failed checks and reasons.
- Known limitations, blockers, production implications, and rollback considerations.
- Working tree status, outstanding staged/unstaged/untracked changes, and allocated resources.

Remain paused at the submitted SHA while it is reviewed. Notify the integrator before any revision; submit a new handoff and checks for a changed head. A report is required even when the audit finds no code change necessary.
