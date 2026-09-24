# JEV / Hermes Bridge latency and precision refactor — local completion receipt

- date: `2026-09-25`
- branch: `main`
- base: `873cc27`
- status: `VERIFIED_LOCAL_NOT_DEPLOYED`
- runtime boundary: Hermes remains the only AI runtime; PCM remains the capability catalog; JEV still selects only `0–1 Skill` and `0–1 Agent`; QCP/Bridge keep deterministic authorization and execution controls.

## Changed

1. Replaced goal-keyword platform-toolset expansion in `scripts/hermes_bridge.py` with a stable authorization-driven base:
   - unauthenticated base is only `clarify`;
   - `file`/`terminal` require the explicit `allow_local_files` authority;
   - remaining toolsets are added from signed/authorized request scope;
   - removed `_resolve_dynamic_toolsets` and its natural-language execution keyword list.
2. Reduced unnecessary remote JEV work:
   - Skill and Agent candidate kinds now abstain independently below the existing similarity floor;
   - omitted kinds are not sent to the remote selector;
   - provider outputs may only reference IDs actually sent in the shortlist.
3. Improved exact-decision cache reuse and correctness:
   - opaque `session_id` no longer fragments identical decisions;
   - platform and other semantic task state remain in the cache key;
   - catalog digest now covers semantic card content, not only ID/version;
   - transient/unvalidated provider failures are not cached.
4. Hardened the resident selector:
   - runtime cards are checked against the warmed semantic card text;
   - non-string or out-of-shortlist provider IDs fail closed;
   - at most two remote provider calls run concurrently; saturation fails open immediately instead of queuing behind stuck calls.
5. Updated Bridge/JEV integration tests and all references to the removed helper.

## Verification

### Targeted regression

```text
175 passed, 8 warnings in 13.88s
```

Covered JEV selector/resident/cache behavior, PCM routing contract, Hermes Bridge, Wiki/knowledge adapters, streaming timing, Agency abstention/integration, and Agent OS acceptance.

### Syntax and diff hygiene

```text
python3 -m py_compile <all changed Python files>  # exit 0
git diff --check                                 # exit 0
no _resolve_dynamic_toolsets Python references  # verified
```

### Live JEV acceptance

Three forced-miss rounds over the existing 12-intent set (`36` decisions), plus cross-session cache-hit replay:

```text
Skill strict accuracy:   97.22%
Agent strict accuracy:  100.00%
Joint strict accuracy:   97.22%
Miss P50:              2126.846 ms
Miss P95:              2636.170 ms
Cross-session hit P50:    7.090 ms
Cross-session hit P95:    7.617 ms
```

Compared with the stored pre-change baseline (`miss P50 2193.255 ms`, `miss P95 3404.529 ms`, `hit P95 19.097 ms`), this run observed lower latency. The two runs occurred at different times, so this is evidence of non-regression and directional improvement, not a causal production SLO claim.

One of 36 strict misses selected `skill:prototype-scaffolding` instead of the accepted iOS implementation alternatives. Joint accuracy therefore remained equal to the stored `97.22%` baseline rather than improving.

### Local shortlist proxy

Using each authorized card's primary `use_when` phrase as the query:

```text
Cards evaluated: 579
Expected card retained in top-20: 100%
Expected card above 0.36 kind floor: 100%
```

This validates the changed shortlist mechanics against the current catalog, but is not a substitute for broader human-labelled production utterances.

### Full repository suite

A full run was attempted:

```text
2337 passed, 17 skipped, 37 failed, 99 errors
```

The failures are outside the changed JEV/Bridge surfaces and are dominated by existing environment/state problems (Starlette/httpx `TestClient` incompatibility, authentication/tenant fixture state, workflow rows with empty tenant keys, and unrelated extraction/deposition expectations). Two initially reported chat-stream failures passed immediately when rerun in isolation. The targeted affected-surface suite is green; the repository-wide suite is not globally clean and is not claimed as passed.

## Adversarial review

Five rounds were performed. Findings fixed before convergence included stale tests, transient-failure caching, semantic-card drift, candidate escape, provider-call saturation, and non-string model IDs. Final round result: `本轮无新增实质问题`.

## Not changed

- No JEV call was added.
- No second router/registry/runtime was added.
- No QCP, Workflow, approval, write-confirmation, Session, idempotency, lock, queue, or SSE state decision was delegated to JEV.
- Existing Bridge regex protocols for Drill-me, note actions, and Skill authoring remain until matching PCM Skills and signed execution-state tests exist.
- `ops/change-manifests/build48-selected-text-gate-20260924-completion.md` was preserved as unrelated work and was not modified or staged.
- No push, deployment, gateway restart, or production configuration change was performed.
