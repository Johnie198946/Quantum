# Optional knowledge pre-read recovery — 20260923

- task_id: `20260923-knowledge-gate-public-recovery`
- status: `TESTED`; deployment and live replay pending
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
