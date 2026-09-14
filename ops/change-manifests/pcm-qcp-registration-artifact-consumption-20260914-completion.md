# PCM/QCP registration and structured artifact consumption completion

task_id: pcm-qcp-registration-artifact-consumption-20260914
status: DEPLOYED; TESTFLIGHT_ARCHIVED_UPLOAD_BLOCKED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-ios-document-ppt-final-20260912
head/local_commit: 8e259b37a67d034af853864c99bfc313a5ec3a6e
remote_sha: 8e259b37a67d034af853864c99bfc313a5ec3a6e (verified after push)
server_before: f03c233a67b265975dc4a92664622062a5ceeac6
server_after: 8e259b37a67d034af853864c99bfc313a5ec3a6e
health_check: PASS (`https://t-react.com/health` -> `{"status":"ok","version":"0.8.0"}`)
functional_check: PYTHON_RELATED_290_PASS; IOS_SIMULATOR_178_PASS
rollback_point: git 9b959309dd6b15624ff864321833700380fc7db5; production release f03c233a67b265975dc4a92664622062a5ceeac6
manifest: ops/change-manifests/pcm-qcp-registration-artifact-consumption-20260914-completion.md
remaining_risks: TestFlight build 40 upload is blocked by the local Xcode account credential (`Failed to Use Accounts`; missing Xcode-Username). Production destructive invoke was deliberately not run; production Registry search/describe and invoke fail-closed were verified.

## Final P1 durable semantic status recovery

1. Durable status now filters the existing persisted run event log against PCM Catalog event IDs, returns at most 100 original envelopes after the caller offset, and exposes `events_next_offset` without skipping a later page. No storage or Runtime was added.
2. `_check_cached_answer` now copies those persisted envelopes into `ChatResponse.events` for non-streaming cache recovery.
3. iOS status decoding includes run/event cursor metadata and QCP events. Completed/failed handling writes events through the existing capability dispatcher or `appendCapabilityBlock`, checkpoints the owning session, then persists the cursor; only a fully drained, checkpointed completed status is acknowledged and settled. Invalid artifact receipts leave the message recoverable and do not advance the cursor.
4. Added regressions for session-switch completion, pre-first-SSE-frame restart, Catalog filtering, the 100-event bound and multi-page drain, status DTO decoding, original-session persistence, and invalid receipt fail-closed behavior.

### Final P1 verification performed

- `python3 -m pytest -q tests/test_chat_status.py tests/test_chat_api.py tests/test_chat_stream_api.py tests/test_chat_run_worker.py tests/test_artifact_structured_consumption.py tests/test_product_capabilities.py`: **158 passed, 8 warnings**.
- `xcodebuild -quiet -project ios/AIPlatformApp.xcodeproj -scheme AIPlatformApp -configuration Debug -destination 'generic/platform=iOS' -derivedDataPath /tmp/pcm-qcp-derived-data CODE_SIGNING_ALLOWED=NO OTHER_SWIFT_FLAGS=-disable-sandbox build-for-testing`: passed with exit code 0; App, unit-test and UI-test targets compiled.
- Parent simulator acceptance completed after the sandbox build: **178 passed, 0 failures**; xcresult `/tmp/pcm-qcp-final.xcresult`.
- `git diff --check`: passed.
- No fetch, commit, push, deployment, upload, server access or remote write was performed.

## Final P1 iOS semantic receipt remediation

1. Added a typed, persisted `ArtifactConsumptionBlock` containing only receipt/artifact/hash/schema/time/status plus a canonical JSON preview capped at 600 characters. `receipt_id` is the block identity and deduplication key; the full structured payload is never persisted.
2. Non-streaming chat, live SSE and durable replay use `ChatMessage.appendCapabilityBlock(from:)`. Live capability events retain their run sequence in `QCPStreamEvent`; artifact cards use the existing atomic `checkpointRunProjection` before the sequence is advanced. Durable replay likewise refuses to advance on an invalid or failed receipt checkpoint.
3. `PersistedMessage` round-trips artifact consumption cards while its optional field keeps old history decodable. `BlockCardDispatcher` renders a light, read-only brand card labelled only “已消费/回执”, with a shortened hash and no immutability claim.
4. Added XCTest coverage for event decoding/live sequence metadata, non-streaming append, receipt deduplication, bounded preview, legacy/round-trip persistence and durable replay ordering.

### P1 verification performed

- `git diff --check`: passed.
- Generic iOS Simulator `xcodebuild ... build-for-testing`: passed once after the P1 implementation and test additions (`** TEST BUILD SUCCEEDED **`).
- Selected simulator XCTest initially ran 3 tests: non-streaming and persisted round-trip passed; durable replay reached the in-memory card but its 20-yield polling assertion ran before the SQLite checkpoint completed. The test now waits up to one second in 10 ms intervals.
- Parent reran the adjusted durable replay test and both related suites on simulator `8386FBF2-321F-4F52-BF4C-337EF3780649`: **154 passed, 0 failures**. The durable receipt card, non-streaming event path, live metadata, persistence round-trip and replay ordering all passed.
- No fetch, commit, push, deployment, upload, server access or external write was performed.

