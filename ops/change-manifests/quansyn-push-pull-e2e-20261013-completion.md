# QuanSyn push/pull authenticated E2E repair

task_id: quansyn-push-pull-e2e-20261013
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/Quantum-quansyn-e2e-20261013
head/local_commit: pending
remote_sha: pending
server_before: 165d4fffa71886fc3131d27869d4c7d874f866f8
server_after: pending
health_check: pending
functional_check: authenticated production pull/return passed; standalone Mac push reproduced HTTP 403 before repair; post-deploy verification pending
rollback_point: pending
manifest: ops/change-manifests/quansyn-push-pull-e2e-20261013-completion.md
remaining_risks: deployment and authenticated production recheck pending

## Scope and boundary

- Keep QuanSyn on the existing account, device, transfer, artifact, tenant, and agreement models.
- Do not add a second runtime, router, registry, tenant model, or credential class.
- Preserve the paired Mac credential's tenant/user/sender binding and its existing `target=mac` read scope.
- Extend the existing transfer endpoint only enough to support the already-shipped `/push` client contract: a paired Mac may create an owner-scoped `direction=result,target=mac` transfer without `reply_to`.
- Existing reply-to result behavior remains unchanged.
- Standalone pushed files must have been uploaded by that exact paired device; account files or another device's files remain forbidden.

## Production evidence before repair

Authenticated account: phone account ending `0894`; tenant `xFusion_MO_Tenant`; paired sender `ou_3af6a2fa4c4035cfbcdcbb5bf9a319dc`.

- Phone authentication and `/api/v1/me` succeeded.
- Web-to-Mac request `qs_d8014d2edc877af7ddee6d41afd4a38d` was claimed/imported by the actual local plugin path.
- Mac return `qs_9c0c9e3eaf85ddca067c3bd1e5461271` was created with matching `reply_to`; the request read back as `returned`.
- Re-pairing and Keychain replacement succeeded; therefore the prior 403 was not caused by an expired local credential.
- Actual `quansyn_relay.push_recent` reproduced HTTP 403.
- Direct readback exposed the server denial: `Mac 凭证只能回传关联结果`.

## Change

- Permit paired Mac credentials to create standalone owner-scoped result transfers to `target=mac`.
- Continue denying device-created requests and device results targeting iOS.
- Require all files on a standalone Mac push to carry metadata for the same device ID.
- Add regressions for standalone text push, idempotent retry, target/direction denial, foreign file denial, and same-device file acceptance.

## Verification

- `.venv/bin/python -m pytest tests/test_quansyn.py tests/test_quansyn_mac.py -q`
- Result: `30 passed`.
- The first host-Python run was invalid because global FastAPI/Starlette versions did not match the repository lock; it is not counted as a product test result. A task-local venv with repository-pinned FastAPI/Starlette was used for the valid run.

## Rollout plan

1. Commit and push this exact main revision to `Johnie198946/Quantum`.
2. Verify GitHub `main` equals the local commit.
3. Record the current production release as rollback point.
4. Deploy the verified GitHub SHA through the existing exact-SHA release path.
5. Verify `/health`, server `.deployed-sha`, authenticated Mac standalone push, account-side transfer readback, retry idempotency, Web-to-Mac pull, and Mac reply-to return.
