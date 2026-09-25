# JEV / Hermes Bridge latency and precision refactor — local completion receipt

- date: `2026-09-25`
- branch: `main`
- base: `873cc27`
- routing_commit: `32f80fd8aab21fa625a4a0881b93bc485c929709`
- structural_code_commit: `6bd0ced`
- status: `COMMITTED_LOCAL_NOT_PUSHED`
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

## Structural decomposition

The follow-up decomposition completed the previously outstanding giant-file work:

- `scripts/hermes_bridge.py`: `8,444` → `287` lines;
- the root now contains import bootstrap, explicit compatibility exports, FastAPI construction, route registration, and the executable entry point;
- implementation moved into normal static Python modules under `scripts/hermes_bridge_runtime/`:
  - `contracts.py`: request contracts, admission and shared configuration/state;
  - `persistence.py`: authorization/capability checks, mappings and Hermes CLI boundary;
  - `session_runtime.py`: sessions, durable streams and status/readback;
  - `agent_config.py`: cached configuration, triage and agent cache;
  - `agent_execution.py`: Hermes `AIAgent` construction and execution;
  - `knowledge.py`: knowledge, notes, tenant Skills and workspace tools;
  - `memory.py`: native memory and gate approvals;
  - `workflow_artifacts.py`: workflow prompts, usage and artifacts;
  - `workflow_runtime.py`: planning, evaluation and workflow execution;
  - `receipts.py`: queues, watchdog and delegation/tool receipts;
  - `endpoints.py`: chat, clarification and health handlers;
- largest replacement module: `1,391` lines; every module is below the `1,500`-line architecture gate;
- no dynamic source loading, wildcard imports, generated runtime code, `sys.modules` mutation, second Router, Registry or Runtime was introduced;
- all `356` previous top-level Bridge symbols remain importable/callable through explicit facade exports; private attribute rebinding now belongs to the owning runtime module rather than the composition root;
- all in-repository production rebinding sites were updated to the owning module, and affected tests patch the actual owner instead of relying on detached facade copies;
- all 26 HTTP routes plus the startup handler retain the previous path/method/endpoint mapping.

## Verification

### Targeted regression

```text
175 passed, 8 warnings in 13.88s
```

Covered JEV selector/resident/cache behavior, PCM routing contract, Hermes Bridge, Wiki/knowledge adapters, streaming timing, Agency abstention/integration, and Agent OS acceptance.

### Structural regression

```text
590 passed, 1 skipped, 4 warnings in 40.35s
53 passed, 4 warnings in 13.94s
137 passed, 4 warnings in 25.08s
```

The first run covers every directly affected Bridge/JEV/architecture test file; the second covers durable chat worker and disclosure/authorization tests; the third independently rechecks architecture, deployment contract, isolation and durable worker admission. The transient heartbeat test was given an explicit 30-second test-only freshness window to avoid false failures under a loaded suite; production freshness remains unchanged.

Additional executable checks:

```text
Bridge import: 30 FastAPI routes including four documentation routes
Old/new business route mapping: identical (26 HTTP routes + startup handler)
Previous Bridge symbols: 356/356 preserved
Fresh-process imports: 11/11 runtime modules passed
ruff check: passed
py_compile: passed
git diff --check: passed
```

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

The failures are outside the changed JEV/Bridge surfaces and are dominated by existing environment/state problems (Starlette/httpx `TestClient` incompatibility, authentication/tenant fixture state, workflow rows with empty tenant keys, and unrelated extraction/deposition expectations). Two initially reported chat-stream failures passed immediately when rerun in isolation. During the structural follow-up, another full-suite attempt reached `1,681 passed / 1 skipped` before the configured 20-failure cutoff; the affected-surface suites above are green, but the repository-wide suite is not globally clean and is not claimed as passed.

## Adversarial review

Five routing rounds were performed. Findings fixed before convergence included stale tests, transient-failure caching, semantic-card drift, candidate escape, provider-call saturation, and non-string model IDs. The structural decomposition then received three additional rounds: round 1 identified that facade exports do not preserve private attribute-rebinding semantics; the claim was narrowed and all production rebindings were verified against owning modules. Rounds 2 and 3 found no new material issue.

## Not changed

- No JEV call was added.
- No second router/registry/runtime was added.
- No QCP, Workflow, approval, write-confirmation, Session, idempotency, lock, queue, or SSE state decision was delegated to JEV.
- Existing Bridge regex protocols for Drill-me, note actions, and Skill authoring remain until matching PCM Skills and signed execution-state tests exist.
- The new runtime modules use explicit late imports to preserve the monolith's shared state during this behavior-preserving extraction; fresh-process import tests pass, but removing all cyclic dependencies is a later maintainability improvement rather than a claimed latency or correctness change.
- `ops/change-manifests/build48-selected-text-gate-20260924-completion.md` was preserved as unrelated work and was not modified or staged.
- No push, deployment, gateway restart, or production configuration change was performed.
