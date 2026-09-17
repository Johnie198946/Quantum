# Capability Gateway and Bridge gate completion

- task_id: `knowledge-gateway-bridge-governance-20260917`
- status: `TESTED_PENDING_DEPLOY`
- branch: `fix/knowledge-gateway-governance-20260917`
- base_sha: `27f6a4aad6c824e2ecf46329acbac069d522474c`
- release_commit: the commit containing this manifest
- server_before: pending deployment receipt
- server_after: pending deployment receipt
- rollback: deploy `base_sha`; no schema or data migration is introduced

## Delivered

- Defined Capability Gateway as the PCM/QCP modular entry point and Knowledge Gateway as a constrained domain gateway, not a second Runtime or business-data truth source.
- Reused the request-scoped authorized path set during lexical, ranking and WikiLink work; calls without trusted request context retain live file checks.
- Preserved the three independent authorization times: request admission, Gateway response revalidation, and Bridge send-time `path + version` verification.
- Added Bridge typed consumption decisions with `knowledge_gate_receipt.v2`:
  - `requirement=required|optional`
  - `attempted`
  - `retrieval_status` and `failure_kind`
  - `consumption=cited|not_exposed|unknown`
  - `decision=allowed_internal|allowed_public_only|blocked_*`
- Ordinary questions use optional pre-read. A public answer is allowed after `no_match`, insufficiency, timeout or system error only when no governed body reached the model and the final answer retains a URL returned by a successful authorized web tool.
- Authorization denial, explicit internal-knowledge requirements, unknown consumption, citation violations, version changes and send-time revalidation failures remain fail closed.
- Distinguished Gateway timeout from authorization denial; the five-second bound was not increased.
- Added the module boundary, status ownership, compatibility, performance, security and acceptance rules to the Gateway product specification, generated PCM and Wiki/Hermes architecture.

## Changed files

- `backend/api/knowledge.py`
- `scripts/hermes_bridge.py`
- `tests/test_knowledge_read_scaling.py`
- `tests/test_knowledge_consumption_gate_server.py`
- `tests/test_chat_triage.py`
- `tests/test_chat_run_worker.py`
- `docs/product-specs/capability-gateway.md`
- `scripts/generate_product_capability_manual.py`
- `docs/product-capability-manual.md`
- `docs/product-capability-coverage.json`
- `docs/wiki-hermes-chat-architecture.md`
- `ops/change-manifests/gateway-module-spec-20260917-completion.md`

## Verification

- PCM generation and `--check`: passed.
- Python compile and `git diff --check`: passed.
- Gateway/Bridge/chat/PCM focused regression after the architecture counter-review fixes: `384 passed, 48 warnings, 16 subtests passed`.
- Deployment contract regression: `123 passed, 4 warnings`.
- Full repository run in the original worktree: `2599 passed, 30 skipped, 4 failed`; the same four `test_research_deposition_plugin.py` revision failures reproduce on untouched `origin/main` because `deposit_research()` rejects the pre-existing `revision_link` argument. They are not caused by this change and are not represented as passing.
- Production-shaped local lexical benchmark before Bridge changes: 39 authorized documents; `和JR如何衔接？` = 763.97/476.49/597.86 ms and `怎么去樱岛` = 448.57/437.52/426.96 ms over three runs. This is not production end-to-end latency.

## Deployment acceptance still required

- Push and read back the exact release SHA from GitHub main.
- Deploy that exact SHA; record immutable `server_before` and `server_after`.
- Read back API container, Hermes Bridge and chat worker revisions/PIDs and health.
- Exercise Build 40 through the production Chat API with ordinary public travel questions and inspect the durable run receipt.
- Verify `requirement=optional`, no internal context exposure, successful public URLs, `decision=allowed_public_only`, no gate-error replacement, and Gateway latency below the unchanged five-second limit.
- Exercise an explicit internal-knowledge question and a denied/revoked case to prove fail-closed behavior survived deployment.
