# Chat attachment and quoted-context execution chain — 20260923

- task_id: `20260923-chat-attachment-quote-execution-chain`
- status: `TESTED` (release receipt will be appended after exact-SHA deployment)
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/quantum-2.0-publication-main`
- baseline_at_start: `34161e9abf6a6c642b035cf95438db1ffa67e170`
- synced_main_before_release: `d4ce6059f02742bdde3d8a79efaba37276ea6183` (fast-forward only)
- scope: uploaded PDF/DOCX/PPTX follow-up questions; selected-text/quoted-context questions; existing Hermes tool/SSE chain reuse

## Change

- Pass existing `quoted_context` into both streaming and non-streaming triage and Hermes goals.
- Evaluate triage against the question plus quoted context so short follow-up questions do not fall into the tool-less `fast_general` path.
- Mark authenticated uploaded-document contexts as requiring the existing `user_note_search` evidence tool; retain `knowledge_search` only when the question itself declares broader document/knowledge intent.
- Reuse the existing document upload/compilation and signed `clientSessionContext` path. In auto mode attach only the most recently ready document and carry its `active_document_note_id`; Hermes deterministically targets that exact note.
- Extend the existing capability-protected Knowledge Gateway with a current-user `note_ids` selector, so durable exact-note content outranks the bounded inline fallback and unrelated private notes remain excluded.
- Extend the existing iOS document picker plus backend document allowlist to PPTX and verify real extraction. Supported Office formats remain DOCX/PPTX; legacy DOC/PPT are intentionally rejected because the existing extractor does not support them.
- Keep streaming and non-streaming bridge payloads aligned for signed client context, quote text, request id, and client capabilities.

## Verification before release

- Python focused, client-context, knowledge-gateway, Hermes toolchain, and deployment-contract regression: `333 passed`, `0 failed`, `6 warnings`.
- Knowledge Gateway scaling/contract regression: `34 passed`, `0 failed`, `4 warnings`.
- Python compile: edited backend, bridge, and test modules passed.
- `git diff --check`: passed.
- iOS `build-for-testing`: passed on iPhone 17 Pro / iOS 26.1 simulator after the final source changes.
- iOS unit tests after final source changes: `176 passed`, `0 failed`; signed-Keychain acceptance is excluded because this simulator build intentionally uses `CODE_SIGNING_ALLOWED=NO`.
- xcresult: `/tmp/quantumn-attachment-chain-final-full-retry.xcresult`.

## Independent review

- Round 1: `NO-GO` — PPTX backend allowlist, target binding, generic-office privacy false-positive, and coverage gaps.
- Round 2: `NO-GO` — non-stream context loss, quoted text omitted from Hermes goal, and non-deterministic active-document retrieval.
- Round 3: `NO-GO` — bounded inline text could shadow the durable document and failed attachments could obscure the last ready document.
- Round 4: `NO-GO` — generic “API 文档 / Word 文档模板” questions could still open private-note search.
- Final focused re-review: `GO` — all prior blockers cleared; generic document questions and unrelated questions with an active attachment no longer trigger private-note search, while concise active-document follow-ups still do.

## Release receipt

- release_commit: pending
- remote_sha: pending
- server_before: pending
- server_after: pending
- rollback_point: baseline `34161e9abf6a6c642b035cf95438db1ffa67e170`; production rollback point to be read before deploy
- health_check: pending
- functional_check: pending
- independent_review: `GO`

## Remaining gates

- Real authenticated iOS upload → compilation → follow-up chat and selected-text chat are not yet physically exercised in this receipt.
- TestFlight/App Store binary distribution is not part of this source/server release unless separately recorded with an archive/upload/processing receipt.
