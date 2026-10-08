# Task: Verify Exact Email Allowlist Matching

## Project Rules and Worker Role
- Read the current repository `AGENTS.md` and applicable directory instructions. Its architecture, production safety, credentials, tests, and auth rules remain in force.
- Work only in this task's assigned Agent Manager worktree. The base is `integration`; verify the actual branch, upstream, base SHA, and clean starting state. Set the Agent Manager base explicitly rather than assuming it.
- Do not merge into `integration` or `main`, push, deploy, delete worktrees/branches, or change production settings. Commit reviewed task files and report ready for review.
- These are suspected issues to audit, not confirmed findings. Inspect actual source/configuration first. No-op findings need evidence and a report; do not invent a vulnerability or manufacture a fix.
- Ownership is a batch agreement, not a filesystem lock. Coordinate any out-of-scope edit before making it. Preserve unrelated edits; avoid repository-wide formatting.
- Never query production BigQuery, run ingestion/deployment, create real accounts, or expose credentials in verification. Use local fixtures/mocks and isolated outputs.

## Assignment and Ownership
- Task ID: `email-allowlist`
- Suggested branch: `agent/security-email-allowlist`
- Wave: 1; may run alongside dependency and CI-log tasks.
- Own: `my-dash-app/auth.py`, `tests/test_auth.py`, and task-specific notes in `docs/security/email-allowlist.md` if needed.
- Read-only: auth frontend, templates, dependency manifests/locks, CI, shared data/cache modules.
- Reserve `auth.py` for this worker in wave 1. The CSP worker may edit it only after this task is accepted or editing is stopped and ownership explicitly transferred.

## Policy Resolution
The supplied issue says both “exact-case-sensitive” and “case-insensitive.” The existing `AGENTS.md` is explicit: match the **complete email address case-insensitively**. “Exact” means the full address, not a domain allowlist, substring, suffix, wildcard, or partial address. Do not introduce case-sensitive local-part/domain matching.

## Requirements
1. Audit parsing of `AUTH_ALLOWED_EMAILS`, normalization, Supabase-verified email handling, and the order of confirmation/allowlist checks. Do not authorize from editable metadata, client state, or unverified claims.
2. Add offline `unittest` regressions for mixed-case allowlist entries and returned emails, including domain case. Require the same full address to match after the established case normalization.
3. Add negative cases: a different local part on the same domain, suffix/prefix lookalikes, attacker subdomains, plus-address variants unless explicitly listed, and empty/whitespace-only allowlists. Test missing and unconfirmed email, preserving established parsing rules rather than adding new canonicalization.
4. Keep an empty allowlist denying everyone. Do not strip dots, discard plus tags, expand domains, or infer equivalence beyond the documented normalization.
5. Make only minimal implementation changes if a regression reveals a mismatch. Preserve exact-Origin checks, cookies, no-store headers, auth installation order, token verification, and required 401/403/503 behavior.

## Acceptance Criteria
- Regression coverage proves full-address case-insensitive matching and rejects partial/domain-only matches.
- Existing authorization remains fail-closed, with confirmation required before data loaders run.
- If behavior was already correct, deliver regression tests and state that the proposed bypass was not confirmed.

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
Use mocked Supabase responses and Flask test requests. Demonstrate that denied identities do not invoke protected data loaders. No production allowlist changes or real identity operations.

## Completion Handoff
Send the integration session:
- Task ID/title, Agent Manager session, actual branch, worktree path, base SHA, and submitted head SHA.
- Acceptance criteria addressed and source/configuration evidence; changed paths and their purpose.
- Dependency, shared-interface, generated-file, or configuration changes; required predecessor commits.
- Exact commands/results and tested SHA; skipped/failed checks and reasons.
- Known limitations, blockers, production implications, and rollback considerations.
- Working tree status, outstanding staged/unstaged/untracked changes, and allocated resources.

Remain paused at the submitted SHA while it is reviewed. Notify the integrator before any revision; submit a new handoff and checks for a changed head. A report is required even when the audit finds no code change necessary.
