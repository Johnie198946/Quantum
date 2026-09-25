# Main item-scoped publication recovery

task_id: 20260925-main-item-scoped-publication-recovery
status: DEPLOYED_LOCAL
branch: main
worktree: /Users/dengzhaoyu/Projects/quantum-2.0-publication-main
head/local_commit: task commit containing this manifest (read with `git rev-parse HEAD`; SHA is not embedded to avoid self-reference)
remote_sha: 9871743416f6e39d06a62d4057aaca5107c69161 (pre-task fetch; no push authorized)
server_before: local unsafe LaunchAgent copy disabled and unloaded
server_after: local no-agent Hermes cron `94f82c141295`, every 10 minutes; installed script SHA-256 `a3b6062d9fb36cec2005f7b5d3d59524f9e04b940c7b9cbe050f244df2f77929`
health_check: first scheduled run at 16:10 executed and failed closed on a concurrently edited invalid ai-toolkit manifest without dispatching duplicate work
functional_check: full publication regression and focused recovery tests passed; scheduled production execution observed
rollback_point: git checkout of the three task files from 9871743416f6e39d06a62d4057aaca5107c69161
manifest: ops/change-manifests/20260925-main-item-scoped-publication-recovery-completion.md
remaining_risks: GitHub push is not authorized; Story remains a separate blocked chain; current same-day content completion is still in progress; four transient `prepare-r2*` files created by the active author task were removed after bounded inspection

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
