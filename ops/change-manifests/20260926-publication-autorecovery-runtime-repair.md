# Publication auto-recovery runtime repair

## Date

2026-09-26

## Problem

The daily publication recovery path still required intervention even though the repository watchdog logic had already learned the two author-job scopes.

Observed failures:

1. The installed `~/.hermes/scripts/publication_scheduler_watchdog.py` had drifted from the repository source and routed every author recovery to the `ai-toolkit` author job. Rejected or missing `ai-history`, `ai-practice`, and `concept-fables` items therefore could not be repaired by their own author job.
2. Editorial evidence upload opened one SSH connection per 24 KiB chunk. A normal five-image issue needed hundreds of SSH handshakes, causing prepare runs to take more than seven minutes and sometimes exceed the recovery execution budget.
3. Recovery failures were reported only as a generic trigger failure, so timeout and non-zero action failures could not be distinguished.
4. Once an approved item became `staged`, the status API correctly removed it from `issues.missing` while `by_series.published` remained false. The watchdog incorrectly required those two different projections to be equal and stopped all later recovery.
5. The installed watchdog launched the editorial client without a verified repository module path, so automatic prepare/finalize failed with `No module named 'backend'` while foreground commands that explicitly set `PYTHONPATH=.` succeeded.
6. Shared author jobs judged only production `published` state. They could therefore rewrite a sibling series already handed off as `prepared`, `await_review`, or `staged`, so the watchdog had to stop with `ambiguous_author_scope` instead of repairing a rejected sibling.
7. `hermes cron run` waits for the whole Agent execution. After a scheduler restart had already terminalized the owner as `unknown`, the CLI could still wait and keep the watchdog lock held, making every native 10-minute recovery tick return `locked`.

## Change

- Keep the repository's series-to-author routing map as the runtime source and reinstall the watchdog from that source.
- Replace per-chunk SSH evidence upload with one bounded stdin stream per file while retaining the 2 MiB size limit, SHA-256 verification, extension allow-list, immutable blob path, and server-side idempotency.
- Add SSH connect and keepalive bounds so dead transports fail into the existing bounded retry path.
- Classify recovery outcomes as `action_timeout`, `action_exit_nonzero`, or `action_exception` without exposing credentials or remote stderr.
- Treat `by_series.published` as the complete unpublished-set truth and validate `issues.missing` as a non-contradictory subset, allowing staged items to proceed to the deterministic release schedule.
- Resolve and validate the repository root, then replace inherited `PYTHONPATH` with that exact root for every watchdog subprocess.
- Claim only series that actually require author work. Persisted author-job guards now skip immutable `prepared`, `await_review`, and `staged` handoffs even while production still reports unpublished.
- Bound Agent dispatch to 30 seconds and require a newly persisted execution row even when the CLI exits zero; classify a zero-exit/no-row response as `dispatch_not_persisted`. The watchdog releases its lock after verified dispatch instead of waiting for long author/reviewer completion.
- When `ai-toolkit` carries a machine-readable `BLOCKED_TUTORIAL_PREREQUISITE` marker, automatically dispatch the governed tutorial-supply job using the marker hash for bounded idempotent retries, without blocking unrelated series while a separately scheduled supply run is active.
- Dispatch tutorial supply first; only a later machine receipt with `READY_FOR_AI_TOOLKIT` allows the toolkit author phase. Supply and author no longer run concurrently.
- Pin the tutorial-supply job to `gpt-5.6-sol` / `openai-codex`, require every adopted URL to be opened and verified, and require a machine-readable `READY_FOR_AI_TOOLKIT` or `BLOCKED_DEPOSIT` receipt. Cron configuration was read back after the edit.
- Add regression tests for stdin upload, timeout classification, and prerequisite-before-author recovery ordering.

## Compatibility and rollback

- Remote blob paths, hashes, API payloads, manifest schema, review/finalize semantics, and exact-SHA deployment contracts are unchanged.
- The legacy chunk upload handler remains accepted by the remote service code; only this client switches to stdin streaming.
- Rollback is the previous three scripts. Reinstall matching copies into `~/.hermes/scripts/` and verify SHA-256 equality.

## Verification

- Publication test modules: `282 passed`.
- Ruff: passed.
- `git diff --check`: passed.
- Installed runtime scripts were hash-compared with repository copies.
- Idempotent production prepare for today's `ai-history` completed successfully in `0.96s`, versus the observed multi-minute chunked path.
- Today's manifests remain governed by independent review; no review decision or image gate was bypassed.
