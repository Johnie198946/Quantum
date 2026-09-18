# Gate 0–6 Remaining Capabilities — 2026-09-18

## Scope

- `file.upload`
- `file.download`
- `voice.transcribe`
- `task.execute`
- `office.spreadsheet.create`
- `office.pdf.create`
- `data.analyze`
- `media.create`
- Base SHA: `887686ea3e6598a970847a3c57f7e528bfba4581`
- Candidate commit: pending

## Implementation

- File upload/download/transcription use the shared native ClientAction registry. Upload reuses authenticated document ingestion; download resolves owner-bound source metadata before fetching and validates SHA-256; transcription sends recorded audio to a bounded authenticated API and fails closed when the model is unavailable.
- Generated XLSX/PDF/JSON-analysis/PNG media artifacts are immutable, owner-namespaced, content-addressed by receipt SHA-256, and reverified before download.
- `task.execute` reuses QWS task-conversation auto-execution. It checks owner, task ID, confirmed intent hash, and task lifecycle before queuing. The delegated JWT exists only in memory, expires after 20 minutes, and is not included in the durable Gateway payload or receipt. Dependency waiting is bounded to 15 minutes.

## Candidate evidence

- New focused backend suites plus Gateway/PCM/matrix: `48 passed`.
- Generated artifact behavior: XLSX/PDF/JSON/PNG bytes, SHA readback, owner isolation, corruption detection.
- Task execution: delegated claims, bounded expiry, fail-closed secret and CAS validation.
- Current iOS `WorkflowLifecycleDTOTests`: `149 passed`.
- Current iOS result: `/tmp/QuantumnRemainingCapabilities.xcresult`.
- PCM generation/check, iOS matrix generation/check, Ruff, governance, Gateway bypass, and diff checks passed.
- Matrix: `70 total / 70 partial / 0 absent / 0 implemented / 0 unverified`.

## Evidence boundary

This closes the code-level `absent` bucket. It does not close production receipts, 70-capability simulator E2E, production clean-room, GitHub push, deployment, or TestFlight.