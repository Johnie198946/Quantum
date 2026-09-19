# Gate 0–6 Workflow capability batch completion

- task_id: `gate0-6-workflow-capabilities-20260918`
- status: `COMMITTED` (local checkpoint; exact SHA is recorded in the delivery handoff)
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-gate0-6-completion-20260917`
- base_head: `706bf5980e49377ae6cef71ee17f87551aa6d0f3`
- remote_sha: `10ddeaf6bc2a5036dcedbdd195397cb4a5067860` (`origin/main`)
- deployment: not authorized; no push, deployment, archive, or TestFlight action performed

## Scope and result

Registered `workflow.approve` and `workflow.revise` on the existing PCM/QCP Gateway. Both are high-risk writes requiring bound confirmation, idempotency, durable receipts, owner/tenant enforcement by the existing Workflow domain handlers, and exact active-plan hash/revision CAS. Approval reuses the existing approve-plan lifecycle and now accepts the optional CAS pair needed by QCP without changing legacy callers. Revision reuses the existing immutable versioned plan editor and its request-id replay.

`workflow.cancel` remains absent. The existing execution cancellation route has no domain idempotency key or durable cancellation receipt. A crash after cancellation but before QCP receipt persistence therefore cannot safely distinguish a replay from an unrelated prior cancellation. No second runtime or state machine was added.

The existing iOS shared `RendererRegistry` routes `workflow.approved@1` and `workflow.revised@1` through the workflow path with answer fallback. Both matrix rows remain `partial`: no production receipt or simulator/real-device end-to-end execution was produced.

## Changed files

- `backend/api/workflows.py`
- `backend/capability_handlers.py`
- `backend/contracts/product-capabilities/{workflow_lifecycle.yaml,manifest.yaml,bindings.yaml,events.yaml,ios-scope.yaml}`
- `backend/services/capability_catalog.py`
- `docs/product-capability-{manual.md,coverage.json}` (generated)
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
- `tests/{test_workflow_capabilities.py,test_workflows_api.py,test_product_capabilities.py,test_ios_capability_matrix.py}`
- `ops/acceptance/{gate0-6-status-20260918.md,ios-capability-matrix.json}`
- `ops/change-manifests/gate0-6-workflow-capabilities-20260918-completion.md`

## Verification

- Focused Workflow/Gateway/QCP, Workflow API, PCM, and matrix suite: `96 passed`, `0 failed`, `8` pre-existing deprecation warnings.
- Focused iOS RendererRegistry test: `1 passed`, `0 failed`; result bundle `/tmp/ai-lab-workflow-renderer.xcresult`.
- Ruff on changed Python paths: passed.
- Product capability manual generation/check: passed.
- iOS capability matrix generation/check: passed.
- Gateway bypass scan: `0` violations.
- Governed engineering rules check: passed.
- Matrix: `70 total`; `implemented=0`, `partial=42`, `absent=28`, `unverified=0`.
- `git diff --check`: passed.

## Remaining risks

- `workflow.cancel` requires a durable, tenant/owner-bound domain cancellation receipt and idempotency contract before Gateway registration.
- No production receipt, deployed revision, simulator UI, or real-device evidence exists for approve/revise; production receipt remains unverified and the rows are not marked matrix-implemented.
