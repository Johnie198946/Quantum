# Quantum 笔记 Chat / PCM 接入验收

- task_id: quantum-notes-pcm-20260927
- status: TESTED
- branch: main
- worktree: /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
- head/local_commit: b74a528886d399615d4dedefc7aeae766c49c09e；此为并行清理任务提交，本任务未提交
- remote_sha: 本任务未执行 git ls-remote；没有 push 授权，不宣称远端包含本任务
- server_before: 未执行；未授权部署
- server_after: 未部署
- health_check: 不适用，未部署；本地编译和定向测试见下文
- functional_check: 后端 64 passed；iOS 41 项不同单元测试与 2 条 UI 流程已通过；最终按钮配色复测通过
- rollback_point: 开工 HEAD 9fbc4e0be46714c093bde3336040cfc9e1e69ca3、基线文件和 diff 归档；没有服务器回滚点
- manifest: ops/change-manifests/quantum-notes-pcm-20260927-completion.md
- remaining_risks: 正式账号模型自主路由／线上 Bridge 与新客户端组合未端到端验证；QWS 未协商新协议时明确拒绝写入；自动配图偏好按当前设备保存

## 范围与复用

接续 `quantum-note-illustrations-20260927-completion.md` 的笔记 UI、旅行版式、格式菜单与自动／手动配图；本次补齐当前 Chat 主路径与 PCM，不重复建立笔记或生图执行系统。

1. 复用 `knowledge.note.create/update`，增补标题、标签、普通／旅行版式、自动配图开关；明确完整正文、富文本块语法与保留旅行内容的契约。
2. 新增 6 个必须可独立发现、校验和授权的 PCM 操作：配图生成、状态、停止、插入、撤销、配置。重试使用原生成契约 `retry_run_id`，复用成功资产。没有新增通用图片工具。
3. 复用 `note_capability_step → knowledge_action_propose → signed knowledge_action_draft → KnowledgeActionExecutor → KnowledgeNoteStore`。当前 QCP 保存完成后统一排入自动配图；旧草稿保存入口保留。
4. 复用持久化配图 job，Chat 结果卡展示实际状态／图片，支持预览、插入、停止、失败重试、撤销。同一批结果不建立另一套 Chat 状态。
5. 写入要求本人笔记快照、原版本 hash、单一配图步骤及确认；原版本过期／未保存编辑／同步期间变更阻止生图。回执重放不重复排队；撤销只移除本批图片，保留后写正文。
6. `note_illustration_v1` 与 `qcp-ios-notes@1` 协商新增字段；旧客户端不能静默忽略后执行。服务端状态只说明生成状态，不虚报设备已插入。
7. 不猜测“这篇笔记”的跨页全局状态：明确 note_id／搜索定位；指代不清沿用搜索或澄清。未新增跨页状态容器。

## 授权、盘点与并行变更

用户授权完成笔记改造与 Chat / PCM 接入，未授权本任务 commit、push、部署。canonical 仓库 AGENTS.md 要求 main；已协调并行清理任务的共享文件 hunks。未暂存或提交任何文件。

开工盘点完整记录：`/private/tmp/quantum-notes-pcm-20260927/inventory.txt`，已复制到下方持久证据目录，涵盖 status、branch、HEAD、remote、worktree。初始 main HEAD 为 9fbc4e0be46714c093bde3336040cfc9e1e69ca3，已存在前轮笔记和其他任务改动。

并行清理任务协调暂停后，保留所有 dirty 文件并 fast-forward 至 ed673c0cbceb239693db3864fe3db2f3bc276866，再仅提交其自己的清理 hunks 至 b74a528886d399615d4dedefc7aeae766c49c09e。本任务新字段、学习新字段和各自契约已联合核对；这两个提交不是本任务交付。

remote 盘点：origin=https://github.com/Johnie198946/Quantum.git；source=https://github.com/Johnie198946/ai-lab-platform.git。唯一当前 worktree 为 canonical 路径，refs/heads/main。最终详细 status 见证据 `current-inventory.txt`。其他任务的 AGENTS、发布文档、清理、学习与网络 transport 改动未覆盖。

## 本次变更文件

- 后端：`backend/api/chat.py`、`backend/api/knowledge_actions.py`、`backend/capability_handlers.py`、`backend/services/{capability_gateway,capability_catalog,knowledge_action_capability}.py`。
- PCM：`backend/contracts/product-capabilities/{note_illustrations,capabilities,bindings,manifest,ios-scope}.yaml`；生成手册／coverage 与 iOS matrix／coverage。
- Bridge：`scripts/hermes_bridge.py`、`scripts/hermes_bridge_runtime/{knowledge,note_illustrations}.py`。
- iOS：`Models/UIModels.swift` 中 KnowledgeActionStep；`Networking/APIClient.swift` 新字段解析和协议协商；`Services/KnowledgeNoteStore.swift`；`Views/Chat/Components/ChatStatusCards.swift` 完成卡／独立配图状态／DEBUG 验收入口；`Views/Knowledge/KnowledgeView.swift` 复用图片视图与 DEBUG 入口。
- 测试：`tests/test_note_illustration_capabilities.py`、`ios/AIPlatformAppTests/KnowledgeNoteStoreTests.swift`、`ios/AIPlatformAppUITests/ProductionBookshelfUITests.swift`。
- 本 manifest。前轮 UI 和配图生成器变更详见前轮 manifest，不混记为本次新增。

## 验证

- 后端：`python3 -m pytest tests/test_note_illustration_capabilities.py tests/test_note_illustrations.py tests/test_product_capabilities.py tests/test_capability_gateway.py tests/test_client_action_capabilities.py tests/test_ios_capability_matrix.py -q`：64 passed，6 个既有 Pydantic 废弃警告。
- iOS：独立 iPhone 16e / iOS 26.1 模拟器 D9C87EC1-3020-4F98-A3F2-4E92F8BBE286；KnowledgeNoteStoreTests 29 项、NoteIllustrationTests 最终 12 项，共 41 项不同单元测试通过。
- UI：`testChatIllustrationPreviewInsertAndUndoPreserveOriginalNote`、`testTravelNoteKeepsItsLayoutWithoutExampleData` 通过。截图已检查，保留真实旅行内容，未回退京都示例；配图预览可插入／撤销。
- `generate_product_capability_manual.py --check`、`generate_ios_capability_matrix.py --check` 通过；全目录矩阵 partial 包含其他能力，不虚报本轮生产验证完成。
- `git diff --check` 通过。
- UI fixture 使用包内图片，只验证显示和插入／撤销，没有付费生图。真实 Seedream 生图复用前轮已通过证据（见前轮 manifest）；本轮未重复付费调用。
- UIKit 在旅行 UI 测试记录一条 `_UIReparentingView` warning，测试通过且截图无布局损坏；非新增失败。
- 修复过两次测试编译问题（fixture 参数、重载方法引用），最终结果以成功的 xcresult 为准。

## 证据与回滚

持久证据目录：`/Users/dengzhaoyu/.codex/visualizations/2026/09/26/01a0de92-056a-7a33-ad69-b8c03694b826/quantum-notes-pcm/`。

包括开工／当前 Git 盘点、基线与最终 source SHA-256、后端／iOS 测试日志、截图、review.patch 和新增文件。`review.patch` 对比并行清理提交并包含此前授权的笔记工作，只用于审查，不得整包覆盖共享 main。结果包在 `/private/tmp/quantum-notes-pcm-20260927/`。

回滚须按本任务字段／方法／独立契约逐 hunk 撤销并重生成目录；不要还原共享文件或 reset main，不得丢失其他任务改动。未部署，无服务器回滚操作。
