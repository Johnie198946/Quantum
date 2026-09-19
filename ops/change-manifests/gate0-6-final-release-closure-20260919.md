---
title: Gate 0–6 Final Release Closure
date: 2026-09-19
status: no-go-testflight-only
tags:
  - gate-0-6
  - release
  - ios
  - production
---

# Gate 0–6 Final Release Closure

> [!warning] Release decision
> **NO-GO — TestFlight only.** Code, production capability, artifact, simulator, matrix, and rollback gates are closed. App Store Connect is not authenticated, so no unused build number has been assigned and no Archive has been uploaded or proven installable.

## Source and production truth

- GitHub `main`: `cf3715917880749796ff0f6e101f42234aac6b0d`
- Commit: `fix(ios): renew stale proposals and close capability evidence`
- Production runtime: `6b461bb49f8ed05e7ba34fc99f44503ebca1cc57`
- Production marker, active release symlink, Bridge CWD, API image revision: matched `6b461bb49f8ed05e7ba34fc99f44503ebca1cc57`
- Compose: `8/8` services running
- Public `/health`: HTTP `200`, `{"status":"ok","version":"0.8.0"}`
- Attempted exact deployment of `cf3715917880749796ff0f6e101f42234aac6b0d` failed closed before switch because preloaded backend images were labeled `6b461bb…`; production remained on `6b461bb…`.
- This boundary is intentional: `cf371591…` changes iOS source, tests, and acceptance evidence only; it does not change deployed backend/frontend runtime code. The TestFlight binary must be archived from `cf371591…`.

## Verified gates

| Gate | Result |
|---|---:|
| iOS unit `.xcresult` | `220 passed / 0 failed / 0 skipped` |
| iOS fixture UI `.xcresult` | `6 passed / 0 failed / 0 skipped` |
| Production Word UI E2E | `1 passed / 0 failed / 0 skipped` |
| Production research report UI E2E | `1 passed / 0 failed / 0 skipped` |
| Production academic paper UI E2E | `1 passed / 0 failed / 0 skipped` |
| Authenticated capability describe | `70/70` |
| Generated iOS capability matrix | `implemented 70 / partial 0 / absent 0 / unverified 0` |
| Production artifact workflows | `3/3` completed with ID, version, SHA-256, repeatable download |
| Rollback → restore | Passed; `30e5f4a…` → `6b461bb…`, both with `8/8`, matching marker/symlink/Bridge/API revision |

Commands:

```bash
python3 scripts/generate_ios_capability_matrix.py --check --require-complete
xcrun xcresulttool get test-results summary --path /tmp/Quantumn-Final-Unit.xcresult --format json
xcrun xcresulttool get test-results summary --path /tmp/Quantumn-Final-FixtureUI.xcresult --format json
```

## Production artifact receipts

- `document.word.create_from_text`: `ops/acceptance/receipts/20260919-production-word-artifact.json`
- `report.research.create_from_text`: `ops/acceptance/receipts/20260919-production-research-report-artifact.json`
- `paper.academic.create_from_text`: `ops/acceptance/receipts/20260919-production-academic-paper-artifact.json`
- 70 authenticated describes: `ops/acceptance/receipts/20260919-production-capability-describe.json`
- Consolidated acceptance: `ops/acceptance/receipts/20260919-gate0-6-final-acceptance.json`

## Findings repaired during acceptance

1. A Word confirmation correctly failed closed with `Policy changed; create a new proposal`.
2. The visible **Retry** action previously retried the invalid opaque token. `TenantSessionCoordinator` now creates a fresh proposal for stale-authority errors while preserving idempotent confirmation retry for ordinary transient failures.
3. The independent Word production flow passed after a fresh proposal.
4. The first rollback drill restored direct API health but exposed public HTTP `502`: frontend nginx retained the replaced API container address.
5. Frontend was recreated, only the accidentally created empty `ai-lab-prod` project resources were removed, and the drill was rerun with frontend recreation plus local HTTPS health inside the gate. Final public health passed.

No running production container, production image, or production volume was pruned.

## Remaining external gate

App Store Connect currently presents a sign-in page in the local Chromium session. Completion requires:

1. authenticate App Store Connect;
2. query the actual next unused build number;
3. set that number without guessing or reusing an occupied number;
4. Archive from `cf3715917880749796ff0f6e101f42234aac6b0d`;
5. upload;
6. read back processing completion;
7. verify tester-group visibility;
8. verify installability.

Until all eight checks pass, the release remains **NO-GO**.
