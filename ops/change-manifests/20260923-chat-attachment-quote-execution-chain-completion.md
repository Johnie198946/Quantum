# Chat attachment and quoted-context execution chain — 20260923

- task_id: `20260923-chat-attachment-quote-execution-chain`
- status: `VERIFIED` (source pushed; exact-SHA production server deployment verified; iOS binary distribution intentionally not performed — see Remaining gates)
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/quantum-2.0-publication-main`
- baseline_at_start: `34161e9abf6a6c642b035cf95438db1ffa67e170`
- synced_main_before_release: `d4ce6059f02742bdde3d8a79efaba37276ea6183` (fast-forward only)
- scope: uploaded PDF/DOCX/PPTX follow-up questions; selected-text/quoted-context questions; existing Hermes tool/SSE chain reuse

## Change

- Pass existing `quoted_context` into both streaming and non-streaming triage and Hermes goals.
- Evaluate triage against the question plus quoted context so short follow-up questions do not fall into the tool-less `fast_general` path.
- Mark authenticated uploaded-document contexts as requiring the existing `user_note_search` evidence tool; broader platform/public retrieval continues to follow its existing independent triage criteria.
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

- release_commit: `c5eb015edca6c28d5ef811c78970f3cd672fb057`
- remote_sha_before_deploy: `c5eb015edca6c28d5ef811c78970f3cd672fb057` (verified with `git ls-remote origin refs/heads/main`)
- server_before: `/opt/releases/ai-lab-platform-381d619b411b.dchorF`, deployed SHA `381d619b411bcfe66230407a144cbcae3f48c04e`
- server_after: `/opt/releases/ai-lab-platform-c5eb015edca6.mAsZSd`, deployed SHA `c5eb015edca6c28d5ef811c78970f3cd672fb057`
- rollback_point: prior release `/opt/releases/ai-lab-platform-381d619b411b.dchorF`; backend image tags `*:rollback-before-c5eb015edca6`; attestation backup `/opt/ai-lab-shared/deploy-backups/chat-attachment-quote-before-c5eb015edca6/offline-images.attested`
- health_check: public `https://t-react.com/ready=200`, `https://t-react.com/health=200`; internal API `/ready=ready/0.8.0`, `/health=ok/0.8.0`; Bridge `/health=ok/v6.0`; `hermes-bridge` and `hermes-chat-worker` active; 8 Compose services running, 0 unhealthy
- functional_check: running API container passed attachment triage privacy/positive smoke; all four backend runtime images read back as `sha256:294ed2f2731a1501153a66deb6c8ce1c1305ddfd16474f78cbf639baa0fc6b88`, non-root `ailab`, OCI revision equal to the deployed SHA
- independent_review: `GO`

### Deployment incident and recovery

- First exact-SHA attempt stopped before cutover because the production offline backend image attestation still referenced the prior image.
- A full offline rebuild could not resolve the pinned Docker Hub base image from the server. The target lock only removed packages from the installed prior lock; no target dependency was missing.
- Recovery used the existing attested production image as the offline parent, replaced the complete target `backend/`, `config/`, and `scripts/` trees from a SHA-256-verified archive of the pushed commit, installed/verified the target locks with `--no-index`, removed packages absent from the target lock, and validated `pip check`, `import backend.main`, triage smoke, architecture, healthcheck, non-root user, and OCI revision before atomically updating four backend tags and the attestation.
- The second standard `deploy_exact_sha.sh` run exited `0`, performed the atomic release switch, and returned the server/release/rollback receipt above.

## Remaining gates

- Real authenticated iOS upload → compilation → follow-up chat and selected-text chat are not yet physically exercised in this receipt.
- No TestFlight binary was uploaded from this worktree: it reports project build `38`, while a separate local candidate reports build `42` and the current-product evidence identifies build `43` as the user-visible version. Publishing this older source as a new build could regress the replaced UI. A TestFlight release requires the exact build-43-or-newer source/commit to be recovered and these changes ported and revalidated there.
