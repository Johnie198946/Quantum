# Gate 0–6 Project Archive Capability — 2026-09-18

## Scope

- Capability: `project.delete`
- Semantics: governed tombstone/archive, not physical deletion
- Base commit: `04b8e0292042e5504b720e7e10fe5b4ae803c9a8`
- Candidate commit: pending at manifest creation; post-commit verification must bind the final SHA below
- Overall release decision: `NO-GO`

## Implementation

- Reuses the existing QWS `ProjectChangeProposal` owner and decision endpoint.
- Adds `PROJECT_ARCHIVE` classification and an `archive_project` proposal operation.
- Proposal creation requires tenant/owner scope, recent interactive-human authentication, `expected_revision`, and a durable request id.
- Proposal replay uses the existing tenant/project/request unique key and rejects mismatched replay.
- Approval rechecks project process revision before applying the tombstone.
- Approval writes the existing immutable audit stream and returns the durable proposal state.
- QCP continues to provide Proposal → Confirm → Execute, confirmation binding, idempotency replay and Receipt/status readback.
- iOS and QWS reuse the registered `project.change_proposed` semantic event and shared Renderer/Consumer path; no Chat-specific switch or second runtime/store was added.
- The legacy direct DELETE route remains for compatibility and is not bound to the governed capability.

## Pre-commit verification

- New-path selection: `4 passed`.
- Gateway/PCM focused suite: `50 passed`.
- QWS project archive domain test: `1 passed` (`53 deselected`).
- Ruff: passed.
- PCM manual check: passed.
- iOS matrix check: passed.
- Gateway bypass scan: `0` violations.
- Governed engineering rules: synchronized.
- `git diff --check`: passed.

## Matrix movement

- Before: `implemented=0`, `partial=48`, `absent=22`, `unverified=0`.
- Candidate: `implemented=0`, `partial=49`, `absent=21`, `unverified=0`.
- `project.delete` remains `partial` until production Receipt/readback and full simulator scenario evidence exist.

## Evidence boundary

This batch does not prove the full current-SHA backend regression, full iOS unit suite, the 70-capability simulator matrix, production clean-room acceptance, deployment, or TestFlight delivery. The historical `2637 passed` backend and `213 passed` iOS results predate this candidate and are not reused as current-SHA proof.

## Post-commit verification

Pending. Record the exact commit SHA and rerun the focused gates after commit before reporting this batch as SHA-bound.
