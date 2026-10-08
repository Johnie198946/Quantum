# Bookshelf performance repair completion record

Date: 2026-10-08
Base: GitHub `main` at `31c5194d84c4b03a6f6edaa5c5804f3954855819`
Scope: bookshelf catalog, publication admission read path, authenticated publication media, iOS local cache

## Problem

Production measurement before this change found:

- public `/health`: about `0.12s`
- API-local health: about `0.01s`
- bookshelf server processing: about `4.7–8.5s` for `62` published books
- the old read path re-opened and re-hashed publication bodies, receipts, and `108` media assets, including image decode/dimension checks
- Settings then fetched subscriptions serially through a second endpoint that rebuilt the same public catalog
- publication media returned `Cache-Control: private, no-store`
- iOS publication media used `.reloadIgnoringLocalCacheData`, so navigation/view reconstruction could download and decode the same `1440×2560` images repeatedly

## Implemented contract

### 1. Admission validation happens once

`backend/services/knowledge_publication_store.py` now persists `publication_admissions` rows bound to:

- `edition_id`
- `content_hash`
- SHA-256 of the frozen `bundle_json`
- `body_ref`
- optional `released_at` receipt

Full body/receipt/media format, hash, and dimension validation runs at stage admission. The stage transaction persists the admission marker with no release receipt. `release_due` atomically records `released_at` in both the edition and its admission marker; ordinary reads require those timestamps to match, so directly changing an admitted staged row to `published` cannot bypass release. Release and ordinary reads otherwise reuse the marker and perform only lightweight state, actual-release, withdrawal, rights-expiry, binding, file-presence, asset-path, byte-count, and MIME checks. They do not re-hash or decode the publication corpus.

An idempotent retry of the exact same admitted stage payload checks the persisted binding and returns the frozen row before all heavyweight validators. Re-submitting an already published or withdrawn edition performs only the frozen-field compatibility guard. Changed or previously blocked payloads still execute a new full admission.

The `publication-admission-v1` migration validates historical `published`, `staged`, and `scheduled` rows once. Rows that fail do not receive a marker and fail closed as `publication_not_admitted`; the migration receipt prevents repeated scans on later process/request construction. A manual state flip cannot publish content because reads also require `actual_release_at` and the bound admission marker.

Post-admission storage corruption is handled by explicit withdrawal and a newly admitted replacement version; ordinary reads deliberately do not rescan immutable publication evidence.

### 2. Previously computed catalog work is reused

`GET /api/v1/knowledge-bookshelves` now returns `subscribed_book_ids` in the same response as the bookshelf catalog. The iOS Settings bookshelf uses that projection directly. It calls the legacy subscription endpoint only when talking to an older server that omitted the field.

This removes the normal serial second request and therefore removes the second catalog construction from one screen load.

The endpoint also loads the admitted publication rows once and injects the same immutable snapshot into both the shelf projection and public-source collection projection. `bookshelf_catalog` passes that same snapshot to `public_source_catalog`, so one request no longer traverses the publication store two or three times.

### 3. Publication images use an iPhone-local cache

Authenticated publication media now provides a strong ETag from the already persisted asset receipt and supports `If-None-Match`/`304` without recomputing image hashes or opening images for validation.

The response policy is:

`Cache-Control: private, no-cache, max-age=0, must-revalidate`

This stores private bytes in the iPhone URL cache while requiring authorization and current publication visibility before reuse. It avoids retransmitting the `~1–2 MB` body on a `304` but does not allow a logged-out or withdrawn publication to bypass the server.

The iOS client now has a dedicated publication-media `URLSession` using `.useProtocolCachePolicy`, a persistent `512 MiB` disk cache, and a `64 MiB` byte cache. Concurrent requests for the same authenticated route are coalesced. Credential changes cancel in-flight image work and clear the private URL cache. The existing tenant/account-scoped decoded-`UIImage` cache remains capped at `32` images / `48 MiB` and is cleared when the API instance, base URL, or credential generation changes, avoiding repeated decode during one signed-in session without crossing accounts.

## Compatibility and security

- JWT, tenant/category visibility, subscriptions, publication state, withdrawal, and rights expiry remain checked.
- Media URLs remain same-origin, publication-bound paths; external URLs, query injection, traversal, fragments, and publication-ID mismatch are rejected before adding authorization.
- A new iOS client remains compatible with an older server through the optional `subscribed_book_ids` fallback.
- A new server remains compatible with existing clients because the response only adds an optional field and standard HTTP cache headers.

## Verification

- Focused admission, catalog reuse, subscription-center, and migration blocker regressions: `36 passed`, `13 warnings`.
- Expanded backend publication/bookshelf/subscription suite after the final once-only admission and release-receipt changes: `401 passed`, `13 warnings` (deprecation warnings only).
- Swift/Xcode focused cache, coalescing, auth, cancellation, route-safety, DTO, and bookshelf tests: `8 passed`, `0 failed`; `** TEST SUCCEEDED **`.
- Python lint: Ruff passed.
- Patch formatting: `git diff --check` passed.
- Adversarial follow-up review: `PASS`; published reads require the admission receipt `released_at` to match `actual_release_at`, and the targeted forged-transition tests passed.
- Simulator build/install/launch: exit `0`; `com.ailab.AIPlatformApp` launched and rendered the login screen without crash, blank content, clipping, or error banner.

## Deployment boundary

This record describes the locally implemented and tested patch. It is not yet a production or App Store/TestFlight receipt. GitHub push, production migration/deployment, authenticated production cold/hot timing, and signed iPhone distribution require explicit external-write approval and separate read-back receipts.
