# iOS SQLite lifecycle gate — 2026-09-19

- task_id: `ios-sqlite-lifecycle-20260918`
- status: `VERIFIED CANDIDATE`
- branch: `main`
- base / server_before: `65bcf9cc29fe18994cd163d0d01cf318b89e73a7`
- authorization: commit, push and production deployment approved by the user on 2026-09-19.

## Change

- Reused `SessionManager`'s ordered persistence tail and generation barriers; no second queue or store was introduced.
- Added idempotent, lock-serialized `ChatHistoryStore.close()` and fail-closed `SQLITE_MISUSE` guards.
- Added `SessionManager.shutdown(closeStore:)` to drain queued writes and destructive mutations before caller-owned close.
- Exhausted message batches and failed queued truncate/clear/delete mutations make the first shutdown fail truthfully; regression tests consume the reported failure before final teardown.
- Failed destructive mutations restore the durable projection, preserving messages and topic-promotion state; successful retries remain atomic.
- Background durable-event replay now validates cancellation payloads and exact event versions before advancing a cursor.

## Final pre-commit verification

- iOS simulator selected suites: `166 passed / 0 failed / 0 skipped`.
- `WorkflowLifecycleDTOTests`: `151 passed / 0 failed`.
- `ChatResponseRecoveryRegressionTests`: included in the selected-suite total and passed.
- Local result bundle retained outside the repository.
- `git diff --check`: passed.

## Delivery contract

- Commit and remote SHA: the commit containing this manifest.
- Rollback point: `65bcf9cc29fe18994cd163d0d01cf318b89e73a7`.
- Server deployment does not replace iOS simulator or future device/TestFlight acceptance; no TestFlight upload is claimed.
