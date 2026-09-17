# Gate 0–6 Project/Task capability batch completion

- task_id: `gate0-6-project-task-capabilities-20260918`
- status: `COMMITTED` (local checkpoint; exact SHA is recorded in the handoff)
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-gate0-6-completion-20260917`
- base_head: `6c7780c788eefb8d21925d2d8692041c45db063f`
- remote_sha: `10ddeaf6bc2a5036dcedbdd195397cb4a5067860` (`origin/main`, fetched before edits)
- server_before: not inspected; deployment was not authorized
- server_after: not applicable
- health_check: not applicable
- functional_check: local focused Gateway/QCP/QWS tests passed
- rollback_point: `6c7780c788eefb8d21925d2d8692041c45db063f`

## Scope and result

Registered `project.list`, `project.create`, `project.open`, `task.list`, `task.create`, `task.update`, and `task.status` on the existing PCM/QCP Gateway and QWS domain APIs. Project/task writes use the durable Gateway confirmation and idempotency flow; task create/update retain QWS project revision CAS and return the domain change proposal rather than claiming the task was already applied. Tenant/member/owner authorization remains in the QWS domain API.

`task.execute` remains absent. The real QWS auto-execution endpoint requires an authenticated Taskboard bearer context plus an existing task-conversation and confirmed project intent. The durable Gateway replay payload intentionally does not persist the bearer credential, so no safe domain call is currently available.

## Changed files

- `backend/capability_handlers.py`
- `backend/contracts/product-capabilities/{project_task.yaml,manifest.yaml,bindings.yaml,events.yaml,policies.yaml,ios-scope.yaml}`
- `backend/services/capability_catalog.py`
- `docs/product-capability-{manual.md,coverage.json}` (generated)
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ops/acceptance/{gate0-6-status-20260918.md,ios-capability-matrix.json}`
- `tests/{test_project_task_capabilities.py,test_product_capabilities.py,test_ios_capability_matrix.py}`
- `ops/change-manifests/gate0-6-project-task-capabilities-20260918-completion.md`

## Verification

- Focused Gateway/QCP capability suite: `60 passed`.
- Existing QWS API suite: `52 passed`.
- Ruff on changed Python paths: passed.
- Product capability manual generation/check: passed.
- iOS capability matrix generation/check: passed.
- Matrix: `70 total`; `implemented=0`, `partial=36`, `absent=34`, `unverified=0`.
- `git diff --check`: passed.

## Remaining risks

- No production receipt or simulator/real-device evidence was created; all seven new rows remain `partial`.
- `task.execute` needs a credential-safe server-side delegated execution entry before PCM registration.
- Existing absent project/task capabilities (`project.update`, `project.delete`, `task.delete`) were not widened into this batch.
- No push, deployment, archive, or TestFlight upload was performed.
