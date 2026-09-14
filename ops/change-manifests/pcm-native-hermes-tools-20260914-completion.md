# Completion Manifest

- task_id: `pcm-native-hermes-tools-20260914`
- status: `TESTED_PENDING_RELEASE`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-ios-document-ppt-final-20260912`
- base_sha: `77b340109735ecb60a9d150e23d892ed350c3c85`
- started_at: `2026-09-14T13:58:00+0800`
- tested_at: `2026-09-14T15:14:52+0800`

## Scope and design decision

PCM no longer exposes `app_capability_search -> app_capability_describe -> app_capability_invoke` as the normal model-facing business path. When the authenticated iOS client declares `qcp_v1`, PCM deterministically compiles every implemented Registry capability into one native Hermes tool definition. The native tool name and input schema come from the governed contract; its handler is closed over exactly one capability ID, so the model neither searches for nor supplies a routing ID.

The existing authenticated API search/describe endpoints remain available for administration and diagnostics, but are not registered in the Hermes `app_capabilities` toolset. With QCP enabled, the legacy model-visible `knowledge_workspace` mutation toolset is withheld to avoid two parallel model routes. Execution authorization, confirmation, idempotency, event projection and receipts remain enforced by QCP/domain handlers.

## Changed files

- `scripts/hermes_bridge.py`
- `scripts/generate_product_capability_manual.py`
- `docs/product-capability-manual.md`
- `tests/test_product_capabilities.py`
- `ops/change-manifests/pcm-native-hermes-tools-20260914-completion.md`

## Verification

- Real Hermes Registry assembly: `registered_count=16`, `expected_count=16`, `missing=[]`; no `app_capability_search`, `app_capability_describe` or `app_capability_invoke` tool was exposed. The generated `app_presentation_create_from_document` definition carried the exact Registry input schema.
- Python focused and adjacent regression suites: `206 passed`, `0 failed`.
- Additional broader workflow/chat/artifact suite from the same change pass: `246 passed`, `0 failed`.
- iOS Simulator `WorkflowLifecycleDTOTests`: `141 passed`, `0 failed`; result bundle `/tmp/pcm-native-tools-workflow.xcresult`.
- iOS Simulator `KnowledgeNoteStoreTests`: `23 passed`, `0 failed`.
- `python3 scripts/generate_product_capability_manual.py --check`: PASS.
- `python3 -m compileall -q backend scripts/hermes_bridge.py scripts/generate_product_capability_manual.py`: PASS.
- Ruff and `git diff --check`: PASS.

## Release fields

- implementation_commit: pending
- remote_sha: pending
- server_before: pending
- server_after: pending
- health_check: pending
- functional_check: pending production Registry/Hermes readback
- rollback_point: Git `77b340109735ecb60a9d150e23d892ed350c3c85`; production release to be captured before switch

## Remaining boundary

The existing `/tmp/Quantumn-1.0.3-40.xcarchive` predates this server-side PCM/Bridge change. No Swift source changed in this task; a compatible `qcp_v1` client can consume the new server tool assembly after deployment. TestFlight upload remains a separate release task and is not claimed here.
