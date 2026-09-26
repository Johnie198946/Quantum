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
8. Three scheduler-owner exits could exhaust a material claim permanently before a healthy retry window.
9. The watchdog's 30-second `subprocess.run` timeout killed the still-attached `hermes cron run` process. Long author and prerequisite executions were therefore persisted as `unknown` even though dispatch had initially succeeded.
10. Rejected-manuscript recovery assigned the content Agent ownership of revision directories, hashes, owner-attestation rebinding, manifest assembly, and server contract fields. This mixed content repair with control-plane repair and made every rejection a bespoke infrastructure intervention.
11. Rejected reviews with structured gaps also emitted a synthetic open `review.rejected` gap. A correctly repaired revision could close every substantive gap and still be blocked by this historical control marker.
12. The shared finalizer loaded every historical manifest before filtering actionable states, so one malformed or incomplete historical item could block a valid approved sibling from staging.
13. An approval recorded under the pre-fix validator became terminal `failed` even though its body, contract, review and native proof were immutable and valid under the corrected validator. Retrying the same finalize could not recover it without manufacturing another content revision.

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
- Allow six bounded claim attempts and retry persisted-but-unchanged dispatches after 15 minutes, so transient gateway restarts do not permanently dead-letter the day's material.
- Start `hermes cron run` in a detached process, poll `executions.db` only until a live `claimed`/`running`/`completed` row appears, and leave that process alive to own the full Agent execution. An `unknown` row is no longer accepted as successful dispatch.
- Add regression tests for stdin upload, timeout classification, and prerequisite-before-author recovery ordering.
- Add deterministic `publication_editorial_remote.py revise`: the author supplies only a revised body, while the platform derives the isolated revision, current Hermes writer identity, hashes, pending bundle/manifest, owner-attestation rebinding, immutable evidence/media reuse, and authoritative remote prepare fields.
- Keep `revision`, `issue_id`, `attempt_id`, `target_hash`, `previous_body_hash`, review identity, stage identity, and publication identity server-owned. Content revisions no longer hand-edit or copy these fields.
- Reuse the prior issue's verified five images for content-only revisions; image generation repeats only when independent review identifies a visual defect or the manuscript's visual thesis changes.
- Stop adding synthetic `review.rejected` when a rejected review already provides structured substantive gaps. Retain a narrowly matched compatibility rule so already-prepared revision 2 attempts are not forced into a fake content revision solely to remove that legacy marker.
- Make the shared finalizer filter for `await_review` before strict manifest loading and isolate invalid pending histories, matching the reviewer selector's per-item failure boundary. One broken book can no longer block a valid approved sibling.
- Permit a terminal `failed` approval to self-heal only when the exact same contract and review hash are resubmitted and the full current editorial/provenance gate passes. The service records the already-verified proof and advances that same attempt; it does not alter content or consume a new revision.
- Reuse an already-written immutable signed proof on finalize retry instead of asking a completed reviewer session to emit a second review request. Isolate per-manifest runtime failures so a broken sibling retains its retryable state without preventing a valid sibling from staging.

## Compatibility and rollback

- Remote blob paths, hashes, API payloads, manifest schema, review/finalize semantics, and exact-SHA deployment contracts are unchanged.
- Initial manuscript packaging remains compatible. The new `revise` action is additive; legacy rejected attempts keep their immutable bytes and are handled by the exact legacy-marker compatibility predicate.
- The legacy chunk upload handler remains accepted by the remote service code; only this client switches to stdin streaming.
- Rollback is the previous three scripts. Reinstall matching copies into `~/.hermes/scripts/` and verify SHA-256 equality.

## Verification

- Publication test modules: `282 passed`.
- Ruff: passed.
- `git diff --check`: passed.
- Installed runtime scripts were hash-compared with repository copies.
- Idempotent production prepare for today's `ai-history` completed successfully in `0.96s`, versus the observed multi-minute chunked path.
- Today's manifests remain governed by independent review; no review decision or image gate was bypassed.
- Content-only revision, immutable approval recovery, proof reuse and per-item isolation regressions are included in the focused publication suite; the latest focused run before commit passed `183` tests, Ruff, and `git diff --check`.

## Content/supply contract correction and scheduled smoke acceptance

- Reaffirmed that authors own only manuscript content and genuinely requested source/experiment/visual evidence. Revision/issue/attempt/target identities, hashes, receipts, review linkage, stage/publication identities and execution claims remain deterministic platform fields; missing control metadata is a pipeline defect, not author work.
- Replaced the tutorial-supply batch-completeness gate with a per-issue sufficiency gate: one verified, authorized, compiled selected candidate can feed one issue. Category coverage is descriptive and optional; unselected candidate failures cannot block the selected candidate.
- Fixed production timing in config and prompt: 01:00 collection/deposit, selected-candidate compilation by 03:00, first author consumption at 08:05, then independent review, finalize, release and reader readback.
- Updated Cron `b8c4c5e40bb1` so queued compilation is `WAITING_COMPILATION`, task-level stale/conflicting items are non-blocking, and READY requires exact selected-item compilation readback.
- Updated Cron `171a125ddb63` to consume one compiled selected candidate and to reject all requests for author-written control-plane fields.
- Added a temporary no-agent scheduled smoke script. Foreground preflight passed eight isolated control-plane checks in 25.29 seconds. The first native one-shot (`bed3a087bf4f`) correctly exposed scheduler-venv drift (`pytest` absent). After pinning `/usr/local/bin/python3`, the second run produced a valid artifact but the stale Desktop-owned `doc-maker serve` process incorrectly terminalized its ledger row as `unknown`. There were no active executions owned by that process, so it was terminated and its Desktop supervisor respawned PID `76276` with current runtime code. The third native one-shot (`15fcf1f451df`) then completed durably: execution `6415df1e030c4fc399e20f6bdb6bfa3a`, ledger `status=completed`, eight checks passed, exact canonical/installed script SHA `cd50a7fe9f06577e844f0cc2b1345f4fcaf68004c00f5c5805f47741450573f1`, and `production_mutated=false`.
- All three temporary Cron definitions and the temporary smoke script were removed after preserving execution/output evidence.
- Post-change focused suite: `114 passed`; Ruff and `git diff --check` passed.
- The smoke is intentionally non-production and cannot replace a native production publication/readback cycle. Story remains unaccepted because its canonical FileProvider worktree still returns `Interrupted system call`/Git timeout and was not modified.
