# JEV semantic capability migration completion receipt

- canonical_task: `hermes-jev-semantic-capability-migration`
- parent_change: `ops/change-manifests/jev-bridge-latency-precision-refactor-20260925-completion.md`
- implementation_commit: `68d57c3f810c2ea465325532a12121fc2cd4e6d5`
- status: `COMMITTED_LOCAL_NOT_PUSHED`
- date: `2026-09-25`

## Scope completed

1. Replaced the detached Bridge export surface with a live owner-module compatibility facade. Private reads, rebinding, and mutable-state replacement now resolve against the runtime owner module. `scripts/hermes_bridge.py` is 145 lines and remains the HTTP/composition root.
2. Added governed PCM Skills:
   - `requirements-clarification`
   - `personal-knowledge-action`
   - `skill-authoring`
3. Projected the existing single JEV decision into the active Hermes turn. JEV still returns at most one Skill and one Agent; no second router, Registry, Runtime, or model call was added.
4. Removed Bridge/API keyword selectors for Drill-me, note actions, and Skill authoring. `chat_triage` remains responsible only for inference/evidence policy and authorized tool-surface narrowing.
5. Preserved QCP as the only authorization ceiling:
   - authorized Skill IDs use canonical `skill:<name>` IDs;
   - unsigned client feature flags cannot enable personal-knowledge writes;
   - Skill authoring requires `tenant_skill_manage`, same-turn JEV selection, tenant-private sandbox writes, controlled loading, SHA-256 receipts, and a tenant-local audit log;
   - sensitive Skills declare `agent: forbidden`; an invalid Skill+Agent combination is rejected inside JEV validation rather than rewritten downstream.
6. Preserved deterministic protocols:
   - requirements clarification records rounds, requires the configured minimum, and permits timeout/cancel as the explicit recovery boundary;
   - personal-knowledge writes retain proposal/confirmation separation, verified identity context, and no-delegation enforcement;
   - Workflow, Session, idempotency, queue, approval, and SSE lifecycle remain outside JEV.
7. Changed resident candidate selection to rank Skill and Agent cards together and send at most five total candidates to the sole JEV call. The provisioner now writes `shortlist_total: 5` while runtime remains backward-compatible with the former setting.

## Verification

### Focused regression

```text
Affected Bridge/JEV/API/runtime suite:
395 passed, 1 skipped

Final semantic protocol + Bridge/note suite:
91 passed

Final selector/stream focused suites:
37 passed
86 passed
```

### Static checks

```text
ruff: All checks passed
py_compile: passed
git diff --check: passed
Bridge facade: 145 lines, 5,748 bytes
```

### Full repository comparison

Baseline recorded before this phase:

```text
2337 passed / 17 skipped / 37 failed / 99 errors
```

Full repository run during final convergence:

```text
2347 passed / 17 skipped / 38 failed / 99 errors
934.15s
```

The only failure above the existing `37 failed / 99 errors` baseline was
`test_formal_skill_cards_preserve_governed_boundaries_and_candidate_budget`.
That run had collected the test before the combined-five shortlist patch was
applied. The final implementation and that test were then rerun successfully
in the final focused suites above. No unresolved failure attributable to this
change remains. Existing dependency/database/authentication failures remain out
of scope and were not represented as green.

### Routing-quality proxy

The resident embedding shortlist was exercised against the seven runtime Skill
cards. All three new Skill primary phrases retained their own Skill in the
combined top-five shortlist (`3/3`). Formal Skill tests also validate positive,
negative, attack, tenant-isolation, QCP-ID, same-turn selection, no-delegation,
and total-candidate-budget contracts.

### Adversarial review

Review blockers found and fixed:

1. bare Skill names did not match canonical `skill:<name>` authorization IDs;
2. an unsigned client feature flag could enable knowledge actions on some paths;
3. downstream Agent suppression rewrote a JEV decision;
4. the initial candidate bound was five per kind rather than five total.

Final convergence review: `无新增实质问题`.

## Boundaries

- No push.
- No deployment.
- No Gateway restart.
- No external knowledge/research deposit claimed.
- Unrelated file `ops/change-manifests/build48-selected-text-gate-20260924-completion.md` was not staged or modified.
