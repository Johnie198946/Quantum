# Publication cover title follow-up

- task_id: publication-standard-workflow-20260926
- followup: 2026-09-27 用户截图指出真实封面没有可见书名。
- status: PUSHED；客户端修复已测试并推送，联合 Build 69 打包/真机验收待接手任务回执，不冒充已安装。
- branch: codex/publication-standard-workflow-20260926
- worktree: /Users/dengzhaoyu/Documents/AI Lab/.worktrees/publication-standard-workflow-20260926
- head/local_commit: ec6b633c8926a4a6334384f3b7c005f2d32f1f62（标题代码与测试）；后续仅交付记录提交。
- remote_sha: ec6b633c8926a4a6334384f3b7c005f2d32f1f62；origin refs/heads/codex/publication-standard-workflow-20260926，git ls-remote 已确认。
- server_before: 不适用，本补修只涉及 iOS；未部署服务器。
- server_after: 不适用，保持其他任务管理的服务器版本。
- health_check: 不适用，本补修不涉及服务端。
- functional_check: 3项iOS模拟器测试通过；5种封面OCR、鉴权图片渲染、账号切换清图。已人工查看长中文和84px小封面截图，文字可读。真机新包尚待协调任务验收。
- rollback_point: 修复前任务HEAD 9bf22c559e3f44caa240bd5df8be403215d9c256；只有标题代码需要撤销时，由集成任务显式revert对应cherry-pick提交，不回退缓存/鉴权或后端。
- remaining_risks: 未安装新客户端前仍显示旧行为；极长标题沿用既有2/3行截断，完整标题保留于数据与详情。

## Git盘点与隔离

开工前任务worktree clean，HEAD 2b55562df473c31de7fc81e7838588cb77d79812；branch codex/publication-standard-workflow-20260926；origin https://github.com/Johnie198946/Quantum.git。worktree列表包含canonical /Users/dengzhaoyu/Projects/quantum-2.0-publication-main（main 2d893130）、本任务、quantum-jev-research-egress-20260923（be1b6bf）、story-port-review-20260926（detached ea7b263）。未修改其他worktree。

本补修是原出版任务的客户端缺陷跟进，沿用原隔离分支/worktree。先整合联合主线e07c57f（merge a938aa5），再整合db9ce27后端修复（merge 9bf22c5）。保留所有并行改动，不覆盖canonical未提交文件，不共享stash。集成任务只cherry-pick ec6b633单提交，无须合入本分支其余历史。

## 根因与最小修复

- 标题数据存在；IllustratedBookCover原先仅在image==nil时绘制Text(title)/Text(author)。真实封面加载成功就隐藏文字，与用户截图一致。已有无障碍标签仍包含标题，因此仅验证图片/AX不足以发现视觉缺失。
- 复用PublicationBookCover→IllustratedBookCover共享入口，书架、详情和其他使用者一起受益。书名/作者无条件显示，真实图片下加97%不透明浅色底板，品牌kicker只保留在旧模板。
- 保留图片16:9纵向比例、账户缓存weak owner、URL鉴权、凭证变更清图；不修改任何正文、图片字节、出版调度或内容合同。无新依赖/抽象。
- 变更文件：ios/AIPlatformApp/DesignSystem/Theme.swift；ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift；本记录。

## 可复现验证

测试设备：iOS26.1 iPhone17Pro模拟器 A5005DE7-3D7E-4FA0-A9D9-92967B4A699A。使用既有AIPlatformApp scheme，单独本任务derivedData /tmp/quantum-publication-ios-derived。

1. 新增testBookTitleRemainsVisibleWithLoadedCover，ImageRenderer生成真实SwiftUI像素，再以系统Vision OCR验证文字。旧代码3个有图场景共6条断言失败，无图场景通过：/tmp/publication-title-before.log、/tmp/publication-title-before.xcresult。
2. 修复后，深色、浅色、84px小封面、长中文标题、无图模板5场景全部通过；同时testPublicationCoverAndReaderImagesRenderAuthenticatedFixture与testPublicationImageClearsOnCredentialChangeAndDisappearance通过，共3测试0失败。/tmp/publication-title-final.log、/tmp/publication-title-final.xcresult。
3. 截图导出到/tmp/publication-title-final-attachments，人工查看中文长标题和小封面，深底上文字底板清晰。截图为合成测试封面，不冒充生产真机。
4. git diff --check通过。

## 协调交付

已把精确代码SHA ec6b633c8926a4a6334384f3b7c005f2d32f1f62、测试记录和验收要求发给用户授权协调的清理任务01a0de14-6e79-7cc2-9765-5313560c4dcb。其负责重归档尚未上传的联合69及真机/上传；reader任务负责唯一服务器/runtime切换。本任务不并行操作设备、归档或服务器。
