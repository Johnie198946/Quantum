# Gate 0–6 Notification/Schedule capability batch completion

- task_id: `gate0-6-notification-schedule-20260918`
- status: `COMMITTED` (local checkpoint; exact SHA is recorded in the delivery handoff)
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-gate0-6-completion-20260917`
- base_head: `078b43f3586e670a242cc77d71f2bb71f8a1818e`
- local_ahead_before: `5`
- remote_sha: `10ddeaf6bc2a5036dcedbdd195397cb4a5067860` (`origin/main`)
- deployment: not authorized; no push, deployment, archive, or TestFlight action performed

## Scope and result

Registered `schedule.list`, `schedule.create`, `schedule.update`, and `schedule.delete` on the existing modular PCM/QCP Gateway. Reads reuse the canonical QWS project schedule. Writes require QCP Proposal → Confirm → Execute, tenant/user-bound confirmation, Gateway idempotency and replayable receipt, and the existing QWS project-change proposal owner with process-revision CAS and domain request replay/conflict handling. No second runtime, state machine, or schedule database was added.

`notification.list`, `notification.mark_read`, and `notification.preferences.update` remain absent. The current Notification table/API is tenant-global with no per-user owner/read state; mark-read lacks user CAS/domain idempotency receipt; and no notification-preferences model, persistence owner, or API exists. Registering these capabilities would violate the requested tenant/user boundary, so exact blockers are recorded in `ios-scope.yaml` rather than overstating implementation.

The shared iOS `RendererRegistry` and QWS event registry consume `schedule.snapshot@1` and `schedule.change_proposed@1`, preserving a deterministic answer fallback for unsupported versions. All schedule matrix rows remain `partial` because no production receipt exists; production receipt status remains `unverified`.

## Changed files

- `backend/api/quantum_workspace.py`
- `backend/capability_handlers.py`
- `backend/services/capability_catalog.py`
- `backend/contracts/product-capabilities/{schedule.yaml,manifest.yaml,bindings.yaml,policies.yaml,events.yaml,ios-scope.yaml}`
- `frontend/src/features/quantum-workspace/{TaskChatDrawer.jsx,qcpEventRegistry.js}`
- `frontend/tests/qcp-schedule-consumer.test.mjs`
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
- `tests/{test_schedule_capabilities.py,test_quantum_workspace_api.py,test_product_capabilities.py,test_ios_capability_matrix.py}`
- `docs/product-capability-{manual.md,coverage.json}` (generated)
- `ops/acceptance/{gate0-6-status-20260918.md,ios-capability-matrix.json}` (generated matrix)
- `ops/change-manifests/gate0-6-notification-schedule-20260918-completion.md`

## Verification

- Focused Gateway/QCP/QWS/PCM/matrix Python suite: `55 passed`, `0 failed`, `14 warnings`.
- QWS shared registry Node suite: `2 passed`, `0 failed`.
- Focused iOS RendererRegistry XCTest: `1 passed`, `0 failed`; result bundle `/tmp/ai-lab-schedule-renderer.xcresult`.
- Additional iOS `WorkflowLifecycleDTOTests` suite: `149 passed`, `0 failed`.
- Frontend production build: passed after deterministic `npm ci --ignore-scripts` (`2686` modules transformed).
- Ruff on changed Python paths: passed.
- Product capability manual generation: passed.
- iOS capability matrix generation/check: passed.
- Gateway bypass scan: `0` violations.
- Governed engineering rules check: passed.
- Matrix: `70 total`; `implemented=0`, `partial=46`, `absent=24`, `unverified=0`.
- `git diff --check`: passed.

## Rollback and remaining risks

- rollback_point: base commit `078b43f3586e670a242cc77d71f2bb71f8a1818e`; revert the local delivery commit before any future push.
- Notification capabilities require per-user domain ownership/persistence, authorization, CAS/idempotency, and durable replayable receipts before registration.
- Schedule production receipts and production/simulator end-to-end UI evidence do not exist; rows truthfully remain partial with unverified receipts.
- No push, remote SHA update, server deployment, health check, or production functional check was performed.
