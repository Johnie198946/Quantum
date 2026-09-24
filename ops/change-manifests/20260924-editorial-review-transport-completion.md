# Editorial Review Transport Completion Manifest

status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/quantum-2.0-publication-main
head/local_commit: pending
remote_sha: pending
server_before: 6508fac50326df95d5346710233e40c05ec12218
server_after: pending
health_check: pending
rollback_point: /opt/releases/ai-lab-platform-6508fac50326.CWEkHm

## Scope

Fix native editorial-review attestation failures caused by Cron output bounds corrupting large inline `manuscript_b64` payloads.

## Design

- Review requests now carry deterministic gzip-compressed Base64 manuscript bytes as `manuscript_gzip_b64`.
- Native attestation decompresses and verifies the exact manuscript bytes before signing.
- Legacy uncompressed `manuscript_b64` requests remain supported.
- Corrupt compressed material fails closed.

## Verification

- `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q tests/test_publication_review_provenance.py tests/test_publication_editorial_remote.py`: 56 passed.
- `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q tests/test_*publication*.py`: 195 passed.
- Ruff and `git diff --check`: passed.
