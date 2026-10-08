# JEV Architect Routing 2026-10-08 — Completion Manifest

## Scope

Repair MAC/Hermes JEV routing so fragmented, cross-turn architecture requirements can recall an authorized Agency architect candidate without granting access, changing ACL semantics, adding a runtime, or forcing an architect selection.

## Source and workspace

- Repository: `https://github.com/Johnie198946/Quantum.git`
- Branch: `main`
- Base / remote SHA: `388b948630731a63a7a5ba45584c204805f1b7b4`
- Clean implementation clone: `/tmp/quantum-jev-main-fix`
- Original user workspace was dirty and behind remote, so it was not modified.
- An initial temporary feature worktree was created before the repository's root `AGENTS.md` prohibition was discovered. Its diff was moved onto a fresh `main` clone, and the temporary worktree and branch were deleted before completion.

## Changes

- Added a deterministic, labels-only architecture Task Capsule over bounded recent user turns, with labels-only session carry and explicit negation/topic-switch reset.
- Never forwards raw conversation history to the JEV selector; architecture continuity is represented only by deterministic labels, and unrelated or single-dimension new tasks receive no old context.
- Enriched selected Agency architect cards with governed `use_when` and `do_not_use_when` boundaries.
- Preserved the total shortlist bound of five while reserving up to two already-authorized architecture candidates and at least one candidate per available kind.
- Kept JEV output at zero-or-one Skill, Agent, and Capability; the reserve is recall-only and grants no permission.
- Added trusted resident-only shortlist trace fields to `RouteDecision`; external/custom Provider output cannot forge the internal trace.
- Updated `config/pcm-routing-contract.yaml` to version `1.5.0`.

## Tests and verification

- Targeted router/selector suite: `73 passed, 6 warnings`.
- Wider affected routing suite: `258 passed, 1 skipped, 6 warnings`.
- `python3 scripts/generate_product_capability_manual.py --check`: exit `0`.
- `python3 -m compileall -q agency/hermes-plugins/ai-lab-capabilities`: exit `0`.
- `git diff --check`: exit `0`.
- Real configured resident JEV synthetic replay:
  - catalog: `309` Skills, `273` Agents;
  - complex follow-up reserved `agency:security-architect` and `agency:software-architect` without sending raw architecture history to the Provider;
  - Provider selected `agency:software-architect`, confidence `0.87`, cold wall latency `1601.828 ms`;
  - identical stable request hit existing cache in `10.813 ms` wall time with `cache_hit=true`;
  - all 12 counterexamples—including weather topic switches, single-dimension cache/latency questions, and `先不谈`/`忽略`/`取消` boundaries—carried zero raw history, did not revive prior architecture labels, and reserved no architect.
- Acceptance receipt: `ops/acceptance/jev-architect-routing-20261008/receipt.json`, SHA-256 `ba52f503a697d3d001a74e31bc1ec684044cd2b9853e163a8897fd6cfe9bb893`.

A broader diagnostic run also encountered eight failures in native dispatch, research-deposition, and latency-only tests. The same eight tests failed on an untouched `origin/main` checkout; they were not introduced by this change. They are not counted as passing gates.

## Security and architecture invariants

- Hermes remains the only AI Runtime.
- JEV sees only QCP/PCM-authorized candidate cards.
- Candidate reservation cannot add an Agent absent from the authorized catalog.
- JEV still selects at most one independent Agent and cannot grant ACL, tenant, entitlement, `noexport`, color, or disclosure access.
- Route trace is observational and is filtered back to authorized candidate IDs.
- No real tenant-sensitive body or personal knowledge body was used; only synthetic sentences and catalog metadata were replayed.

## Delivery state

- Status: `COMMITTED` in the local isolated `main` clone; not pushed or deployed.
- Local commit: `THIS_COMMIT` (resolve with `git log -1 --format=%H -- ops/change-manifests/jev-architect-routing-20261008-completion.md`).
- Remote SHA after task: not pushed; remains `388b948630731a63a7a5ba45584c204805f1b7b4`.
- Deployment: not performed.
- Runtime restart: not performed.
- Server before / after: not applicable; unchanged.
- Rollback point: base SHA `388b948630731a63a7a5ba45584c204805f1b7b4` plus removal of the local commit.

## Remaining risks

- The current governed contract intentionally remains zero-or-one independent Agent per route. This repair makes the architecture specialist visible and selectable; it does not introduce a second multi-Agent orchestrator.
- Deterministic label rules need production trace sampling after an approved deployment to measure false positives/negatives across real task classes.
- Raw conversation history is intentionally excluded from the selector. Non-architecture elliptical follow-ups may therefore abstain until a QCP-approved safe topic projection exists; Hermes direct handling remains the fallback.
- The installed MAC plugin remains unchanged until push/deployment/restart are explicitly approved and completed.
