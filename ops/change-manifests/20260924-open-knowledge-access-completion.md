# Open knowledge access — completion manifest

- task_id: `20260924-open-knowledge-access`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/quantum-2.0-publication-main`
- baseline: `076cc97a18aa82544f2503e256327883556d5e27`
- authorization: user explicitly requested commit, push, and production deployment in the active Feishu conversation.

## Scope

- Remove tenant, subscription, plan, security-color, owner, capability-scope, export/noexport, external-publication, and summary-substitution gates from authenticated knowledge reads.
- Apply the open-read contract to Wiki search, selected books, bookshelf projections, user-note model context, and the Hermes knowledge bridge.
- Preserve authentication, Vault path-escape protection, revoked/deleted lifecycle filtering, source withdrawal, file-version integrity, and non-knowledge write/publish/admin authorization.
- Preserve the unrelated untracked file `build_20260924_issues.py` without modification or staging.

## Verification before release

- Focused knowledge/read/bridge/policy regression: `217 passed, 1 skipped, 19 warnings`.
- Static verification: `git diff --check` and Python compile of all changed runtime modules passed.
- Full repository run: `2378 passed, 30 skipped, 38 failed, 99 errors`; the focused knowledge suite is green. The remaining failures/errors are in unrelated repository-wide fixtures and workflows, including TestClient/database state and extraction/publication/workflow suites. This release is therefore bounded to the verified knowledge-read surface rather than represented as a clean full-suite release.

## Release receipt

- implementation_commit: pending
- github_remote_sha: pending
- server_before: `/opt/releases/ai-lab-platform-076cc97a18aa.P6wnzY`, `.deployed-sha=076cc97a18aa82544f2503e256327883556d5e27`
- server_after: pending
- health_check: pending
- functional_check: pending
- rollback_point: pending

## Remaining risks

- Removing tenant and disclosure labels from reads intentionally changes confidentiality semantics for admitted shared knowledge. Authentication and path/lifecycle/integrity boundaries remain enforced.
- Production functional verification must prove a cross-tenant/red/noexport document can reach the authenticated model path while an out-of-Vault path and a withdrawn/deleted record remain unavailable.
