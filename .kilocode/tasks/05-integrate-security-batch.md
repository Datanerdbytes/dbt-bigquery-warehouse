# Task: Integrate the Security Hardening Batch

## Rules, Role, and Authorization
Read and follow the current repository `AGENTS.md`. You are the single integration writer for this batch. When the user launches this task with an instruction to integrate the batch, you are authorized to create local candidate worktrees, merge the listed submitted commits, make straightforward in-scope integration fixes, run safe checks, and fast-forward local `integration` after verification.

Do not push, merge into `main`, deploy, change production resources/settings, rotate credentials, or delete branches/worktrees. These instructions do not themselves launch workers or grant external service permissions. Preserve pre-existing edits and recovery references.

## Task Manifest
Task-file paths are repository-relative after copying this package into `.kilocode/tasks/`. Branch names are proposed defaults; verify and substitute actual branches from the worker handoffs. Do not assume a task is complete because its branch exists.

| ID | Suggested branch | Task file | Phase |
|---|---|---|---|
| email-allowlist | agent/security-email-allowlist | .kilocode/tasks/01-email-allowlist.md | 1 |
| dependency-audit | agent/security-dependency-audit | .kilocode/tasks/02-dependency-audit.md | 1 |
| ci-secret-logs | agent/security-ci-secret-logs | .kilocode/tasks/03-ci-secret-logs.md | 1 |
| csp-hardening | agent/security-csp-hardening | .kilocode/tasks/04-csp-hardening.md | 2 |

## Coordination Record
Maintain the single batch record at `docs/agent-work/security-hardening.md` in the integration checkout. Workers send handoffs rather than editing competing records. Record actual sessions, paths, branches, base/submitted SHAs, authorized operations, task statuses, checks, and ownership transfers. Keep the record in local coordination state unless it is deliberately reviewed and committed; do not let unrelated record edits contaminate candidate promotion.

## Phase 1: Foundational Integration
1. Obtain all three wave-1 handoffs. Inspect their exact submitted SHAs, diffs, acceptance criteria, clean state, and blockers. Request missing evidence; do not launch or assume completion of missing workers.
2. Verify that the case-insensitive exact full-email policy is preserved and that dependency/CI ownership was respected. A dependency task's new audit workflow and the CI-log task's existing workflow must work together without changing deployment gates or exposing secrets.
3. Create a clean isolated candidate from the current local `integration` SHA. Record a recoverable pre-integration reference. Merge the accepted dependency commit first, then CI-log and email commits, using exact submitted SHAs and an ancestry-preserving merge method. Record audited no-op tasks without inventing commits.
4. Inspect each combined result and run affected checks. Resolve only unambiguous textual/integration problems while preserving every task's intent. Never choose blanket ours/theirs, manually splice lockfiles, weaken authorization/tests, or silently add scanner suppressions.
5. Run the complete verification gate below on the final combined candidate SHA. Recheck local `integration`: if it moved, incorporate that head and reverify. Fast-forward it only to a verified candidate with a clean target checkout.
6. Report the verified phase-1 integration SHA. Tell the user to launch the CSP task from that base. Record that auth.py and generated-bundle ownership has transferred to CSP after the earlier workers stop editing. Return awaiting CSP; do not wait forever or silently mark the whole batch finished.

## Phase 2: Final CSP Integration
Continue in this same integration session once the user supplies the completed CSP handoff.
1. Verify the CSP base includes the accepted phase-1 result. Review nonce/header wiring, route coverage, inline/client-side code, generated outputs, browser evidence, and compatibility with final locks.
2. Create/reuse a suitable clean candidate from the current `integration` head and merge the exact accepted CSP SHA. If a submitted head changes, request refreshed evidence and rerun checks.
3. Rerun the full gate on the combined tree. Make separately recorded straightforward integration fixes only within batch scope. Ambiguous business/security choices, scope expansion, unavailable required checks, or unresolved audit/CSP gaps require escalation; retain recoverable work and do not promote a failed candidate.
4. Recheck the target head immediately before fast-forwarding. Any new target changes must be incorporated and verified again. Report the final integrated SHA and coverage. Do not promote to main or clean up branches/worktrees.

## Verification Gate (Both Phases)
Run from the combined candidate's repository root:

```bash
.venv/bin/python -B -m unittest discover -s tests -v
npm run build:auth
npm run test:auth
```

- Run the dependency owner's exact supported audit/export commands against final locks; retain runtime/development coverage and report every unresolved advisory/exclusion and scanner error. A pass must meet the recorded audit policy; unresolved exceptions need user decisions.
- Validate both CI workflows statically and execute their safe local checks. Do not trigger a deployment or claim local validation is hosted CI success. Confirm CI audit jobs are credential-free and secret protections survive the combined diff.
- Rerun email allowlist regressions and authorization failures, preserving 401/403/503 and empty-allowlist denial.
- In phase 2, run dedicated CSP response and browser tests, including injection blocking, nonce freshness, auth flows, Dash rendering/chunks/callbacks, and route coverage with local mocks.
- Inspect rebuilt tracked bundles, final diff/status, accidental credentials, conflict markers, unrelated artifacts, lock consistency, callback contracts, and auth/security behavior. Include required generated changes before certifying the tested SHA.
- No production BigQuery client, real accounts, cloud mutations, ingestion, dbt clean, or deployment. Required skipped checks mean awaiting verification. Changes after testing require relevant checks again.

## Escalation and Final Report
Stop the affected integration for ambiguous CSP exceptions, incompatible contracts, architectural/security decisions, unverifiable recovery, or unexplained failures. Report paths/SHAs, both intents, safe evidence, recovery state, and the smallest needed decision. Continue unrelated work only when safe and independent.

Report phase/final target SHA; accepted task SHAs or documented no-ops; conflict/fix commits; exact checks/results/tested SHA; coverage gaps/advisories and approved exceptions; retained recovery references/worktrees; and the next required action. Only phase 2 passing makes the complete batch integrated. Cleanup is a separate authorized operation.
