# Editorial review transport: sub-threshold chunks

Date: 2026-09-24

## Incident

The 32-character Base64 chunk transport still allowed the gateway redactor to replace a high-entropy substring inside one chunk. The affected native request contained `***`, so provenance correctly failed closed with `native request lacks actual review material`.

## Change

- Reduce deterministic gzip+Base64 chunks from 32 to 12 characters.
- Enforce the same maximum in server-side provenance validation.
- Preserve compatibility with legacy manuscript and single-field gzip payloads.
- Do not relax hash, target, native-session, or reviewer-independence checks.

## Verification

- Publication test suite: 200 passed.
- Ruff: passed.
- `git diff --check`: passed.
- Production must be deployed from the exact Git commit and all API/worker images read back before retrying review.

## Rollback

Deploy the previous exact SHA. Existing failed review artifacts remain non-attestable and must not be reused.
