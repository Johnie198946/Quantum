# Global editorial review discovery

Date: 2026-09-24

## Problem

The scheduled reviewer depended on `active-review-root.txt`, a mutable pointer that was set manually during incident recovery. A new daily author run could write a different dated directory while the reviewer continued scanning yesterday's completed root and returned `no_await_review`.

A naive global scan was also blocked by historical manifests that were either already reviewed locally or were legacy non-candidates.

## Change

- The scheduled review-input wrapper always scans the global controlled output root.
- A local review file is skipped before remote `await_review` readback, so completed historical attempts do not block discovery.
- Invalid historical manifests that are not marked `await_review` are ignored; malformed pending candidates still fail closed.
- `active-review-root.txt` is no longer part of scheduled review selection.

## Verification

- Focused publication tests: 30 passed.
- Ruff: passed.
- `git diff --check`: passed.
- Live global scan after all four 2026-09-24 issues completed: `{"status":"no_await_review"}` with exit 0.
