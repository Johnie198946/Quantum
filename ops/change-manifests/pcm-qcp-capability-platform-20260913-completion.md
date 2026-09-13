# PCM/QCP capability platform completion

- task_id: `pcm-qcp-capability-platform-20260913`
- status: `VERIFIED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-ios-document-ppt-final-20260912`
- head/local_commit: implementation commit `e787d2c13da29a54300da7a1391b74d0ece0b546`
- remote_sha: `e787d2c13da29a54300da7a1391b74d0ece0b546`, verified with `git ls-remote origin refs/heads/main` before deployment
- server_before: `/opt/releases/ai-lab-platform-5bcb0dac4e89.fZdeXk`, `.deployed-sha=5bcb0dac4e89baf33df11ee7822ed9444d867bc9`
- server_after: `/opt/releases/ai-lab-platform-e787d2c13da2.LafdiJ`, `.deployed-sha=e787d2c13da29a54300da7a1391b74d0ece0b546`
- health_check: deployment script passed additive migration, runtime contract audit, atomic switch and final checks; API ready, Hermes Bridge `ok/v6.0`, public `/health` ok, and 8/8 Compose services running/healthy
- functional_check: final backend suite passed 132 tests; simulator suites passed 163 tests; deployed catalog loaded 15 capabilities with digest `2fb5823ef73b12286f441b0c2bdce0f755548dd6cde7ecc494db773495827bff`; unauthenticated search returned 401; all three Bridge tool registrations are present
- rollback_point: `/opt/ai-lab-shared/deployment-checkpoints/pcm-qcp-e787d2c13da29a54300da7a1391b74d0ece0b546`; deployment rollback release `/opt/releases/ai-lab-platform-5bcb0dac4e89.fZdeXk`
- deployment/release: GitHub push and exact-SHA production deployment completed; TestFlight 1.0.3 (39) archive passed, but upload was blocked by missing Xcode account credentials (`Failed to Use Accounts`)

## Delivered

- Model-triggered required-confirmation mutations now stop at an identity-free `capability.proposed` event. The Hermes tool schema exposes no confirmation authority and never self-confirms.
- iOS renders the validated workflow/PPT/start proposal and only calls authenticated `/api/v1/capabilities/invoke` with `confirmed=true` after the user taps confirm. The deterministic proposal ID is reused as the invocation idempotency key across retries and restarts.
- Interrupted persisted `.applying` proposals restore as `.awaitingConfirmation`, preserving the same proposal/idempotency key so recovery is retryable without duplicate creation.
- Capability completion checks the captured tenant epoch before workflow tracking, navigation, or proposal mutation; delayed completion from a prior tenant is discarded after an account switch.
- Knowledge update/archive/merge proposals preserve the caller-supplied target and source CAS hashes exactly. Stale hashes are no longer refreshed from the workspace read and therefore reach the existing conflict checks instead of overwriting concurrent edits.
- DB-backed Bridge reads use the FastAPI-owned process-stable event loop through `run_coroutine_threadsafe` with a bounded timeout; consecutive-call regression coverage verifies one loop.
- `knowledge.note.create` now performs create-only comparison under the existing note lock: identical key/payload replays, changed payload returns deterministic `idempotency_conflict` without mutation.
- Capability search and describe routes now require authentication; unauthenticated tests cover both routes.
- Added validated knowledge natural-QA, workflow KnowledgeNeed/injection, and structured-artifact consumption contracts with receipt/gate references; structured artifact consumption remains honestly marked `partial`.
- Deterministic validation now enforces mutation confirmation/idempotency/receipt, executable/allowlisted bindings, valid unique references, renderer fallback/version coverage, and generated-document synchronization.
- Preserved and tested the existing knowledge archive/CAS fixes from the prior pass.
- PCM string limits now enforce the existing workflow DTO maxima, and any remaining Pydantic DTO validation failure becomes a redacted structured QCP `contract_invalid` result instead of HTTP 500.
- Failed iOS capability proposals can be retried or discarded with their stable proposal ID/idempotency key; completed and discarded proposals remain terminal.
- `PersistedMessage` stores and restores every capability proposal, decodes the legacy singular field, and de-duplicates singular/array overlap.
- Workflow deterministic IDs and request digests now include the exact capability ID, preventing workflow and presentation creation from sharing an idempotency identity.
- Knowledge update/archive/restore now use durable per-account, per-capability receipt files under the existing note `.operations` namespace. A hashed key and payload digest are persisted before mutation under a per-receipt file lock; completed JSON-safe result metadata is replayed exactly, payload drift conflicts, corrupt receipts fail closed, and no note body is stored in a receipt.

