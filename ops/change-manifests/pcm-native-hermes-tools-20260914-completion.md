# Completion Manifest

- task_id: `pcm-native-hermes-tools-20260914`
- status: `VERIFIED`
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
- iOS Simulator `KnowledgeNoteStoreTests`: `23 passed`, `0 failed`.
- iOS Simulator `WorkflowLifecycleDTOTests`: result remains unverified. Both attempts were interrupted by orphan recovery, so no pass count is claimed.
- `python3 scripts/generate_product_capability_manual.py --check`: PASS.
- `python3 -m compileall -q backend scripts/hermes_bridge.py scripts/generate_product_capability_manual.py`: PASS.
- Ruff and `git diff --check`: PASS.

## Release fields

- implementation_commit: `3444d3b08b1bedb674ca91deaef7ea97bf74522c`
- remote_sha_at_deploy: `3444d3b08b1bedb674ca91deaef7ea97bf74522c` (verified by `git ls-remote` before deployment)
- server_before: `8e259b37a67d034af853864c99bfc313a5ec3a6e`; release `/opt/releases/ai-lab-platform-8e259b37a67d.wN9l4P`
- server_after: `3444d3b08b1bedb674ca91deaef7ea97bf74522c`; release `/opt/releases/ai-lab-platform-3444d3b08b1b.Fup8VU`
- backend_image: `sha256:2753ee24f37bab6e6ec5c0476b1a6e8fc1e9cad8778100123256baa240aaf56f`; all four backend service image labels read back the implementation SHA
- source_archive_sha256: `aec1127412154fbac16ae063bcf4619a18e308fe045ac1fdf07a1c8e3a926711`
- health_check: PASS; API `/ready` returned `ready`, Bridge returned `ok`, both Hermes services were active, and `https://t-react.com/health` returned `ok`
- functional_check: PASS; a fresh production Hermes process compiled `16/16` Registry capabilities into native tools, reported no missing tools, exposed the PPT/workflow/knowledge tools, and exposed none of the three search/describe/invoke meta-tools
- rollback_point: `/opt/releases/ai-lab-platform-8e259b37a67d.wN9l4P`; the prior backend images were also preserved under `rollback-8e259b37a67d034af853864c99bfc313a5ec3a6e` tags
- verified_at: `2026-09-14T15:35:11+0800`

## Deployment recovery note

The first standard deployment attempt stopped before any runtime switch because the private GitHub codeload URL returned `404`. The first offline-source retry also stopped before runtime mutation because its locally generated archive lacked the required top-level prefix. A correctly prefixed, SHA-256-verified Git archive was then installed at the allowlisted root-owned offline-source path. The next attempt correctly stopped on the old backend image revision; a linux/amd64 backend image was built from the exact implementation commit, transferred with SHA-256 verification, loaded and attested, after which the exact-SHA deployment completed. Production remained on the previous release throughout all failed preflight attempts.

## Remaining boundary

The existing `/tmp/Quantumn-1.0.3-40.xcarchive` predates this server-side PCM/Bridge change. No Swift source changed in this task; a compatible `qcp_v1` client can consume the new server tool assembly after deployment. TestFlight upload remains a separate release task and is not claimed here.
