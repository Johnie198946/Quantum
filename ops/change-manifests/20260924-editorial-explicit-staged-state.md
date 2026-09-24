# Editorial approval: explicit staged state

Date: 2026-09-24

## Incident

An approved editorial attempt was recorded correctly, but the author bundle still carried `state: draft`. The finalize client passed that state through to the stage operator. The server therefore created a valid reviewed edition in `draft`, while the client correctly rejected the readback because it expected `staged`, `scheduled`, or `published`.

## Change

- On approved finalize, set the outgoing bundle state explicitly to `staged` before invoking the stage operator.
- Preserve rejection behavior and all review/provenance/hash gates.
- Add regression coverage for an author bundle that enters finalize with `state: draft`.

## Verification

- Publication test suite: 201 passed.
- Ruff: passed.
- `git diff --check`: passed.

## Recovery

After deployment, retry the idempotent finalize. The existing approved attempt and edition are reused; the edition must read back as staged, scheduled, or published before the local manifest advances.
