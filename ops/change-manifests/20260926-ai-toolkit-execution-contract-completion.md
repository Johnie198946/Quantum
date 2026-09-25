# 2026-09-26 AI Toolkit execution contract fix

## Scope

- Task ID: `20260926-ai-toolkit-execution-contract`
- Branch: `main`
- Defect: `ai-toolkit` carries governed tutorial execution evidence, but bundle validation treated every non-`ai-practice`/`quantumn-originals` execution claim as not applicable. This made finalize readback disagree with the already-created stage.
- Fix: include `ai-toolkit` in the tutorial execution series set. Existing requirements for a `success`/`failed` claim to carry execution evidence remain unchanged.
- Out of scope: editorial approval, content/image hashes, five-image requirements, review history, publication data, and unrelated untracked files.

## Validation

- `python3 -m pytest -q tests/test_daily_publication.py tests/test_publication_editorial_workflow.py tests/test_publication_editorial_remote.py tests/test_publication_remote_release.py tests/test_publication_scheduler_watchdog.py`
  - Result: `178 passed, 4 warnings`
- `python3 -m ruff check backend/services/knowledge_publication_store.py tests/test_daily_publication.py`
  - Result: passed
- `git diff --check`
  - Result: passed
- Regression coverage now applies the same missing-evidence and valid-evidence assertions to both `ai-practice` and `ai-toolkit`.

## Delivery contract

- GitHub remote target: `main`
- Server before / rollback SHA: `e8a4567e6d21ccc7b6b15038c2995b87422688b5`
- Server after: the immutable 40-character SHA of this manifest-bearing commit, after GitHub readback confirms it is `refs/heads/main`
- Deployment entry point: `scripts/deploy_exact_sha.sh`
- Required post-deploy verification: deployment marker, image OCI revision, deployed source rule, `/health`, Revision 9 finalize/release, and public/server/iOS publication readback.

## Remaining risks

- Deployment and Revision 9 publication are not established by this manifest; they require live readback.
- Story remains a separate acceptance chain and is not changed by this fix.
