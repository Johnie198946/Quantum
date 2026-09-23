# Completion Manifest

- task_id: `20260923-home-capability-pages`
- objective: 基于 Build 45 深化首页，并实现“继续学 / 继续做 / 帮我清理 / 为你留意”五页交互；仅安装真机，不上传 TestFlight。
- changed_files:
  - `ios/AIPlatformApp/Views/Chat/ChatView.swift`
  - `ios/AIPlatformApp/Views/Chat/Components/ChatInputBar.swift`
  - `ios/AIPlatformApp/Views/Chat/Components/ChatMessageStreamView.swift`
  - `ios/AIPlatformApp/Assets.xcassets/home_learning_hero.imageset/*`
  - `ios/AIPlatformApp/Assets.xcassets/home_continue_work_art.imageset/*`
  - `ios/AIPlatformApp/Assets.xcassets/home_cleanup_art.imageset/*`
  - `ios/AIPlatformApp/Assets.xcassets/home_attention_botanical.imageset/*`
  - `ios/AIPlatformApp/Assets.xcassets/home_work_hero.imageset/*`
  - `ios/AIPlatformApp/Assets.xcassets/home_work_books.imageset/*`

## 开工前 Git 盘点

- status: `## main...source/main`（clean）
- branch: `main`
- HEAD: `5085e6585f0ae69c20a49747c3257568709fd852`（Build 45）
- remote:
  - `origin https://github.com/Johnie198946/Quantum.git`
  - `source https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/quantum-home-capability-build45`
- other_worktrees: 原仓库 detached worktree 含其他任务改动，本任务未触碰。

## 架构与复用

- 复用 `APIClient.fetchBookSubscriptions`、现有 `KnowledgeBookReaderView`、`SessionManager` 会话生命周期、`APIClient.fetchKnowledgeNotes` 和既有 Chat/PCM 执行链。
- 未新增重复 backend service、repository、状态容器、数据库或 PCM capability。
- 归档对话前保留明确确认；笔记合并、删除、覆盖未在预览页直接执行。

## 测试与校验

- `xcodebuild ... -sdk iphoneos ... build`: `BUILD SUCCEEDED`
- `PYTHONPATH=. python3 -m pytest -q tests/test_product_capabilities.py tests/test_ios_capability_matrix.py`: `35 passed`
- `git diff --check`: passed
- 空操作扫描（Chat 新页面范围）: 未发现 `Button {}` 或 `onToggleSubscription: {}`。
- “为你留意”已按独立参考页重构：专属说明头图、自绘分类胶囊、今天/稍后处理分组、原因条、卡片双操作、管理弹层、设置栏与底部提问入口。
- “继续做”已按参考页重构：项目头图、上次进度时间线、当前建议、三阶段流程、开始前确认与页面专属补充输入栏；所有操作复用现有 Chat/PCM 主链。
- “帮我清理”已按独立参考页重构：清理插画标题区、四类筛选、归档/合并/需确认三种专属卡片、差异预览、逐项选择确认条及页面专属输入栏。
- “归档确认”已按确认设计稿落成原生全屏页：复用现有清理候选与 `SessionManager.setLifecycle/switchTo`，不再把归档动作重新发送为 Markdown；包含植物便签/清理插画、逐项勾选、全选/全不选、依据展开、继续学习、稍后处理、逐项调整和固定底部确认按钮。
- “为你留意”再次按参考图校准：植物便签说明头、卡片比例、原因条、今日/稍后分组，以及珊瑚/蓝/深色主按钮层级。
- 真机测试 target 构建并启动成功；指定 XCTest 过滤器返回 `TEST SUCCEEDED`，但报告执行 0 个测试，因此不将其计为功能断言通过。
- 归档确认页模拟器入口验收：从“帮我清理 → 归档”成功进入；“查看依据”展开成功；“全不选”将计数更新为 0 并禁用确认按钮；图片裁切及底部安全区正常。
- 最新真机签名构建: `BUILD SUCCEEDED`
- 最新真机安装/启动: `com.ailab.AIPlatformApp` 已通过 CoreDevice 安装并启动；iPhone 镜像要求 Mac 登录密码，未进行真机画面点击验收。

## 交付状态

- status: `TESTED`
- branch: `codex/archive-confirmation-build45`
- commit_sha: 未授权/未执行
- github_remote_ref_sha: 未授权 push，未执行 `git ls-remote`
- server_before: 不适用；本任务未部署后端服务器
- server_after: 不适用；本任务未部署后端服务器
- health_check: 本地 iOS 无签名构建、真机签名构建、CoreDevice 安装与启动均通过
- functional_check: PCM 相关测试 35 项通过；归档确认页模拟器入口、依据展开、选择计数和按钮禁用逻辑通过；真机画面点击验收受 iPhone 镜像锁定限制
- rollback_point: Build 45 `5085e6585f0ae69c20a49747c3257568709fd852`；改动仅存在独立 worktree，可删除本 worktree 回退

## 风险与未完成项

- “继续做”的结构化项目数据在 Build 45 iOS 端没有公开 QWS DTO；确认后复用 Chat/PCM 主链执行，未伪造第二套项目接口。
- “建议合并 / 重复待办”只展示预览并进入确认流程，不直接写后端。
- 未 push、未部署服务器、未上传 TestFlight。
- 真机已安装并启动；如需录制真机点击证据，仍需用户解锁 iPhone 镜像，Codex 不会请求或代输 Mac 登录密码。
