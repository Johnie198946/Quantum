# QuanSyn push/pull authenticated E2E repair

task_id: quansyn-push-pull-e2e-20261013
status: VERIFIED
branch: main
worktree: /Users/dengzhaoyu/Projects/Quantum-quansyn-e2e-20261013
implementation_commit: 38a935b5d62d82c246a87011ae48c7569cbca15b
remote_sha_at_deploy: 38a935b5d62d82c246a87011ae48c7569cbca15b
server_before: 165d4fffa71886fc3131d27869d4c7d874f866f8
server_after: 38a935b5d62d82c246a87011ae48c7569cbca15b
health_check: API ready; public health ok; all Compose services healthy; Hermes Bridge ok
functional_check: authenticated pull/return passed; standalone Mac push with attachment passed; exact readback and retry idempotency passed
rollback_point: /opt/releases/ai-lab-platform-165d4fffa718.dzFbvZ
manifest: ops/change-manifests/quansyn-push-pull-e2e-20261013-completion.md
remaining_risks: test transfers remain visible in the authenticated QuanSyn history as audit evidence

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

- Backend: `.venv/bin/python -m pytest tests/test_quansyn.py tests/test_quansyn_mac.py -q` → `30 passed`.
- Installed relay/client source: `python3 -m pytest tests/test_quansyn_relay_batch.py tests/test_quansyn_desktop_relay.py -q` → `18 passed` in `Johnie198946/ai-lab-platform` main checkout.
- The first host-Python run was invalid because global FastAPI/Starlette versions did not match the repository lock; it is not counted as a product test result. A task-local venv with repository-pinned FastAPI/Starlette was used for the valid run.

## Deployment and production verification

- Implementation SHA pushed and read back from GitHub main: `38a935b5d62d82c246a87011ae48c7569cbca15b`.
- Standard exact-SHA deployment initially stopped safely because the preloaded backend image still carried revision `165d4fffa71886fc3131d27869d4c7d874f866f8`.
- Built a proof child image from the exact current backend image, replacing only `/app/backend/api/quansyn.py`; image/source SHA-256 matched. New image: `sha256:a849d987e228a52552f7f088b15880cb85718e67eaf280acb5707456ccf4e548`.
- The first retry stopped safely on the 5 GiB disk gate. Eight oldest, unreferenced release directories were retired; current and immediate rollback releases were preserved.
- Standard `deploy_exact_sha.sh` then completed with exit 0.
- Independent readback: `.deployed-sha` and all four backend image labels equal the implementation SHA; API and workers use image `sha256:a849d987e228a52552f7f088b15880cb85718e67eaf280acb5707456ccf4e548`; all Compose services are healthy.
- Public `https://www.t-react.com/health` returned `{"status":"ok","version":"0.8.0"}`; internal `/ready` returned ready; Hermes Bridge returned ok. Bridge and chat worker CWDs both point to `/opt/releases/ai-lab-platform-38a935b5d62d.1b7oAk`.
- Authenticated post-deploy standalone Mac push: `qs_452cb2df24f7797f0acb6588bbe4cc93`.
  - Exact text marker read back: `QS-E2E-PUSH-e0d35e0e6484`.
  - Attachment SHA-256 read back: `2df51cd6adb84edbf1b6326391b0d9921a43f61ac1372aca07984c2ec0ee05b5`.
  - Repeating the same persisted-session push returned local cursor `noop=true`; no duplicate was created.
  - Anonymous and wrong-sender probes both returned 401.
- Authenticated Web→Mac pull and linked return evidence from the same account:
  - request `qs_d8014d2edc877af7ddee6d41afd4a38d` reached `returned`;
  - linked result `qs_9c0c9e3eaf85ddca067c3bd1e5461271` read back with the matching `reply_to` and exact marker.

## Rollout completion

1. Implementation commit pushed to `Johnie198946/Quantum` main and remote SHA verified.
2. Previous immutable release recorded as the rollback point.
3. Verified implementation SHA deployed through the existing exact-SHA release path.
4. Runtime SHA, image identity, health, authenticated push/pull records, attachment hashes, idempotency, and denial probes read back.
