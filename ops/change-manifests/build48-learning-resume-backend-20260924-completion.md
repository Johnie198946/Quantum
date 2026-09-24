# Completion Manifest

- task_id: `build48-learning-resume-backend-20260924`
- goal: Replace the build 48 “先帮你找回思路” hard-coded learning points with a backend resume projection and restore reading to the recorded paragraph and character.
- changed_files:
  - `backend/api/subscriptions.py`
  - `backend/db.py`
  - `backend/models/tenant.py`
  - `ios/AIPlatformApp/Networking/APIClient.swift`
  - `ios/AIPlatformApp/Views/Chat/Components/ChatMessageStreamView.swift`
  - `ios/AIPlatformApp/Views/Settings/SettingsView.swift`
  - `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
  - `tests/test_book_subscriptions.py`
  - `ops/change-manifests/build48-learning-resume-backend-20260924-completion.md`

## Start inventory

- status: clean task worktree at creation; source checkout had unrelated modified manifests and was not edited
- branch: `codex/build48-learning-resume-backend`
- HEAD: `54eb24dfabe9e05dedd42b05a62d5d0e66ef1693` (build 48)
- remote: `origin https://github.com/Johnie198946/Quantum.git`
- worktree: `/Users/dengzhaoyu/Documents/AI Lab/.worktrees/quantum-build48-learning-resume-backend`
- baseline sync: `git fetch origin main` completed; task intentionally targets the build 48 commit requested by the user

## Implementation

- Reused the existing versioned book subscription checkpoint and reader sections.
- Added `last_section_id`, `last_block_index`, and `last_character_offset` to the existing subscription row and additive startup migration.
- Extended the existing progress write contract with a validated section/block/character checkpoint.
- Added `GET /api/v1/me/learning-resume`, returning the latest readable subscription, exact paragraph checkpoint, and exactly two points extracted from that section's governed body.
- Replaced the two iOS hard-coded mathematical points and percentage-derived resume section with the backend projection.
- Reused TextKit to record the rendered paragraph's UTF-16 character offset and restore the corresponding glyph to the reading line.
- Kept completion percentage monotonic while allowing the latest section position to move backward during review.

## Tests and checks

- `python3 -m pytest tests/test_book_subscriptions.py -q`: 12 passed.
- `python3 -m pytest tests/test_book_progress_legacy.py -q`: migration test passed; 11 HTTP tests blocked by the existing Starlette/httpx incompatibility (`Client.__init__() got an unexpected keyword argument 'app'`).
- `xcodebuild ... -only-testing:...testBookWritesMatchBackendWireContract -only-testing:...testLearningResumeDecodesExactSectionAndTwoPoints`: 2 passed.
- `git diff --check`: passed.
- `python3 -m py_compile backend/api/subscriptions.py backend/db.py backend/models/tenant.py`: passed.

## Delivery

- status: `TESTED`
- commit SHA: not requested; not created
- GitHub remote/ref/SHA: release authorized; pending final integration commit and remote verification
- server_before: `/opt/releases/ai-lab-platform-92d7d273fc94.iJAvgh`, `.deployed-sha=92d7d273fc94052a696183ebc36dedc8cd7093d4`; `/health` and `/ready` passed before release
- server_after: pending exact-SHA deployment
- health_check: pending exact-SHA deployment
- functional_check: backend and iOS contract tests passed locally
- rollback_point: build 48 baseline `54eb24dfabe9e05dedd42b05a62d5d0e66ef1693`; local changes can be discarded by removing this isolated worktree after review

## Risks and remaining work

- Existing checkpoints created before this change have no exact tuple; the resume endpoint intentionally falls back once to their versioned percentage until the reader records a new position.
- Character offsets are UTF-16 indices, matching `NSString`/TextKit. Non-text blocks resume at their block boundary (`character_offset = 0`).
- Key points are deterministic extracts from the last section, not an LLM-generated summary; add model summarization only if product evaluation shows extraction quality is insufficient.
- Push, production deployment, and TestFlight upload were authorized after local verification and are in progress.
