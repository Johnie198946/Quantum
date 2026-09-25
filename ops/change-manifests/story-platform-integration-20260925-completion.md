# Story platform integration completion

- task_id: `story-platform-integration-20260925`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0`
- baseline/local HEAD: `ed85a752074008a743f360d44be6e205dafea9c0`
- source provenance: `source/main` at `5ab35ef8f959aabd5c5c6a324624860662f6e64d`
- other remote reference: `origin/main` at `92d7d273fc94052a696183ebc36dedc8cd7093d4`
- delivery: no commit, push, deployment, production write, profile edit, or production credential access

## Inventory and semantic decisions

- Preflight recorded canonical path, `main`, HEAD, remotes, and worktrees. Because `main` diverges from `source/main`, no pull, merge, or rebase was performed.
- Preserved pre-existing user/governance changes in `AGENTS.md` and `ops/change-manifests/quantum-2.0-hermes-gate-i0-20260909-completion.md`; neither was edited for this task.
- The production baseline did not contain the PCM/QCP final-tree implementation even though related history existed. The minimum dependency closure was selectively migrated from `source/main`: governed contracts/catalog, gateway and handlers, native Hermes capability tools, API/lifecycle integration, workflow/session/artifact/client-action dependencies, QWS/iOS consumers, generators, acceptance matrices, and their tests.
- The three known merge conflicts were resolved semantically: current build48 reader/resume/chat behavior was extended rather than replaced; `hermes_bridge.py` retained the deployed flow and gained QCP/native-tool propagation; the removed ordinary knowledge-answer gate stayed removed and is protected by regression tests. No second runtime, duplicate manifest, publication queue, or knowledge queue was added.
- Current online behavior was retained while adding owner-scoped notifications, workflow CAS/cancel semantics, task/project/schedule operations, tenant Skill facade, Hermes owner sessions, generated artifacts, and publication identity/inline-image support through existing catalog -> gateway -> handler and publication-store paths.
- The profile-specific `Unknown toolsets agency_agents,ai_lab` attempt was not treated as proven to share this root cause. Product-native `app_capabilities` assembly is tested; no profile configuration was changed and no production research receipt is claimed.

## Archived Story work restored

- Full archive: `/Users/dengzhaoyu/.hermes/profiles/story/output/story-publication-test/pre-platform-integration/publication-work.patch`
  - SHA-256: `d8e49731a6f7b7e4f6c98d97dae5b2c67309ae92755369c45b70539acac2e424`
- Reviewed identity repair: `/Users/dengzhaoyu/.hermes/profiles/story/output/story-publication-test/repair-final.diff`
  - SHA-256: `d8b56a487dc431abff74605f815baee846fcedf05cc76a360c8ed63f910462bc`
- Identity semantics were restored onto the integrated baseline: story author/supervision reviewer attribution, signed asset evidence, proof retry/rollback, and immutable-edition cover replacement.
- Inline-image support was migrated onto the current APIs and iOS reader without overwriting build48: validated PNG/JPEG assets, digest/publication binding, published/non-withdrawn checks, authenticated same-origin image fetching, ordered text/image blocks, captions/alt text, scaled rendering, and failure fallback.

## Validation

- Publication suite: `239 passed, 4 warnings` using `tests/test_publication*.py tests/test_daily_publication.py tests/test_pcm_jev_routing_contract.py`.
- PCM/QCP/native tools and capability closure: `130 passed, 6 warnings` using the capability, gateway, structured-consumption, iOS-matrix, and task-execution suites.
- Affected Hermes/session/book/no-gate regression: `62 passed, 6 warnings`.
- Earlier integrated PCM plus deployed online regression: `199 passed, 8 warnings`; book/open-knowledge/QCP/worker regression: `60 passed, 6 warnings`.
- `python3 scripts/generate_product_capability_manual.py --check`: passed after deterministic regeneration.
- `python3 scripts/generate_ios_capability_matrix.py --check`: passed; matrix reports `70 implemented`, `0 partial`, `0 unverified`, `0 absent`.
- `python3 -m ruff check backend scripts tests`: passed.
- `git diff --check`: passed.
- Relevant Python bytecode compilation: passed.
- Frontend locked dependencies restored with `npm ci` (no manifest/lock change), then `npm run build`: passed, including Vite production bundle and showroom gateway.
- iOS application build with signing disabled: `BUILD SUCCEEDED`.
- iOS `build-for-testing` with signing disabled: `TEST BUILD SUCCEEDED`.
- Isolated iPhone 17 Pro tests, without login or publication actions: authenticated bounded publication-image path test passed; ordered inline-image block decoding test passed.
- Warnings are existing FastAPI `on_event`, Pydantic class-config, and `UITextItemInteraction` deprecations; no validation failure remains.

## Failed/intermediate checks retained for audit

- The first frontend build failed with `vite: command not found` because `frontend/node_modules` was absent. `npm ci` restored the versions already pinned by the lockfile; the subsequent production build passed.
- Generator checks initially detected stale restored outputs. Both governed outputs were regenerated from the migrated catalog and then passed `--check`.
- One focused Python invocation incorrectly set `HERMES_AGENT_ROOT=/Users/dengzhaoyu/.hermes`, causing five import/setup failures. The verified runtime root is `/Users/dengzhaoyu/.hermes/hermes-agent`; the identical suite then passed `62/62`.
- An earlier `xcodebuild` process handle expired before its result could be collected. The same `build-for-testing` command was rerun and completed successfully.

## Delivery and rollback record

- local commit: none; HEAD remains `ed85a752074008a743f360d44be6e205dafea9c0`
- remote SHA: not updated; no push (`source/main=5ab35ef8f959aabd5c5c6a324624860662f6e64d`, `origin/main=92d7d273fc94052a696183ebc36dedc8cd7093d4`)
- server_before: task evidence identifies deployed `ed85a752074008a743f360d44be6e205dafea9c0`; no new production access was made
- server_after: not deployed
- health_check: not run because deployment was explicitly out of scope
- functional_check: local suites/builds above passed; no production write or publication performed
- rollback_point: clean code baseline `ed85a752074008a743f360d44be6e205dafea9c0` plus the two SHA-256-verified Story archives above

## Remaining risks / unverified

- No production end-to-end PCM invocation, publication, server health check, or deployment verification was authorized or performed.
- No real public-source article ingestion, supervision approval, or user final confirmation was performed; therefore the complete Story publication chain is not claimed as published.
- The `agency_agents,ai_lab` profile-specific unknown-toolset condition remains unverified outside the product-native path.
- Deprecation warnings listed above remain as pre-existing maintenance work.
