# Gate 0–6 Full Backend Regression Fixes — 2026-09-18

## Base

- Base SHA: `e0b3c29bb910b4d65e6eaf300118b8e51fd082d7`
- Candidate SHA: pending
- Status: local candidate, not pushed/deployed

## Fixes

- Removed service → API reverse dependency from governed `task.execute`.
- Preserved HTTP-entry and shared-helper kill switches.
- Added ReportLab to the reproducible Linux dependency lock without deleting retained packages.
- Updated stale `task.execute` and Notification absent assertions to their governed contracts.
- Added provider-signature-compatible research revision handoff while retaining full lineage on the current governance pipeline.

## Exact test environment

- Python 3.11.15 isolated venv.
- API dependencies from `requirements.txt`.
- bridge worker dependencies from `requirements-bridge-worker.in`.
- HTML extractor dependencies from `agency/hermes-plugins/ai-lab-capabilities/requirements-html.txt`.
- Local Hermes source installed `--no-deps` from `/Users/dengzhaoyu/.hermes/hermes-agent`.
- `RESEARCH_PIPELINE_MODULE=/Users/dengzhaoyu/Projects/ai-lab-vault-governance/tools/article_research_pipeline.py`.

## Candidate verification

- Backend full: `2717 passed`, `18 skipped`, `0 failed`, `16 subtests passed`.
- Ruff, PCM, iOS matrix, governed engineering rules, diff: passed.
- Gateway bypass: `0`.
- Matrix: `70 partial / 0 absent / 0 implemented / 0 unverified`.

This candidate result is not final SHA evidence until repeated after commit.
