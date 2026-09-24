# Editorial Review Redaction-Safe Chunk Transport Manifest

status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/quantum-2.0-publication-main
head/local_commit: pending
remote_sha: pending
server_before: 4a8da38156d8288aa1e17e48050c69a8a8d2a20b
server_after: pending
health_check: pending
rollback_point: /opt/releases/ai-lab-platform-079e324eaa99.J2toza

## Incident

A valid `concept-fables` revision 4 review could not be attested because the gateway replaced three characters inside one long `manuscript_gzip_b64` token with `***`. The native request remained valid JSON but its gzip/Base64 manuscript bytes were corrupt, so attestation correctly failed closed with `native request lacks actual review material`.

## Scope

- Split deterministic gzip/Base64 manuscript transport into ordered JSON string chunks of at most 32 characters.
- Reassemble and validate chunks only inside native attestation.
- Retain compatibility with existing single-string gzip/Base64 and legacy Base64 requests.
- Reject empty, non-string, oversized, malformed Base64, or invalid gzip chunks.
- Do not weaken reviewer independence, target hash, body hash, source receipt, or signature checks.

## Verification

- `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_*publication*.py`: 200 passed.
- Ruff: passed.
- `git diff --check`: passed.
- Production deployment, native re-review, finalize, and service readback remain pending.
