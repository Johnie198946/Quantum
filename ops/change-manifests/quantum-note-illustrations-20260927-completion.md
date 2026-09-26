# Quantum 笔记 UI、旅行融合与智能配图交付记录

- task_id: quantum-note-illustrations-20260927
- status: TESTED
- branch: main
- worktree: /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
- head/local_commit: 9fbc4e0be46714c093bde3336040cfc9e1e69ca3；本任务未提交
- remote_sha: 未执行 git ls-remote；未授权／未执行 push，不宣称远端包含本任务
- server_before: 未授权／未执行部署检查
- server_after: 未部署
- health_check: 服务器检查不适用，未部署；本地编译与相关测试通过
- functional_check: 后端 45 项、iOS 36 项不同单元测试、4 条 UI 流程通过；本机真实 Seedream 生图通过；生产账号完整端到端未执行
- rollback_point: 开工 HEAD 9fbc4e0be46714c093bde3336040cfc9e1e69ca3 + 下列原始盘点／基线 hash／本任务差异归档；无服务器回滚点（未部署）
- manifest: ops/change-manifests/quantum-note-illustrations-20260927-completion.md
- remaining_risks: 生产 Bridge/provider、正式账号联调及签名真机尚未验证；部署需另行授权；具体边界见下文

## 授权与任务归属

用户确认以当前 main 为基线；最新“综合一下，帮我完成我所有需求的开发”授权实现此前讨论的笔记图片权限、私有生成媒体与旅行可选字段。当前 canonical repo 的 AGENTS.md 要求仅 main，沿用已协调的 main 工作区。

用户未授权提交、push 或部署。本次没有修改 Hermes 配置或密钥、没有安装真机包。清理差异任务与本任务同时存在；已协调文件归属，未操作其 project.yml、project.pbxproj、AIPlatformApp.swift、UIModels.swift、清理组件／后端／测试／manifest。既有 AGENTS.md 及其他任务文档保留。

## 实现范围

1. 保留前两轮已验收的笔记首页、编辑／阅读、搜索、标签、废纸篓和大字号改造；本轮补充格式菜单中的提示块、卡片、代码块入口，复用图片、高亮与图表渲染。块插入保证段落分隔并保留选中内容。
2. 手动新建／切换旅行版式；保留专属概览、行程、地点和地图，编辑游记不破坏 JSON 与未知字段。真实数据不再回退京都示例；修正封面横向溢出、重复标题／操作和代码围栏被清理的问题。
3. 普通编辑点击完成、聊天草稿保存、旅行成果保存进入同一配图入口。自动落盘不生图；默认自动配图可关闭，每次 0–3 张。
4. 段落光标／旅行卡片指定位置，输入要求、生成预览、插入；状态恢复、停止、重试、成功结果复用、撤销与正文冲突保护。
5. 私有 JPEG/hash 引用和带认证下载，账户隔离、请求幂等、服务端 owner 校验及重开恢复。没有开放全局图片工具，没有第二条聊天运行时。

## 复用与新增理由

复用 KnowledgeNoteStore、APIClient 下载／认证与笔记同步队列、knowledge_sync 命名空间、DurableChatRunStore／worker、现有 Hermes image provider 和 html_illustration 段落评分。新增 note_illustrations 服务／Bridge 路由是笔记专用生成契约与私有资产所必需；未新增依赖、数据库或通用平台。

## 变更文件（不含其他任务）

- `backend/api/knowledge_sync.py`
- `backend/services/note_illustrations.py`
- `scripts/chat_run_store.py`
- `scripts/chat_run_worker.py`
- `scripts/hermes_bridge.py`
- `scripts/hermes_bridge_runtime/note_illustrations.py`
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformApp/Services/KnowledgeNoteStore.swift`
- `ios/AIPlatformApp/Views/Knowledge/KnowledgeView.swift`
- `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
- `ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift`
- `ios/AIPlatformAppTests/KnowledgeNoteStoreTests.swift`
- `ios/AIPlatformAppUITests/ProductionBookshelfUITests.swift`
- `tests/test_note_illustrations.py`
- `docs/quantum-note-illustrations-design-20260927.md`
- 本 manifest；前两轮 manifest 保留原记录。

## 开工 Git 盘点

