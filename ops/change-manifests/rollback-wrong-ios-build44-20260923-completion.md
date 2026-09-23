# Completion Manifest

- task_id: `rollback-wrong-ios-build44-20260923`
- objective: 回滚从旧 `source/main` 基线错误构建、推送和上传的 iOS Build 44。
- status: `PUSHED`

## Incident

- wrong release source: `7b08337d56ef37cf1e85c4fa1a543e4ed8f15ff1`
- wrong receipt commit: `10f63c53917b1ce3dc0ec3cf9061933ae63a6105`
- root cause: 发布候选错误地基于旧 `source/main@3a319d49973e1dafa4971b30096437bcb37f68b7`，不是用户当前最新前端版本。
- affected upload: TestFlight `1.0.3 (44)`。

## Rollback

- revert receipt commit: `c17d7e0`（撤销错误发布回执）
- revert feature commit: `8c05e3d3c17d490af0fe3e45c1784c90bb93a39f`（撤销错误前端和 Build 44 源码）
- restored code tree check: `git diff --quiet 3a319d49973e1dafa4971b30096437bcb37f68b7 HEAD` returned `0` before adding this audit-only manifest。
- remote readback: `source/main@8c05e3d3c17d490af0fe3e45c1784c90bb93a39f` matched local after rollback push。

## TestFlight Containment

- App Store Connect readback: Build 44 upload processing completed。
- distribution readback: `群组 (0)`；未分配任何内部或外部测试组，测试员不可访问。
- Apple does not support deleting an uploaded build; `将构建版本设为过期` was disabled at readback, so no unsupported destructive action was claimed。
- prior distributed Build 43 was not changed。

## Preservation

- Existing dirty manifests were neither staged nor changed by rollback:
  - `ops/change-manifests/ios-explicit-memory-receipt-20260913-completion.md`
  - `ops/change-manifests/knowledge-action-context-handoff-20260913-completion.md`
  - `ops/change-manifests/hermes-operation-attribution-20260913-completion.md`

## Standard Status

- branch: `main`
- worktree: `/Users/dengzhaoyu/Documents/AI Lab/Quantum-2.0`
- server_before: 不适用
- server_after: 不适用
- health_check: 不适用
- functional_check: Git 代码树恢复；TestFlight Build 44 群组为 0
- rollback_point: `source/main@3a319d49973e1dafa4971b30096437bcb37f68b7`
- remaining_risks: Build 44 上传记录永久保留在 App Store Connect，但没有测试组访问权限；后续必须先定位并验证真正最新前端分支，再使用新的构建号发布。
