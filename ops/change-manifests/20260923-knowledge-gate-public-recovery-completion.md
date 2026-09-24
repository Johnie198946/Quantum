# Optional knowledge pre-read recovery — 20260923

- task_id: `20260923-knowledge-gate-public-recovery`
- status: `DEPLOYED`; public-question gateway recovery verified
- branch: `main`
- worktree: isolated clone `quantum-knowledge-gate-20260923`
- baseline: `8ea0dcc31843a48517d96f0e8a7c0407ee944d8e`, clean before edits; fetched current `origin/main`, fast-forward verification passed
- origin: `https://github.com/Johnie198946/Quantum.git`; visibility verified public
- server_before: `c5eb015edca6c28d5ef811c78970f3cd672fb057`
- authorization: user approved repair deployment and production verification

## Root cause and scope

Production's old final gate rejects `error` even when optional internal retrieval exposed no documents and public search succeeded. The runtime pre-read reproduces a timeout, mapped to generic `knowledge_gateway_unavailable`. A separate repository contained newer gate semantics; deploying its whole tree would regress unrelated current-production changes, so only the knowledge gate and its caller are ported onto the actual production main.

No Jev, new Runtime, iOS change, timeout increase, permission expansion, or travel feature is included. Existing attachment and quoted-context changes are retained. Public regression fixtures are synthetic; real prompts, identities, tokens, run payloads, and private knowledge stay outside the repository.

## Contract

- Trusted triage defines required versus optional knowledge independently of runtime availability.
- Optional retrieval failure with no internal exposure cannot become a blanket public-QA denial.
- Required knowledge, explicit authorization denial, malformed/unknown observation, exposed internal evidence without verifiable citations, and changed versions remain fail-closed.
- Direct and deferred knowledge results are observed; exposure cannot be cleared by a later empty result.
- `knowledge_gate_receipt.v2` separates requirement, attempt, consumption, retrieval status, failure kind, and final decision. Public-only evidence is not labelled internal retrieval.
- Gateway timeout has a separate error instead of generic unavailability.
- The new selected-book bypass from the other repository is deliberately excluded from this repair.

## Verification

- Focused Bridge, chat API/stream/status, triage, worker, attachment/context, Knowledge API/policy/scaling regressions: **318 passed, 0 failed, 0 skipped**, 9 deprecation warnings.
- `git diff --check`: passed.
- An initial test selector referenced a nonexistent file and ran no tests; corrected selector produced the actual result above.
- Initial transplant test exposed a missing timeout adapter branch; fixed and reran successfully.

## Release fields

- head/local_commit: pending
- remote_sha: pending
- server_after: pending
- health_check: pending
- functional_check: pending authenticated production replay of the reported public question
- rollback_point: current release retained; exact path/image/attestation snapshot to be recorded before deployment
- remaining_risks: internal retrieval timeout latency is distinct from erroneous public-answer blocking; this repair does not claim general internal-knowledge retrieval quality is solved. No physical iOS UI test yet.

## Release receipt

- Code commit and deployed SHA: `6d761991870150f65a7c1468388ccbb142eeba0e`.
- Prior deployed SHA / rollback release: `c5eb015edca6c28d5ef811c78970f3cd672fb057`.
- Bridge source SHA-256: `a3e6853b6e349d7475b2803f9e14cec26b860d32cc0934413b6dd311d22f9e53`.
- Exact-SHA release script completed successfully; source, image revision and
  release pointer were checked, and health/readiness gates passed.
- Live Bridge / worker services and API health were read back after release.
- Original public question replayed through HTTPS `/api/chat/stream`:
  HTTP 200, terminal `done`, persisted run `completed`, nonempty answer blocks,
  empty error code, no knowledge-gate rejection.
- Actual live receipt: optional knowledge requirement, internal search no-match,
  no internal knowledge exposed, `allowed_without_internal_knowledge`.
- Timeout/gateway-unavailable recovery is covered by deterministic regressions;
  the live replay itself encountered no-match, not a forced timeout.
- Private request identifiers and replay payload remain outside this public repo.

## Acceptance boundaries

- This verifies removal of the public-question false block, not the semantic
  accuracy of the generated answer or general internal-knowledge recall.
- The replay searched the web but omitted source URLs in its answer. Therefore
  `web_fallback=false` is consistent with the current retrieved-and-cited URL
  intersection rule; it does not mean no web tool ran. Do not attribute this to
  Hermes safety wrapping without callback evidence.
- No physical iOS visual replay was performed. Existing failed messages were
  not rewritten; regeneration uses the deployed fix.
