# Exact-SHA deploy portable mktemp repair — 2026-09-19

- task_id: `deploy-exact-sha-portable-mktemp-20260919`
- status: `TESTED`
- branch: `main`
- base: `30e5f4a94a40ad36effa592e7ccce0786a40fbb0`
- server_before: `7b3863a954e689f87ed2a8f1b7d9863a676dfb7d`

## Incident and root cause

The authorized exact-SHA deployment stopped before any server mutation because macOS `mktemp` requires the six `X` characters to terminate the template. `scripts/deploy_exact_sha.sh` used `ai-lab-source.XXXXXX.tar.gz`, so local source-archive allocation failed with `File exists`. The same non-portable template also existed in the remote upload allocation path.

## Change

- Use suffix-free, trailing-`XXXXXX` temporary paths for both local and remote source archives.
- Keep the immutable installed archive name `/opt/ai-lab-shared/offline-source/ai-lab-platform-$SHA.tar.gz`; only transient paths change.
- Keep strict path-shape validation and cleanup aligned with the new temporary path.
- Add a regression contract that rejects any `XXXXXX.tar.gz` template.

## Verification

- `bash -n scripts/deploy_exact_sha.sh scripts/update.sh`: passed.
- Native macOS `mktemp "${TMPDIR:-/tmp}/ai-lab-source.XXXXXX"`: passed and cleaned.
- `PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_server_deployment_contract.py tests/test_deploy_current_release_cas.py`: `127 passed`, `0 failed`, `4 warnings`.
- `git diff --check`: passed.
- The failed pre-fix deployment did not reach SSH upload or server mutation; production remained on `7b3863a954e689f87ed2a8f1b7d9863a676dfb7d`.

## Delivery contract

- Commit / remote SHA: the commit containing this manifest.
- Exact-SHA deployment may resume only after GitHub `main` is read back at that commit.
- Expected-current CAS remains `7b3863a954e689f87ed2a8f1b7d9863a676dfb7d` until deployment starts.
- Rollback point remains `/opt/releases/ai-lab-platform-7b3863a954e6.wcJHj6`.
