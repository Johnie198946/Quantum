# Gate 0–6 Native Client Actions — 2026-09-18

## Scope

- `file.pick`
- `photo.capture`
- `photo.import`
- `voice.record`
- `share.present`
- Base SHA: `9abd8ffa0a9d1ee03ad31510cd6e3b39c2ca4f1f`
- Candidate commit: pending

## Architecture

- Gateway proposal/confirm/idempotency remains the authority boundary.
- `ClientActionInvocation` persists owner, normalized input hash, pending state and terminal receipt.
- QCP execution means the action was issued; it does not claim the device action succeeded.
- The authenticated receipt endpoint completes the action as `SUCCEEDED`, `CANCELLED` or `FAILED`.
- iOS dispatches renderer `client_action` to one `NativeClientActionHost`; ChatView has no capability switch.
- The registry supports native document picker, photo library, camera, voice recorder and share sheet.

## Focused verification

- Python focused suites: `38 passed`.
- ClientAction domain replay/owner/terminal receipt tests: `2 passed`.
- iOS `WorkflowLifecycleDTOTests`: `149 passed`, 0 failed.
- iOS simulator target build: `BUILD SUCCEEDED`.
- Result bundle: `/tmp/QuantumnClientActionTests.xcresult`.
- Ruff, PCM, iOS matrix, governed engineering, diff: passed.
- Gateway bypass: 0.
- Matrix: `62 partial / 8 absent / 0 implemented / 0 unverified`.

## Evidence boundary

This is focused candidate verification. It does not claim five per-action UI flows were manually exercised, does not provide production terminal receipts, and does not replace final-SHA backend/iOS full regression, clean-room, deployment or TestFlight evidence.