## Review 2 remediation

1. Non-streaming `/api/chat` now returns the Bridge's original QCP semantic event envelopes. `_call_hermes` and `_call_hermes_recorded` return `(reply, reasoning, events)`; normal, skill, delegated child/main, and streaming delegated fallback call sites preserve events. Delegated child and parent events are ordered and combined. Bridge event selection derives QCP event IDs from the existing PCM catalog rather than copying a second protocol list.
2. The legacy `note_draft` post-processing fallback is gated by `_legacy_client_context_enabled(...)`, which is permanently false. A QCP-only save-request regression proves neither `_user_note_search_tool` nor `_note_draft_tool` is called and no legacy draft event is emitted.
3. iOS decodes non-streaming `ChatResponseDTO.events` into the same `QCPStreamEvent` envelope used by SSE. Non-streaming confirmation events route through `RendererRegistry` into message blocks. Durable replay now calls the same capability dispatcher as live SSE for every capability event, including `artifact.consumed`, and advances `lastEventSequence` only after dispatch.
4. Structured artifact payload traversal rejects every non-finite float with `math.isfinite` before digest or receipt persistence. Real artifacts containing `1e400`, `NaN`, `Infinity`, and `-Infinity` all return structured `artifact_parse_failed` envelopes without a receipt or uncaught exception.

## Verification

- `python3 scripts/generate_product_capability_manual.py` and `--check`: passed; generated manual and coverage files are current.
- `python3 -m compileall -q backend scripts tests`: passed.
- `python3 -m ruff check backend scripts tests`: passed.
- Focused review-2 Python regression set: **126 passed, 8 warnings**.
- Final expanded Python suite (architecture, chat, durable status/worker, client notes, PCM/QCP, structured artifacts, document/presentation, workflows): **290 passed, 8 warnings in 42.37s**.
- `git diff --check`: passed.
- The new `artifact_consumption.py` service-to-API dependency was removed by enforcing ownership directly against tenant-scoped workflow models. The pre-existing QCP integration adapter was moved from `backend/services/capability_handlers.py` to `backend/capability_handlers.py`, so the repository's service layer no longer imports the HTTP layer.
- Parent verification reran generation check, compileall, Ruff, the nine directly modified Python test modules and `git diff --check`: **221 passed, 8 warnings**.
- iOS `build-for-testing` succeeded on simulator `8386FBF2-321F-4F52-BF4C-337EF3780649`.
- Real simulator XCTest for `WorkflowLifecycleDTOTests`, `KnowledgeNoteStoreTests`, and `ChatResponseRecoveryRegressionTests`: **178 passed, 0 failures**. xcresult: `/tmp/pcm-qcp-final.xcresult`.
- The first simulator run exposed an invalid test setup that called non-streaming response application without its real pending placeholder; the fixture was corrected to reproduce the production path, then the full 154-test selection passed.

## Not performed

The implementation/review subprocesses performed no remote writes. Parent release actions and receipts are recorded separately below after deployment.

## Release and runtime receipts

- Implementation commit: `8e259b37a67d034af853864c99bfc313a5ec3a6e`; local `main` and GitHub `origin/main` were read back equal after push.
- Production release symlink: `/opt/releases/ai-lab-platform-8e259b37a67d.wN9l4P`; `.deployed-sha` read back as `8e259b37a67d034af853864c99bfc313a5ec3a6e`.
- Production API, workflow worker, planning worker and agent-evaluation worker all run the offline image labelled with the same implementation SHA; Compose reports them healthy. `hermes-bridge.service` and `hermes-chat-worker.service` are active.
- Public health readback: `https://t-react.com/health` returned `{"status":"ok","version":"0.8.0"}`.
- Production Hermes Registry process registered all three meta-tools. Registry dispatch verified `app_capability_search` finds `artifact.consume_structured`, `app_capability_describe` reports it `implemented`, and `app_capability_invoke` without trusted tenant/user context returns `trusted_invocation_context_required` (fail-closed). Catalog digest: `83abb82e5bd7eb2b202839f91f4b1c2fd876349d2d5a602bd9a90a08b9cb33d6`.
- iOS Archive `/tmp/Quantumn-1.0.3-40.xcarchive`: version `1.0.3 (40)`, codesign verification passed, provisioning expires 2027-08-30.
- TestFlight upload attempt failed before upload with Xcode `Failed to Use Accounts`: the Keychain credential for the configured developer account is missing `Xcode-Username`. No Apple upload or processing receipt exists for build 40.
