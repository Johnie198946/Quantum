# Note quality and latency acceptance follow-up

task_id: note-quality-acceptance-20260927
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
head_at_start: b696d13bdcef18cc23b1707dc00501ca012ee224

## Goal and architecture

Continue failed acceptance: improve lexical recall without declaring semantic conclusions, enable complete-body batch review through existing PCM, remove repeated device upload, and move first-call PCM imports into existing worker prewarm. Reuses note snapshots, knowledge.note.search/read/compare, Hermes request workspace, existing run_knowledge_read admission gate, and existing CloudKnowledgeNotesResponse. No new service, persistent cache, authority model, or dependency.

Files owned: backend/services/user_note_context.py; note-only hunks of backend/capability_handlers.py and backend/contracts/product-capabilities/capabilities.yaml; generated PCM manual/coverage; scripts/hermes_bridge_runtime/knowledge.py and agent_config.py; tests/test_user_note_context.py, test_cleanup_capabilities.py, test_client_session_notes.py; ios/AIPlatformApp/Services/KnowledgeNoteStore.swift. Reader task owns KnowledgeView snapshot deduplication and joint iOS checks, deployment. Media task owns unrelated hunks in shared PCM files; never stage them as this task.

## Start inventory

Canonical pwd; main tracking origin/main, HEAD b696d13bdcef18cc23b1707dc00501ca012ee224; no local commits ahead at start. origin https://github.com/Johnie198946/Quantum.git; source https://github.com/Johnie198946/ai-lab-platform.git. Worktrees: canonical main and independent travel-notes c1c5788c7a94a25f8f4cb6ed81c50614b4feeba1. Initial dirty AGENTS.md, prior manifests/receipts preserved. Coordinated reader and media changes remain separate. Applicable canonical AGENTS prescribes main-only, and this existing task continues its canonical checkout.

## Validation

- 108 backend tests passed: user_note_context, cleanup_capabilities, product_capabilities, client_session_notes. Log /private/tmp/note-quality-tests-final.log. Includes full-body paging with oversized notes, tenant-field denial, full-body workspace reuse, truthful scan progress, single-snapshot compare, and startup-only handler import.
- Static check: git diff --check passed; final Ruff result recorded below when complete.
- Read-only production snapshot benchmark: 135 notes, original36 candidates, new68 (duplicate1, partial_overlap36, similar_content_candidate18, same_topic8, reference5). New initial implementation1282.8ms, standard integer-bitset implementation307.7ms; old same-run22.4ms. This increases recall but adds ~285ms scan work. Counts do not establish semantic precision or full review.
- Existing PCM independent-process profile: first call10400.1ms, warm86.7/84.5ms, dominated by module compilation/Pydantic startup. New warmup only imports modules; no identity, note retrieval, or capability execution at startup. Actual Chat improvement remains to be measured after deploy.
- Production notes stayed on server; benchmarks returned only counts, relations and timing. No note body or private per-file manifest exported, no note mutation performed.
- iOS joint tests and device acceptance pending reader task. Return the same authenticated restore response to existing view; skip only matching content hash AND lifecycle state, preserve credentials/account guards and cancellation.

commit: pending
remote_sha: pending; start b696d13bdcef18cc23b1707dc00501ca012ee224
server_before: b696d13bdcef18cc23b1707dc00501ca012ee224
server_after: not deployed for this follow-up
health_check: pending exact committed deployment
functional_check: local checks above; complete semantic review, actual UI and latency acceptance pending
rollback_point: deployment owner must establish before new release; prior release /opt/releases/ai-lab-platform-b696d13bdcef.82EYgj
remaining_risks: pairwise integer comparisons scale quadratically with owner note count; benchmark covers135. Lexical candidates are not semantic decisions and cannot authorize archive. Full-body batches must follow next_offset; only actual read bodies count as reviewed. Build69 is already testing; Build70 will use only tested committed source. Unrelated media and publication work must be coordinated, not silently bundled.

## Joint local validation

Reader owner reports213 iOS unit tests (KnowledgeNoteStoreTests and WorkflowLifecycleDTOTests) and3 UI tests passed; final reader UI delta remains its separate scope. Ruff passes changed note handlers/services/tests; agent_config has the same3 F811 duplicate-import diagnostics reproduced from HEAD, no new diagnostic. git diff --check passed. PCM generated documents independently match a clean HEAD catalog plus only knowledge.note.search changes, excluding media work.
