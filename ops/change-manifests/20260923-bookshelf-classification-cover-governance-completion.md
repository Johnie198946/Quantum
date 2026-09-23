# Completion Manifest

- task_id: `20260923-bookshelf-classification-cover-governance`
- objective: 1:1 对齐书架设计稿；修复查看全部入口；为现有与后续连载提供内容相关、可校验的独立封面。

## 变更文件

- `ios/AIPlatformApp/Views/Settings/SettingsView.swift`
- `ios/AIPlatformApp/DesignSystem/Theme.swift`
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
- `ios/AIPlatformApp/Assets.xcassets/book_publication_*.imageset/*`
- `backend/services/knowledge_publication_store.py`
- `backend/services/knowledge_catalog.py`
- `backend/api/subscriptions.py`
- `scripts/publication_operator.py`
- `scripts/publication_editorial_remote.py`
- `docs/prompts/quantumn-editorial-v2.md`
- `docs/publication-operations-runbook.md`
- `tests/test_daily_publication.py`
- `tests/test_publication_editorial_remote.py`
- `tests/test_publication_editorial_workflow.py`

## 开工前 Git 盘点

- status: 分支已有同一 build45 连续任务的未提交改动；未清理、覆盖、暂存或混入其他 worktree。
- branch: `codex/archive-confirmation-build45`
- HEAD: `5085e6585f0ae69c20a49747c3257568709fd852`
- remote: `origin=https://github.com/Johnie198946/Quantum.git`; `source=https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/quantum-home-capability-build45`

## 实现与复用

- 复用 `SubscriptionCenterView`、现有书架 DTO、订阅进度、`IllustratedBookCover` 和刊物发布主链路；未新增平行 service/repository。
- 书架首页、全部书籍、筛选排序、书单与主题卡片按设计稿收敛；“查看全部/查看更多”进入现有全部书籍页面。
- 使用 imagegen 按 6 本线上刊物的正文主题生成 6 张不同封面，并以稳定 publication ID 绑定；文字继续由 iOS 原生排版。
- 新刊 manifest 增加 `cover_file/cover_sha256`；正式 stage 强制 PNG/JPEG 封面并写入私有收据。书架 DTO 只暴露 `cover_available`，封面字节通过鉴权端点返回，iOS 失败时回退到旧模板。

## 测试与校验

- `python3 -m pytest -q tests/test_daily_publication.py::test_published_cover_is_verified_and_projected tests/test_publication_editorial_workflow.py::test_cli_signed_approval_ingests_proof_and_releases tests/test_publication_editorial_remote.py`: `27 passed`。
- iOS Simulator Debug build（无签名）: `BUILD SUCCEEDED`。
- iOS test target `build-for-testing`（无签名）: `TEST BUILD SUCCEEDED`。
- 模拟器安装、启动并截图核对书架首页；按截图移除主搜索框多余筛选图标，并区分三类书单插画；最终增量构建 `BUILD SUCCEEDED`。
- `git diff --check`: 通过。

## 当前状态

- status: `TESTED`
- commit_sha: 未授权/未执行。
- github_remote_ref_sha: 未授权 push/未执行。
- server_before: 未授权部署/未执行。
- server_after: 未授权部署/未执行。
- health_check: 本地 Python 发布链路测试与 iOS 编译通过；服务器未检查。
- functional_check: 封面收据、发布接力、DTO 投影、鉴权读取和 iOS 回退路径已通过自动化/编译检查；模拟器完成视觉截图核对，本轮未安装真机。
- rollback_point: 当前 HEAD `5085e6585f0ae69c20a49747c3257568709fd852`；按本 manifest 文件清单逐项回退，不能覆盖同文件内前序任务改动。

## 风险与未完成项

- 现有 6 本刊物使用 App 内稳定 ID 映射完成封面治理；服务端已发布 edition 保持不可变，没有回写旧 bundle。
- 后续新刊必须在作者阶段调用 imagegen 产出封面；能力不可用或封面不匹配时按协议 blocked。
- 未 push、未部署后端、未安装真机、未上传 TestFlight。
