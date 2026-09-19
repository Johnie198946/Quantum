# Hermes provider-failure receipt fix — 2026-09-19

- task_id: `quantumn-provider-failure-receipt-fix-20260918`
- status: `VERIFIED CANDIDATE`
- branch: `main`
- base / server_before: `65bcf9cc29fe18994cd163d0d01cf318b89e73a7`
- authorization: commit, push and production deployment approved by the user on 2026-09-19.

## Scope and diagnosis

- Prevent exit-zero `API call failed after … retries: Connection error.` responses from becoming assistant answers, successful cache entries, workflow artifacts or knowledge-consumption receipts.
- Reuse `_HERMES_PROVIDER_FAILURE_RE` and `HermesInvocationError` in both chat and workflow in-process completion paths.
- The observed `no_internal_knowledge_consumed` receipt means no controlled knowledge was exposed; it is not an authorization denial.
- Green base knowledge remains readable by every authenticated formal tenant without subscription or plan gating. Yellow/red knowledge retains entitlement and tenant isolation.
- This patch classifies the provider failure truthfully; it does not claim to repair the underlying provider/network incident.

## Final pre-commit verification

- Original isolated focused regression: `43 passed / 0 failed / 0 skipped`.
- Integrated Python capability/deployment/provider scope: `250 passed / 0 failed`.
- Added a workflow regression for the exact observed provider-failure string.
- Python compilation, shell syntax and `git diff --check`: passed.
- Added-source scan: 0 absolute user paths, private-key blocks or credential assignments.

## Delivery contract

- Commit and remote SHA: the commit containing this manifest.
- Rollback point: `65bcf9cc29fe18994cd163d0d01cf318b89e73a7`.
- Post-deploy verification must check typed failure behavior without emitting a false answer or knowledge receipt and must separately report provider connectivity health.
