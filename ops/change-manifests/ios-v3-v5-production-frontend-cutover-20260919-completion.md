# Completion Manifest

- task_id: `ios-v3-v5-production-frontend-cutover-20260919`
- goal: 将已验收的 V3–V5 iOS 前端作为现有客户端唯一正式运行界面，退出旧 UI 的生产入口，同时保留现有数据结构、接口和后端协议。
- status: `TESTED`

## Architecture decision

- 判定为已实现：新版不是旁路 App，而是原位修改 `ios/AIPlatformApp` 的生产组件。
- 正式入口保持 `AIPlatformApp -> AppRootCoordinatorView -> MainTabView`，直接加载新版 `LoginView`、`ChatView`、`KnowledgeView`、`WorkflowDashboardView` 和 `SettingsView`。
- 原型导航和页面选择器仅位于 `#if DEBUG`，不进入 Release 产物；保留它们供 UI 回归测试使用，不新增第二套生产前端。
- React `frontend/` 是独立 Web 管理控制台，不属于本次移动端切换范围，未做破坏性下线。
- 本次无需新增产品代码；只进行了 Release 切换验证与真机覆盖安装。

## Git preflight

- status: 隔离 worktree 已包含本轮持续进行的 V3–V5 前端改造；未覆盖、清理、暂存或提交其他改动。
- branch: `codex/ios-v3-v5-style-sandbox-20260917`
- HEAD: `58d212f18ed1edd71d0a95d18b12fc0b820eb277`
- remote: `origin` = `/Users/dengzhaoyu/Documents/AI Lab/Quantum-2.0`; `source` = `https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/Users/dengzhaoyu/Documents/AI Lab/.worktrees/quantum-ios-style-sandbox-20260917`

## Validation

- Signed Release build: passed for physical destination `00008150-000C50980244401C`.
- Release bundle: `com.ailab.AIPlatformApp`; executable: `AIPlatformApp`.
- Release binary inspection: `-prototypePreview`, `-tabBarPreview`, `-bookshelfPreview`, and `-knowledgeHomePreview` are absent.
- Physical-device install: passed at 07:50 on `囧尼部落` (`CFE79F35-1270-527D-8BD7-9AB60449B6DF`).
- Automatic launch: denied by SpringBoard because the phone remained locked; the installed app can be opened after unlock.
- `git diff --check`: passed.
- Related regression evidence inherited from the immediately preceding implementation pass: 145 iOS tests and 27 PPT capability tests passed.

## Delivery evidence

- commit SHA: not created; user did not request a commit.
- GitHub remote/ref/SHA: not pushed; no push authorization.
- server_before: iOS continues to target `https://120.24.248.58`.
- server_after: not deployed; no server deployment authorization.
- health_check: signed Release build and physical-device installation passed; launch automation was blocked only by device lock.
- functional_check: Release binary excludes all DEBUG preview routes and uses the production app coordinator; prior 145 iOS and 27 PPT regressions remain green.
- rollback_point: repository HEAD `58d212f18ed1edd71d0a95d18b12fc0b820eb277`; reinstall the preceding Debug build from `/private/tmp/quantum-ios-note-bookshelf-20260919` if local device rollback is needed.

## Remaining risks

- Final touch/visual acceptance requires unlocking the connected phone and opening the installed app.
- The locally tested PPT Hermes routing fix is still not deployed to `https://120.24.248.58`; frontend cutover does not change that backend state.
- Source changes remain uncommitted and unpushed by policy; this is a tested local/device cutover, not a GitHub or App Store release.
