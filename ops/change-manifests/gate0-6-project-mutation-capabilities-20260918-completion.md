# Gate 0–6 Project mutation capability batch completion

- task_id: `gate0-6-project-mutation-capabilities-20260918`
- status: `TESTED` (local candidate; commit pending at manifest creation)
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-gate0-6-completion-20260917`
- base_head: `7cc24fd464709ec97a0a2b409dd9274e5daec7f4`
- remote_sha: `10ddeaf6bc2a5036dcedbdd195397cb4a5067860`
- rollback_point: `7cc24fd464709ec97a0a2b409dd9274e5daec7f4`

## Scope

Added two governed capabilities on the existing PCM/QCP/Gateway/QWS chain:

- `project.update`
- `task.delete`

`project.update` delegates to the canonical QWS project update proposal using the caller's expected project revision and the Gateway idempotency key as the domain request ID.

`task.delete` is intentionally a soft delete. It delegates to the canonical QWS task archive-proposal route with `action=ARCHIVE`; it does not hard-delete task or audit history.

Both writes require Proposal → Confirm → Execute, authenticated tenant/user binding, expected-revision CAS, idempotency, durable invocation receipt, replay readback, shared iOS RendererRegistry consumption and QWS event-registry consumption. No second Runtime, project/task store, client-side authority or Chat capability switch was added.

## Changed surfaces

- PCM contract, bindings and events
- Existing capability handler/catalog registration
- iOS scope and shared RendererRegistry route
- QWS shared event registry
- Contract/Gateway/security/replay/CAS tests
- Generated product capability manual, coverage and iOS matrix

## Verification

- Python focused suite:
  - command: `PYTHONPATH=. <repo-compatible-python> -m pytest -q tests/test_project_task_capabilities.py tests/test_product_capabilities.py tests/test_ios_capability_matrix.py tests/test_capability_gateway.py tests/test_gateway_bypass.py`
  - result: `49 passed, 0 failed` (12 warnings)
- QWS Node registry: `3 passed, 0 failed`
- Ruff: passed
- Product capability manual check: passed
- iOS capability matrix check: passed
- Gateway bypass scan: `0 violations`
- Governed engineering rules: passed
- `git diff --check`: passed
- iOS Simulator, iPhone 17 Pro / iOS 26.1:
  - valid suite: `WorkflowLifecycleDTOTests`
  - result: `149 passed, 0 failed`
  - xcresult: `/tmp/QuantumnGateProjectTaskMutationClass.xcresult`
- Invalid iOS attempt retained as negative evidence:
  - the single-method selector exited zero but the result reported `Executed 0 tests`; it is not counted as passing evidence.
  - xcresult: `/tmp/QuantumnGateProjectTaskMutation.xcresult`

## Matrix

- total: `70`
- implemented: `0`
- partial: `48`
- absent: `22`
- unverified capability status: `0`
- production receipt status: all `70` remain unverified; no local receipt is represented as production completion.

## Delivery boundary

- GitHub push: not performed
- Server deployment/readback: not performed
- Production clean-room: not performed
- Archive/TestFlight: not performed

## Remaining risks

- Both new capabilities remain `partial` until production receipt, truth-source readback and real UI end-to-end evidence exist.
- `project.delete`, `task.execute`, `workflow.cancel`, Notification and device/file/media/session capabilities remain absent unless their real state-owner and crash-safe replay contracts are completed.
- Full backend and full iOS regression are not part of this focused batch and must be rerun on the final delivery SHA.