```text
pwd -P
/Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0

git status --short --branch
## main...origin/main
 M AGENTS.md
 M ios/AIPlatformApp/Networking/APIClient.swift
 M ios/AIPlatformApp/Services/KnowledgeNoteStore.swift
 M ios/AIPlatformApp/Views/Knowledge/KnowledgeView.swift
 M ios/AIPlatformAppTests/KnowledgeNoteStoreTests.swift
 M ios/AIPlatformAppUITests/ProductionBookshelfUITests.swift
 M ops/change-manifests/cleanup-exercise-testflight-20260927-completion.md
?? docs/quantum-note-illustrations-design-20260927.md
?? ops/change-manifests/quantum-2.0-hermes-gate-i0-20260909-completion.md
?? ops/change-manifests/quantum-note-illustrations-20260927-completion.md
?? ops/change-manifests/quantum-notes-ux-20260927-completion.md
?? ops/change-manifests/quantum-notes-youth-ui-20260927-completion.md

git branch --show-current
main

git rev-parse HEAD
9fbc4e0be46714c093bde3336040cfc9e1e69ca3

git remote -v
origin	https://github.com/Johnie198946/Quantum.git (fetch)
origin	https://github.com/Johnie198946/Quantum.git (push)
source	https://github.com/Johnie198946/ai-lab-platform.git (fetch)
source	https://github.com/Johnie198946/ai-lab-platform.git (push)

git worktree list --porcelain
worktree /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
HEAD 9fbc4e0be46714c093bde3336040cfc9e1e69ca3
branch refs/heads/main
```

开工已 fetch origin main 并确认 HEAD 与 origin/main 一致。原始记录与基线 hash：`/Users/dengzhaoyu/.codex/visualizations/2026/09/26/01a0de92-056a-7a33-ad69-b8c03694b826/quantum-notes-all/inventory.txt`、`baseline.json`。最终 HEAD 未变化；工作区仍有已协调的其他任务改动，禁止整体还原或整体暂存。

## 验证证据

- `python3 -m pytest tests/test_note_illustrations.py tests/test_chat_run_store.py tests/test_chat_run_worker.py tests/test_knowledge_sync_api.py -q`：45 passed，6 条既有弃用警告，日志 `backend-verified.log`。
- 独立 iPhone 16e / iOS 26.1 模拟器 `D9C87EC1-3020-4F98-A3F2-4E92F8BBE286`，Xcode `CODE_SIGNING_ALLOWED=NO`，未使用真机。
- `verified.xcresult`：29 项 KnowledgeNoteStore + 6 项 NoteIllustration + 4 条 ProductionBookshelf UI 通过。
- 最后仅对旅行 JSON 解析修正增量复测 `travel-data.xcresult`：7 项 NoteIllustration + 1 条旅行 UI 通过；合计 36 项不同单元测试、4 条不同 UI 流程。
- UI 覆盖创建／编辑／搜索／恢复、最大辅助字号首页与书架分隔、富文本提示块与配图面板、手动旅行创建及横向边界。截图人工检查旅行与提示块修复。
- 真实 provider：`volcengine-seedream`，model `doubao-seedream-5-0-pro-260628`；输出 2048×1152 JPEG、492295 bytes，SHA256 `384f258fe1ede15b34160c6c1eeebed883c9d94d006e0745e6f35890c5c9d038`。人工检查校园夜读内容与统一清新风格；保留 provider 水印。
- `git diff --check` 通过。
- 测试结果目录：`/private/tmp/quantum-notes-all-20260927`；稳定截图、日志、真实图片和源码 hash／差异：`/Users/dengzhaoyu/.codex/visualizations/2026/09/26/01a0de92-056a-7a33-ad69-b8c03694b826/quantum-notes-all`。

## 边界与剩余风险

- 未部署，当前线上 App／后端不会自动拥有这些改动。正式环境需核验 Bridge 地址、内部认证、持久任务 worker 和已配置 provider，再做真实账号端到端验证。
- 自动选位为现有评分启发式，并非额外语义规划模型；全文上限 48,000 字符，超过会提示拆分。
- 停止阻止后续生成和结果应用；已经发送至外部 provider 的单次请求不保证取消计费。
- 本次新增的是生成插图的私有媒体下载，未补齐任意相册图片的跨设备二进制上传同步。
- 生成媒体与既有任务库应一起备份；未增加自动清理，避免破坏已保存笔记引用。
- 模拟器 UI 与后端契约／worker 和本机真实 provider 分别验证；不将它们表述为生产账号或真机全链路验收。

## 回滚说明

未提交／部署，不存在本任务服务器版本。恢复时按 `notes-task.patch` 审查并逆向移除本任务差异，保留前置笔记工作和其他任务改动；不得整体还原共享文件或使用 reset --hard。开工基线文件副本位于 `/private/tmp/quantum-notes-all-20260927/ios`。已存用户笔记为向后兼容的 Markdown／可选旅行字段，无强制数据迁移。
