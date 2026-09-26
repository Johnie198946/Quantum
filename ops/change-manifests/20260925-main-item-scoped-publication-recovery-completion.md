# Main item-scoped publication recovery

task_id: 20260925-main-item-scoped-publication-recovery
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/quantum-2.0-publication-main
head/local_commit: pending task commit; read with `git rev-parse HEAD` after commit (SHA is not embedded to avoid self-reference)
remote_sha: 2866034c409cec35ee951c01dd1ba8f76709d3a5 (current GitHub main; retry-policy follow-up not yet pushed)
server_before: production retry policy permits only one same-body gap-closure attempt after four failures; revision 5 rejection therefore blocks a valid revision 6 repair
server_after: NOT_DEPLOYED; local tested change permits only materially changed candidates that exactly close every latest open review gap
health_check: pending deployment authorization
functional_check: retry-policy/editorial relay/release/watchdog regression set passed locally (122 tests)
rollback_point: current deployed/GitHub SHA 2866034c409cec35ee951c01dd1ba8f76709d3a5
manifest: ops/change-manifests/20260925-main-item-scoped-publication-recovery-completion.md
remaining_risks: retry-policy fix is local only until explicit push and deployment authorization; production revision 6 cannot be prepared before exact-SHA deployment; Story remains a separate blocked chain

## Inventory and scope

- Started on local `main` at `9871743416f6e39d06a62d4057aaca5107c69161`; `origin/main` was fetched and already matched.
- Preserved the unrelated untracked `build_20260924_issues.py` without reading or modifying it for implementation.
- Replaced timestamp-based phase inference in `scripts/publication_scheduler_watchdog.py` with validated manifest item/material barriers and production day readback.
- Installed the tested script copy at `~/.hermes/scripts/publication_scheduler_watchdog.py`; source and installed hashes matched. The unsafe LaunchAgent remains unloaded. Recovery runs through no-agent Hermes cron `94f82c141295` every ten minutes with failure delivery to the origin chat.

## Safety properties

- Recovery is restricted to the default Hermes home/profile and strips inherited `STORY_*` credentials.
- Five media hashes and editorial manifest invariants are delegated to the existing `publication_editorial_remote.load_manifest`; invalid daily candidates fail closed.
- Review dispatch claims the deterministic first global pending manifest, matching reviewer input order; an older out-of-scope pending item blocks instead of being skipped.
- Prepare and finalize use the existing gate-enforcing editorial client; staged items are left to the existing deterministic publisher, so recovery cannot create a second publisher.
- Item/day/material/phase idempotency keys are inserted atomically in SQLite before dispatch; shared-author scope claims every affected item in one transaction.
- Agent dispatches enter `dispatched` rather than `completed`; absent progress is eligible for bounded retry only after a 45-minute reconciliation window, with at most three attempts.
- `unknown` executions with a durable terminal timestamp are treated as dead owners only after current manifests, review artifacts, and production status are reconciled. A live or unverifiable owner still blocks recovery.
- Failure alerting no longer invokes the publication delivery/release job.

## Verification

- `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q tests/test_publication_scheduler_watchdog.py`: **27 passed**, 4 existing Pydantic deprecation warnings.
- `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q tests/test_publication_editorial_remote.py tests/test_publication_release_remote.py`: **43 passed**, 4 existing Pydantic deprecation warnings.
- `python3 -m ruff check scripts/publication_scheduler_watchdog.py tests/test_publication_scheduler_watchdog.py`: **passed**.
- `git diff --check`: **passed**.
- Broad `tests/test_*publication*.py`: **272 passed**, 4 existing Pydantic deprecation warnings. Two stale remote-release assertions were updated to the already-shipped richer `today.by_series` observability shape (`published`, `body_available`, `media_roles`).
- Recovery supervisor suite: **28 passed**, including concurrent-publication reconciliation.
- Focused end-to-end publication regression set (recovery, remote release, editorial relay, review input, daily completion): **99 passed**; Ruff and `git diff --check` passed.
- First scheduled live execution: day `2026-09-25`; planner detected the in-flight ai-toolkit manifest hash mismatch, returned `invalid_manifest`, and dispatched nothing. A subsequent fix allows finalized items in other series to progress while the invalid series itself remains fail-closed.

## Revision 6 governed retry follow-up

- Revision 5 independently rejected the candidate because the successful five-document Codex chain was not evidenced and `illustration_02` did not clearly bind the beige note to the inner straight handle.
- The repaired candidate now binds a fresh empty-directory Codex replay with five `file_change` events, `turn.completed`, five output hashes, and the same checker returning `OK`; the corrected image binds built-in image-generation events, current PNG/JPEG hashes, and a separate read-only final inspection ending `FINAL_DECISION: PASS`.
- Production correctly rejected the next prepare with `editorial retry limit reached`: the old policy allowed exactly one same-body closure attempt after four failures, so a new reviewer-requested body/evidence correction could not enter revision 6 after revision 5 was rejected.
- The follow-up changes the post-budget gate rather than bypassing review: the latest attempt must be terminal `failed`/`rejected`; every inherited open gap must be present with the exact question and a non-empty resolved resolution/source list; and the resulting input hash must differ from the latest attempt. Identical retry loops and dropped/reworded gaps remain blocked.
- Verification: `tests/test_publication_editorial_workflow.py`, `tests/test_publication_editorial_remote.py`, `tests/test_publication_remote_release.py`, and `tests/test_publication_scheduler_watchdog.py` — **122 passed**, with four existing Pydantic deprecation warnings. Ruff and `git diff --check` passed.
- No production database was edited and no rejected review was overwritten. The production fix remains undeployed pending explicit GitHub push and deployment authorization.
