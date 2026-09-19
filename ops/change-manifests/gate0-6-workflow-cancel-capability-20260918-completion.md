# Gate 0–6 Workflow Cancellation Capability — 2026-09-18

## Scope

- Capability: `workflow.cancel`
- Base commit: `d42e832a5bf5ccd78b343978aa5e323847b271c0`
- Candidate commit: pending at manifest creation; post-commit verification must bind the final SHA externally without changing it
- Overall release decision: `NO-GO`

## Implementation

- Reuses the existing Workflow owner, execution/planning records, remote cancellation transport, shared QCP Gateway, workflow event, renderer and consumers.
- Adds a governed `POST /workflows/{workflow_id}/cancel` endpoint; the legacy direct DELETE remains for compatibility and is not the PCM handler.
- Requires tenant/user ownership, QCP confirmation, QCP idempotency, and `expected_updated_at` CAS under a database row lock.
- Persists the terminal cancellation request id, canonical request hash and full receipt on `WorkflowDefinition`.
- Replays the exact saved receipt for the same request and payload; rejects same-key/different-payload and stale revision.
- Cancels active executions and planning jobs, archives clarification state, then tombstones the workflow.
- A remote cancellation error returns 502 and does not archive the workflow, mutate the execution to cancelled, or write a success receipt.
- Adds additive startup migration columns and the tenant/user/request unique index; no second runtime or cancellation store was introduced.

## Pre-commit verification

- Workflow/Gateway/PCM focused suite: `44 passed`.
- Workflow API cancellation/legacy deletion cases: `3 passed`.
- Ruff: passed.
- PCM manual check: passed.
- iOS matrix check: passed.
- Gateway bypass scan: `0` violations.
- Governed engineering rules: synchronized.
- `git diff --check`: passed.

## Matrix movement

- Before: `implemented=0`, `partial=49`, `absent=21`, `unverified=0`.
- Candidate: `implemented=0`, `partial=50`, `absent=20`, `unverified=0`.
- `workflow.cancel` remains `partial` until production receipt/readback and full simulator scenario evidence exist.

## Evidence boundary

This focused batch does not prove the full current-SHA backend regression, full iOS unit suite, 70-capability simulator matrix, production clean-room acceptance, deployment, or TestFlight delivery. Historical full-suite results are not reused as proof for this candidate.
