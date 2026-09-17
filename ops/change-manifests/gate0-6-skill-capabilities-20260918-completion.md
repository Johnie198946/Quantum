# Gate 0–6 Skill capability batch completion

- task_id: `gate0-6-skill-capabilities-20260918`
- status: `COMMITTED` (local checkpoint; exact SHA is recorded in the delivery handoff)
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-gate0-6-completion-20260917`
- base_head: `dc4f82ff2f2f8fdc60b4c91b4bda8a04d3388c2f`
- remote_sha: `10ddeaf6bc2a5036dcedbdd195397cb4a5067860` (`origin/main`, fetched before edits)
- server_before: not inspected; deployment was not authorized
- server_after: not applicable
- health_check: not applicable
- functional_check: local Skill/Gateway/QCP/Bridge focused suite passed
- rollback_point: `dc4f82ff2f2f8fdc60b4c91b4bda8a04d3388c2f`

## Scope and result

Registered `skill.list`, `skill.create`, `skill.update`, and `skill.delete` on the existing PCM/QCP Gateway. Reads and writes reuse the signed tenant/user Hermes sandbox; no Skill database, second Runtime, client-side authority, direct sandbox writer, or model-tool bypass was added. Create/update use the existing governed atomic sandbox primitive through a private signed Bridge HTTP facade. Create/update/delete verify the resulting signed sandbox catalog after mutation. QCP writes require durable Proposal → Confirm → Execute, one-time bound confirmation, and tenant/user-scoped idempotency.

The iOS RendererRegistry consumes `skill.snapshot@1` and `skill.changed@1` through the existing answer fallback path. The four matrix rows remain `partial` because no production receipt or simulator/real-device E2E was produced; production receipt remains `unverified`.

## Changed files

- `backend/capability_handlers.py`
- `backend/contracts/product-capabilities/{skill.yaml,manifest.yaml,bindings.yaml,events.yaml,policies.yaml,ios-scope.yaml}`
- `backend/services/{capability_catalog.py,hermes_sandbox_catalog.py}`
- `scripts/hermes_bridge.py`
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
- `tests/{test_skill_capabilities.py,test_product_capabilities.py,test_ios_capability_matrix.py}`
- `docs/product-capability-{manual.md,coverage.json}` (generated)
- `ops/acceptance/ios-capability-matrix.json` (generated)
- `ops/change-manifests/gate0-6-skill-capabilities-20260918-completion.md`

## Verification

- Focused Skill/Gateway/QCP/Bridge suite: `101 passed`, `13 skipped` (platform-specific skips), `8` pre-existing deprecation warnings.
- Ruff on changed Python paths: passed.
- Product capability manual generation/check: passed.
- iOS capability matrix generation/check: passed.
- Gateway bypass scan: `0` violations.
- Governed engineering rules check: passed.
- Matrix: `70 total`; `implemented=0`, `partial=40`, `absent=30`, `unverified=0`.
- `git diff --check`: passed.

## Remaining risks

- No production receipt, deployed revision, simulator, or real-device evidence exists; the four Skill rows are not end-to-end verified.
- The Bridge facade is an internal signed domain adapter; public clients must continue through QCP and cannot treat the signed sandbox capability as user confirmation.
- Existing FastAPI lifecycle and Pydantic deprecation warnings were not introduced or expanded by this batch.
- No push, deployment, archive, or TestFlight upload was performed.
