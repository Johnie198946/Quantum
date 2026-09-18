# Gate 0–6 capability-consumer continuation — 2026-09-19

- task_id: `gate0-6-completion-20260918`
- status: `VERIFIED CANDIDATE / PARTIAL PRODUCT COVERAGE`
- branch: `main`
- base / server_before: `65bcf9cc29fe18994cd163d0d01cf318b89e73a7`
- authorization: commit, push and production deployment approved by the user on 2026-09-19.

## Scope and truth boundary

- Audited all 70 IDs from `manifest.yaml#ios_scope` through schema, binding, handler, policy, event, renderer/fallback, automated-test references, iOS consumer and QWS consumer.
- Added versioned iOS/QWS registry routes and fail-closed event/renderer pairing for previously unregistered scoped result events.
- Event and renderer versions must both match exactly; missing versions are rejected instead of being promoted to v1.
- QWS now exposes consumed capability events in the task-chat UI; iOS dispatches the supported typed paths and rejects unsupported native-action versions.
- Corrected stale iOS consumer annotations and regenerated `ops/acceptance/ios-capability-matrix.json`.
- This release remains truthfully `0 implemented / 70 partial`: it closes transport/registry/fallback gaps, not all domain-specific product UIs. Production receipts remain unverified.
- No second runtime, state store, capability handler or dependency was added.

## Final pre-commit verification

- Python capability/deployment/provider scope: `279 passed / 0 failed`.
- iOS simulator selected suites: `166 passed / 0 failed / 0 skipped` (`WorkflowLifecycleDTOTests` 151; total includes `ChatResponseRecoveryRegressionTests`).
- Frontend complete Node test suite: passed.
- Frontend production builds, including showroom gateway: passed.
- `bash -n scripts/deploy_exact_sha.sh scripts/update.sh`: passed.
- `git diff --check`: passed.
- Added-source scan: 0 absolute user paths, private-key blocks or credential assignments.
- `--require-complete` is still expected to fail closed until 70 production receipts exist.

## 2026-09-19 follow-up

- `capability.proposed` is bound to the `confirmation` renderer and QWS posts the proposal token with the canonical bound `session_id` to `/api/v1/capabilities/confirm`.
- Follow-up gates: Python targeted scope `279 passed`; frontend complete test/build passed; focused QCP/deployment `20 passed`; iOS `WorkflowLifecycleDTOTests` `153 passed / 0 failed`.
- Production receipts remain pending; the matrix therefore correctly remains `partial: 70` until the exact SHA is deployed and verified.

## Delivery contract

- Commit and remote SHA: the commit containing this manifest.
- Rollback point: `65bcf9cc29fe18994cd163d0d01cf318b89e73a7`.
- Deployment must require a pinned known-hosts file and compare the active server SHA under the deployment lock before any mutation.
- Post-deploy acceptance must bind server `.deployed-sha`, health, running files and functional probes to the pushed commit.
- TestFlight is out of scope for this deployment; no claim of `70 implemented` is made.
