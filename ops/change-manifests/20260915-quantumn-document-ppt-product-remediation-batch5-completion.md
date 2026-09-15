# Batch 5 document-class PCM completion

- task_id: `20260915-quantumn-document-ppt-product-remediation-batch5`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-ios-document-ppt-final-20260912`
- head/local_commit: `35eb697bdad218aeb5371bcd8f63c0671393c5fb` (working tree only; no task commit requested)
- remote_sha: not checked for delivery; push was not authorized
- server_before: not applicable
- server_after: not applicable
- health_check: not run; no deployment authorized
- functional_check: `39 passed` for PCM catalog, artifact renderer/reader and three document E2Es
- rollback_point: repository HEAD before working-tree edits (`35eb697bdad218aeb5371bcd8f63c0671393c5fb`)
- manifest: `ops/change-manifests/20260915-quantumn-document-ppt-product-remediation-batch5-completion.md`

## Delivered

1. Deterministic DOCX renderer page breaks using the governed form-feed token.
2. Word E2E: three pages, exactly two content edits, append-only artifact version 2, authenticated re-download and SHA-256 verification.
3. Research report E2E: three independent HTTPS institutional sources with captured excerpts and hashes, exhaustive `[S1]`–`[S3]` traceability, revision loop and re-download hash.
4. Academic paper E2E: abstract/body/required sections/references, exhaustive in-text/reference correspondence against three verified accessible publications, no citations outside the allowlisted fixture.
5. Generated iOS chain matrix: user function → capability → event → renderer → handler → consumer → policy → automated test → production receipt.

## Verification

```text
PCM_E2E_ARTIFACT_DIR=$PWD/artifacts/acceptance/document-e2e PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/e2e/test_word_workflow.py \
  tests/e2e/test_research_report_workflow.py \
  tests/e2e/test_academic_paper_workflow.py
3 passed

PYTHONPATH=. python3 -m pytest -q \
  tests/test_workflow_artifact_reading.py \
  tests/test_product_capabilities.py \
  tests/e2e/test_word_workflow.py \
  tests/e2e/test_research_report_workflow.py \
  tests/e2e/test_academic_paper_workflow.py
39 passed, 8 warnings

PYTHONPATH=. python3 scripts/generate_product_capability_manual.py --check
exit 0
```

Warnings are existing FastAPI/Pydantic deprecations.

Durable local artifacts and per-version receipts are stored at
`artifacts/acceptance/document-e2e/`. The final hashes are:

- Word v2: `1be6aab71b98af12c476c2731b5124f796bef95d137032c7e7cf6ec4a4fe63a5`
- Research report v2: `ecb258ceb6b6b3a1933525a66071d30d0f3c4511df7bfcbced49997a25e6655b`
- Academic paper v1: `f151dc48b3e58a37b0a5dd2161e2bbf44a73c76f357a6936d104bbd1cfff70f6`

## Remaining risks

- Production clean-room workflow receipts remain `unverified`; all three iOS feature rows are therefore `partial`, not implemented end-to-end in production.
- The deterministic tests exercise the production PCM handler, event projector, DOCX renderer, ownership policy and download path using captured Hermes output events; they do not call a live nondeterministic model or production server.
- The shared working tree contains concurrent Batch 1–4 changes outside this task; none were reverted, staged, committed or pushed.