## Changed files

- `backend/api/capabilities.py`
- `backend/api/knowledge_sync.py`
- `backend/api/workflows.py`
- `backend/main.py`
- `backend/services/capability_catalog.py`
- `backend/services/capability_handlers.py`
- `backend/contracts/product-capabilities/binding.schema.json`
- `backend/contracts/product-capabilities/bindings.yaml`
- `backend/contracts/product-capabilities/capabilities.yaml`
- `backend/contracts/product-capabilities/capability.schema.json`
- `backend/contracts/product-capabilities/consumption.schema.json`
- `backend/contracts/product-capabilities/consumptions.yaml`
- `backend/contracts/product-capabilities/event.schema.json`
- `backend/contracts/product-capabilities/events.yaml`
- `backend/contracts/product-capabilities/manifest.yaml`
- `backend/contracts/product-capabilities/policies.yaml`
- `backend/contracts/product-capabilities/policy.schema.json`
- `backend/contracts/product-capabilities/renderer.schema.json`
- `backend/contracts/product-capabilities/renderers.yaml`
- `docs/product-capability-coverage.json`
- `docs/product-capability-manual.md`
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformApp/Models/UIModels.swift`
- `ios/AIPlatformApp/Services/KnowledgeNoteStore.swift`
- `ios/AIPlatformApp/Views/Chat/Components/ChatStatusCards.swift`
- `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
- `ios/AIPlatformApp/Views/Chat/Dispatchers/BlockCardDispatcher.swift`
- `ios/AIPlatformApp/Views/Chat/Dispatchers/PluginRenderContext.swift`
- `ios/AIPlatformApp/Views/Chat/MessageBubbleView.swift`
- `ios/AIPlatformAppTests/KnowledgeNoteStoreTests.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
- `scripts/generate_product_capability_manual.py`
- `scripts/hermes_bridge.py`
- `tests/test_product_capabilities.py`
- `ops/change-manifests/pcm-qcp-capability-platform-20260913-completion.md`

## Verification

- Final independent acceptance rerun: `python3 scripts/generate_product_capability_manual.py --check` + `compileall` + Ruff + `python3 -m pytest -q -rs tests/test_product_capabilities.py tests/test_workflows_api.py tests/test_workflow_contract.py tests/test_workflow_event_projection.py tests/test_document_presentation.py tests/test_knowledge_sync_api.py tests/test_knowledge_actions.py tests/test_knowledge_consumption_gate_server.py` + `git diff --check`: **132 passed, 8 warnings**, all non-test checks passed.
- Final simulator acceptance on iPhone 17 Pro `A5005DE7-3D7E-4FA0-A9D9-92967B4A699A`: `WorkflowLifecycleDTOTests` **140 passed** and `KnowledgeNoteStoreTests` **23 passed**; **163 total, 0 failures**. Result bundle: `/tmp/pcm-qcp-final-acceptance/Logs/Test/Test-AIPlatformApp-2026.09.14_00-41-49-+0800.xcresult`.

## Remaining risks / intentionally partial

- Structured artifact consumption is contractually described and content-hash receipted, but remains `partial`: there is no general downstream structured-artifact consumer that emits a durable consumption receipt.
- FastAPI reports existing `on_event` deprecation warnings; replacing the Bridge lifecycle style was outside this security fix.
- The passing iOS run still emitted existing SQLite test-cleanup `vnode unlinked while in use` diagnostics and AppIntents metadata-skip warnings; neither produced a test/build failure.
- The deployed iOS source was archived as TestFlight `1.0.3 (39)` with executable SHA-256 `2d5621d6debc810e783efd46ba0205bd5ae060d97d7ac963f54a6a67b3c010b4`; strict code-sign verification passed. Upload did not occur because Xcode has no usable App Store Connect account credential in the current keychain (`Failed to Use Accounts`).
