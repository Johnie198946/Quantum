# Gate 0–6 Notification Capabilities — 2026-09-18

## Scope

- `notification.list`
- `notification.mark_read`
- `notification.preferences.update`
- Base SHA: `6876b110248ddbd4d3423cba821f54e97b8e6a75`

## Domain changes

- Notifications are now bound to `tenant_key + user_id`.
- Legacy rows without an owner are deliberately invisible; migration does not guess ownership.
- Scheduled Agent notifications target `Agent.created_by`.
- Mark-read uses a locked unread-state CAS.
- User preferences are persisted per principal and use revision CAS.
- Mutations remain behind QCP Proposal → Confirm → Execute and durable invocation receipts.

## Candidate verification

- Notification and legacy notification API tests: `8 passed`.
- Ruff: passed.
- PCM generation/check: passed.
- iOS matrix generation/check: passed.
- Gateway bypass: `0 violations`.
- Governed engineering rules: synchronized.
- `git diff --check`: passed.

## Matrix movement

- Before: `partial=50 / absent=20`.
- Candidate: `partial=53 / absent=17`.
- No capability is marked production `implemented`; production receipts and simulator evidence remain outstanding.

## Evidence boundary

This proves focused local code and contract behavior only. It is not production clean-room, deployment, simulator E2E, or TestFlight evidence. Post-commit verification must be bound to the exact candidate SHA.
