# Story review image handoff fix completion

- task_id: `story-review-image-handoff-fix-20260925`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0`
- head/local_commit: `ed85a752074008a743f360d44be6e205dafea9c0` / none
- remote_sha: not queried or changed; parent preflight recorded `origin/main=873cc27e676915cc8a69adf48921479e512b24f8`
- server_before: not accessed
- server_after: not deployed
- rollback_point: parent archive `candidate-before-upstream-20260925-040602`; this task made no Git commit

## Change

- Reused `review_input()` and `local_path()` so reviewer read-only assets include both cover files and every manifest-bound inline image.
- Required visual-tool inspection of every actual image; hashes and prompts remain evidence, not substitutes for inspection.
- Added the inline-image handoff assertion to the existing remote workflow test. No approval/signature condition changed.

## Validation

- RED: `python3 -m pytest -q tests/test_publication_editorial_remote.py::test_prepare_ingests_manifest_bound_inline_image_bytes` — failed because `read_only_inputs.assets=[]`.
- GREEN: same command — `1 passed, 4 warnings`.
- Parent offline negative: `python3 /Users/dengzhaoyu/.hermes/profiles/story/output/story-publication-test/check-inline-review-handoff.py` — passed; `inline_image_delivered_to_reviewer=true`.
- Remote: `python3 -m pytest -q tests/test_publication_editorial_remote.py` — `36 passed, 4 warnings`.
- First provenance/workflow run without repository `PYTHONPATH` — `69 passed, 3 failed, 4 warnings`; all failures were CLI subprocess imports of `backend`.
- Provenance/workflow: `PYTHONPATH=. python3 -m pytest -q tests/test_publication_review_provenance.py tests/test_publication_editorial_workflow.py` — `72 passed, 4 warnings`.
- Inline/asset checks: `PYTHONPATH=. python3 -m pytest -q` with the four selected daily-publication/provenance nodes — `5 passed, 4 warnings`.
- `python3 -m ruff check scripts/publication_editorial_remote.py tests/test_publication_editorial_remote.py` — passed.
- `git diff --check HEAD` — passed.

## Remaining risks

- No commit, push, deployment, production access, real review, or publication was performed.
- Warnings are existing Pydantic class-config deprecations.
