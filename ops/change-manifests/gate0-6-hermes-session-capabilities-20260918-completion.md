# Gate 0–6 Hermes Session Capabilities — 2026-09-18

## Scope

- `hermes.session.list`
- `hermes.session.open`
- `hermes.session.resume`
- `hermes.session.delete`
- Base SHA: `948cfaa6f15e270f96d0502ee9c1660cdd5c7fd7`
- Candidate commit: pending

## Semantics

- Reuses Hermes SessionDB in the tenant/user sandbox; no second runtime or session store.
- Requires an existing authenticated `WorkflowClientSessionBinding` before bridge lookup.
- Derives the same tenant/user-namespaced client session key used by Chat.
- Bridge accepts only internal-token calls with explicit tenant/user headers and rejects namespace mismatches.
- List/open return metadata only; message bodies are excluded from QCP receipts.
- Resume/delete require Gateway confirmation and idempotency; delete removes the SessionDB record and atomically removes the cross-process owner mapping.

## Focused verification

- Hermes session / Gateway / PCM / iOS matrix: `43 passed`
- Ruff: passed
- PCM generation/check: passed
- iOS matrix generation/check: passed
- governed engineering rules: synchronized
- Gateway bypass: `0`
- `git diff --check`: passed
- Matrix candidate: `57 partial / 13 absent / 0 implemented / 0 unverified`

## Evidence boundary

This is focused local evidence only. It does not prove production bridge reachability, production receipts, full backend/iOS regression, simulator E2E, deployment, or TestFlight readiness.
