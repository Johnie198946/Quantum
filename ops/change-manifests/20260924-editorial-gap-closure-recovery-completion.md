# Editorial gap-closure recovery

task_id: 20260924-editorial-gap-closure-recovery
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/quantum-2.0-publication-main
head/local_commit: pending
remote_sha: pending
server_before: pending
server_after: pending
health_check: pending
functional_check: pending
rollback_point: pending
manifest: ops/change-manifests/20260924-editorial-gap-closure-recovery-completion.md
remaining_risks: production deployment and live editorial recovery pending

## Scope

- Preserve the normal four-rejection retry limit.
- Permit exactly one fifth attempt only when the body hash is unchanged and the proposed contract explicitly resolves every inherited open research gap using the same IDs and questions.
- Keep the fifth attempt subject to the normal independent review, proof, staging and release gates.
- Do not mutate production editorial rows or bypass review.

## Verification

- `python3 -m ruff check backend/services/knowledge_publication_store.py tests/test_publication_editorial_workflow.py`: passed.
- `git diff --check`: passed.
- `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q tests/test_publication_editorial_workflow.py`: 21 passed.
- `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q tests/test_publication_editorial.py tests/test_daily_publication.py`: 69 passed.
- `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q tests/test_*publication*.py`: 193 passed.
- `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q tests/test_server_deployment_contract.py tests/test_deploy_current_release_cas.py`: 123 passed.
- `bash -n scripts/update.sh scripts/deploy_exact_sha.sh`: passed.
- Initial focused run without `PYTHONPATH=.` had three CLI import failures (`ModuleNotFoundError: backend`); rerun with the repository execution contract passed all 21 tests.