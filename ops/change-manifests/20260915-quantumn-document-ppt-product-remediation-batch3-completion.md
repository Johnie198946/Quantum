# Batch 3 owner/session/generation isolation status

- task_id: `20260915-quantumn-document-ppt-product-remediation-batch3`
- status: `LOCAL_ACCEPTANCE_PASSED_PRODUCTION_PENDING`
- production deployment: not authorized

## Local implementation and tests

- Authoritative `owner + tenant + registered client session` bindings are established by authenticated chat and enforced on workflow creation.
- Active activity/execution APIs filter on owner and client session server-side.
- Legacy workflows fail closed to creator/owner and do not enter a current chat without trusted session provenance.
- iOS immutable UI scope includes owner, client session and generation; bootstrap, SSE, polling, direct creation, deep links, artifacts and review writes check scope before mutating observable state.
- Backend test covers two owners × two sessions with four active tasks and verifies each owner/session sees only its own task.
- Simulator unit tests cover generation rollover, late-response rejection, cross-session tracking rejection, deep-link rejection and artifact-preview rejection.
- Full current `AIPlatformAppTests`: `208 passed, 0 failed, 0 skipped`.

## Remaining production gate

The required deployed matrix has not run: two production accounts × two sessions, four concurrent tasks, rapid switching, logout/login, cold start, delayed responses and legacy-workflow mixing. No production credentials or deployment authorization were provided, so these cases remain `unverified` and Batch 3 is not globally accepted.
