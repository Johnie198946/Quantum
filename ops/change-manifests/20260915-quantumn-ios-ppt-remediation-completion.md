# Quantumn iOS / PPT remediation completion

- task_id: `20260915-quantumn-ios-ppt-remediation`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-ios-document-ppt-final-20260912`
- head/local_commit: pending first release commit
- remote_sha: `fec23ad9205f1ba4cfa9e96507e1cc01151e0c99` before first release
- server_before: `/opt/releases/ai-lab-platform-fec23ad9205f.hYCwvD`; `.deployed-sha=fec23ad9205f1ba4cfa9e96507e1cc01151e0c99`
- server_after: pending
- rollback_point: `/opt/releases/ai-lab-platform-fec23ad9205f.hYCwvD`

## First release scope

- iOS keyboard safe-area regression coverage.
- Workflow creation/resume routes atomically to the task detail and preserves failed pending navigation for retry.
- Rejects the observed `agent_ready -> building_agent` stale status regression.
- Reuses the QCP artifact/renderer path and makes the complete artifact row tappable; no fake field-save contract.
- Agent descriptions expose function, fit and boundary within 100 Chinese characters and only show collapse controls when needed.
- PPT/document generative nodes use an explicit 32,000-character limit while chat remains 12,000 and private-source intake remains 96,000; no silent truncation.
- Session tests use isolated persistent mapping files instead of process defaults.
- Deployment creates `vault/workflows` before ACL repair and makes a real workflow-worker write probe part of the release gate.

## Verified before first release

- `git diff --check`: passed.
- Ruff for changed Python files: passed.
- Bridge/document/workflow/session regression: `178 passed`.
- Deployment/hardening contracts: `139 passed`.
- iOS `build-for-testing`: exit 0.
- `WorkflowLifecycleDTOTests`: exit 0.
- `ChatKeyboardFixtureUITests`: `1 passed`, XCResult `/tmp/quantumn-first-release-keyboard.xcresult`.

## Remaining after first release

- Fresh clean-room Istanbul workflow through full deck preview and PPTX download/hash verification.
- Cross-session/global activity restoration isolation.
- Image/map/icon/timeline layout quality and visual scoring.
- First-class Word, research-report and academic-paper PCM contracts.
- Final push, exact-SHA deployment and all receipts.
