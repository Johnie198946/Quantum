# Travel notes local implementation completion record

- task_id: travel-notes-20260927
- status: DEPLOYED
- branch: codex/travel-notes-20260927
- worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-notes-20260927
- head/local_commit: f8c7d064c959312e54fcb1dcaf3a08f5bbf19dfe（首轮已部署版本；后续修复见文末）
- remote_sha: origin refs/heads/main=f8c7d064c959312e54fcb1dcaf3a08f5bbf19dfe；git ls-remote 已核对
- server_before: 21250c7b8a5290abcf649b9279bbd91b9af1db88（并行发布完成后重新建立基线）
- server_after: f8c7d064c959312e54fcb1dcaf3a08f5bbf19dfe；/opt/releases/ai-lab-platform-f8c7d064c959.229Byr
- health_check: 更新器最终 /ready、Bridge、所有服务检查通过；独立公开 /health=ok/0.8.0；.deployed-sha 和 API 镜像 revision 一致。切换时 ready 五次 5 秒超时，随后恢复，未掩盖该时延。
- functional_check: 正式服务环境原生浏览器指定日期公交通过；真实 Bridge 研究前置空范围知识检索 20 秒超时，尚未完成生产全链路。不能标 VERIFIED。
- rollback_point: /opt/releases/ai-lab-platform-21250c7b8a52.rS7UdR；镜像、数据库备份 /opt/ai-lab-shared/rollbacks/chat-travel-pcm-f8c7d064c959；浏览器配置/包清单 /opt/ai-lab-shared/rollbacks/travel-browser-20260927
- manifest: ops/change-manifests/travel-notes-20260927-completion.md

## 目标与复用

更新旅行设计并开发通用澄清、附件上下文、Hermes 记忆入口、旅行工作流、逐日安排、实际进度、未来重规划、旧版本、设计地图、摄影参考与笔记回链。复用 Workflow/Hermes/私有 documents/知识编译/原生记忆/既有多租户边界。唯一新增产品模块为 travel_plan.py：旅行数据约束与历史冻结规则不能由通用文档渲染器替代；没有新增数据库、队列、选择器或沙箱。

## 开工盘点

完整 status/branch/HEAD/remote/worktree 记录在 [inventory](travel-notes-20260927-inventory.txt)。开始时任务工作树只有盘点文件；原 Quantum main 已有多任务改动，全部保留。用户当前要求的一任务一分支/Worktree 优先于仓库旧 main-only 规则。托管工具绑定 AI Lab、不能创建 Quantum 基线；工具失败后采用独立 Quantum git worktree。

## 变更文件

- `backend/api/chat.py`
- `backend/api/documents.py`
- `backend/api/workflows.py`
- `backend/contracts/product-capabilities/capabilities.yaml`
- `backend/services/document_sources.py`
- `backend/services/note_illustrations.py`
- `backend/services/workflow_executor.py`
- `backend/services/workflow_planner.py`
- `ios/AIPlatformApp/Models/UIModels.swift`
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformApp/Views/Chat/Cards/ClarifyCard.swift`
- `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
- `ios/AIPlatformApp/Views/Chat/NativeClientActionHost.swift`
- `ios/AIPlatformApp/Views/Chat/PlusMenuSheet.swift`
- `ios/AIPlatformApp/Views/Knowledge/KnowledgeView.swift`
- `ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
- `scripts/hermes_bridge_runtime/contracts.py`
- `scripts/hermes_bridge_runtime/workflow_artifacts.py`
- `scripts/hermes_bridge_runtime/workflow_runtime.py`
- `tests/test_document_presentation.py`
- `tests/test_note_illustrations.py`
- `backend/services/travel_plan.py`
- `tests/test_travel_plan.py`
- `docs/design/travel-notes-design-20260927.md`
- `ops/change-manifests/travel-notes-20260927-inventory.txt`

## 扩展验证（2026-09-27）

- 后端相关回归：263 passed, 1 skipped, 8 warnings，17.02 秒。命令范围见 receipts/backend-regression-expanded.txt；使用独立 SQLite 与 AI_LAB_HOME。
- 补充记忆测试：test_memory_capabilities.py，4 passed；验证最新偏好即时读取、未创建档案不读宿主、不同用户无混入。
- Office 预览跳过项在获准环境单独执行：1 passed。实际二进制 DOC/PPT 转换提取均通过。
- iOS WorkflowLifecycleDTOTests：182 tests, 0 failures；/tmp/travel-complete-ios3.xcresult。覆盖最新延误、交通起终点、返程、附件 DTO、原生 OCR 等。
- 真实模型结构生成：7.96 秒，校验通过；两轮真实模型重规划：36.58 秒，历史与个人手记保留，原生用户记忆注入。仅为模型节点样本，不是全链路或 p95。
- 日志位于 ops/acceptance/receipts/travel-notes-20260927/，包含 backend-regression-expanded、ios-expanded-tests、real-model-schema、real-model-revision、legacy-office、office-preview。

- 附件请求快照修改后重新构建与针对性 XCTest：1 passed，记录 attachment-retry-snapshot.txt。Python Ruff、compileall、git diff --check 通过。

## 新增复用范围

扩展原有普通聊天附件引用、原生记忆读取、Office 转换、笔记网络图归档与截图回退、旅行结构校验修复、用户延误和预约变更、路线起终点及返程。普通聊天请求固定发送时附件引用，重试不读取后来追加的附件；复用 InFlightRequest 并扩展 ChatStatusCards.swift。新增修改文件还包括 presentation_renderer.py、upload_text_extractor.py、agent_execution.py、memory.py、test_chat_stream_api.py、test_upload_text_extractor.py、test_memory_capabilities.py；没有新增服务或持久化通路。

## 未完成项与风险（历史记录，以文末当前结论为准）

当前 LOCAL_ONLY：局部测试通过，但用户要求的全部验收尚未完成，不能标为整体 TESTED。

- 用户已授权本机登录态只读验收及打开 Chrome 新窗口。新窗口已打开；重装扩展并重启 Codex 后，仍出现 30 秒超时和 nodeRepl.fetch request failed，连接尚未恢复；未读取收藏或社交账号资料，没有写入收藏、发帖或预约。
- 网络图归档/截图分支仅模拟测试；全流程 API→真实研究→审批→重规划→笔记、十轮实际交互、断网写入恢复、端到端 p50/p95 未完成。
- Office 内嵌图全面视觉理解尚未完成。地图是设计示意和位置球，不是道路/地形底图。
- 保存笔记为快照；主分支有其他任务的重叠改动，后续整合必须逐项处理，不可整文件覆盖。
- 未提交、未推送、未部署。commit SHA 不适用；GitHub remote/ref/SHA 和 ls-remote 未授权/未执行；server_before、server_after、health_check 不适用。rollback_point 为盘点基线，仅按本任务 diff 撤回，不动主工作区。


## 继续开发：修订恢复与离线读取

- 修复旅行修订幂等回执顺序：相同请求在后续重规划已经启动时仍能取回原回执；相同 request_id 的不同内容仍拒绝。
- iOS 旅行编辑与实际进度共用 submitTravelRevision，复用现有网络层的单次瞬态重试，保持请求字节和编号不变，保留取消与凭据代际检查。
- 扩展原有十轮 API 修订验证：每轮断线重试、过期版本冲突、个人原文保护、历史版本逐一回读以及同租户不同用户拒绝访问。此验证不含真实模型或真实 UI 十轮操作。
- 后端相关回归 264 passed, 1 skipped, 8 warnings，32.29 秒；跳过的 Office 预览此前已单独实测通过。
- 真实模拟器丢失响应测试通过：计划编辑与进度记录都只重发相同内容一次。
- 工作流旅行成果页复用 InboxFileManager 用户隔离私有缓存，缓存最近读取版本并验证内容 SHA-256；离线标示“上次保存”，禁止把缓存当最新云端数据修改。网络恢复后刷新；文件使用原有原子写入与完整文件保护。新增文件修改为 ios/AIPlatformApp/Services/InboxFileManager.swift。
- 离线读取缓存可能被系统清理，并不等于永久离线文档库；离线草稿写入与自动同步仍未完成。完整真实研究、模型、审批、笔记链路和端到端性能验收仍未完成。总体继续保持 LOCAL_ONLY。

- 最新 iOS 完整 WorkflowLifecycleDTOTests：Executed 184 tests, with 0 failures (0 unexpected) in 13.943 (13.992) seconds；日志 offline-recovery-ios.txt，xcresult /tmp/travel-offline-ios.xcresult。


## 继续开发：持久离线编辑与附件桥接修复

- 复用 InboxFileManager 的用户隔离、原子写入与文件保护，增加 Application Support 存放选项；旅行云端快照和待同步草稿采用此选项，注销清除当前用户文件。此前仅 Cache 的限制已被本次实现取代。
- 计划编辑和实际进度先本地持久化，保存 request_id、原始发生时间以及提交前的精确 payload。打开成果页、回到前台、现有网络层确认恢复或点击同步时依序恢复提交。
- 自动合并仅限云端未改变的目标事项；其他事项的云端更新保留。同事项冲突保留本机草稿，可查看云端、核对后重试首项或显式撤回待同步队列。核对重试使用新 request_id；后端历史冻结、版本校验仍有效。ISO8601 等价时区/小数格式规范化后再比较。
- 修复多附件 dispatch 组装成无来源 ID 的对象导致桥接拒绝：沿用每份原始 ID/版本/hash，以 source_documents 传入同一 WorkflowRunRequest，最多 20 份、总正文 80000 字符，保留单文档兼容。旅行行程节点也直接读取附件，避免关闭联网时研究快捷路径遗漏材料。
- 修复 Hermes 原生视觉截图回退：兼容 meta.screenshot_path 以及普通顶层 screenshot_path，两条格式均有回归。
- XCTest 完整组 185 tests, 0 failures，16.630 秒；/tmp/travel-conflict-ios.xcresult。后端 267 passed, 1 skipped, 8 warnings，19.68 秒；Office 预览跳过项此前单独实测通过。Ruff 和 git diff --check 通过。
- 真实公开图片下载、尺寸限制、JPEG 转换通过，0.66 秒；使用 python.org 公开测试图片验证机制，不作为旅行摄影资料。截图回退仍仅格式契约测试，未实测真实页面截图。
- 完整用户 UI 离线/重开/十轮操作、Office 内嵌图视觉理解、外部登录态和端到端性能仍未验收。真实桥接研究→审批→笔记测试正在单独执行，结果未出前不计通过。总体 LOCAL_ONLY。


## 真实工作流桥接验收

- 已通过真实 Bridge HTTP 启动、实际知识网关、Hermes 公开网页检索、审批回执及笔记生成。终态为 awaiting_review（等待成果复核），不是发布完成。
- 耗时 170.75 秒：研究 90.24 秒，行程 43.13 秒，笔记 36.58 秒。研究调用 9 次搜索，部分查询空结果/失败，网页提取后端不支持；最终生成 3 项安排、4 条来源，已核对最终 actions/stops 与批准稿完全一致。
- 证据：real-bridge-research-notebook.json、real-bridge-notebook.json。该测试不包含外层平台 API、真实 iOS 十轮操作、账号收藏、截图下载回退或 p50/p95，不得把单样本当作全部验收。


## 研究收敛与真实事件回放

- 首轮研究指令收敛为最多三次搜索、一次批量提取；工具明确不支持时不重复同一路径，摘要不能冒充已读正文，缺口留给后续补充。未新增检索服务。
- 同一真实桥接场景复测 108.28 秒，研究、行程、审批、笔记均通过。与此前 170.75 秒仅为两次样本观察，不是 p50/p95，也不证明来源覆盖相同；当前网页正文提取后端不支持，生成物仍带待核实事项。
- 将真实运行的节点事件保存为可回放验收材料，并经 project_event 写入平台数据库与文件。3 份成果经真实 API 回读，旅行 JSON 校验通过；同租户其他用户读取返回 404。26 项旅行测试通过（包含此跨层回放）。回放不等同于外层平台从启动到结束的实时端到端验收。
- 最新 iOS 完整 185 项测试通过（offline-pending-final-ios.txt，/tmp/travel-final-queue-ios.xcresult），包括禁止待同步草稿保存为已确认笔记所需的最终编译。Ruff、git diff --check 通过。
- 剩余：Office 内嵌图片完整理解、真实客户端十轮与断网/重开全流程、外层平台实时全链路、真实网页截图回退、登录态收藏/社交资料、端到端 p50/p95。没有提交、推送或部署，总体仍为 LOCAL_ONLY。


## 本轮验收进展（以上旧“未完成项”按本节更新）

- Office 图片：沿用 upload_text_extractor → document_sources → 私有知识笔记。复用已有内部鉴权与 Hermes owner sandbox，在已有 Bridge 注册图片分析入口；主模型原生图像输入，工具禁用。最多 16 张不同内嵌图、25 MB 解压后图片，两个并发分析，180 秒批次超时，成功结果按用户和图像 SHA 缓存。没有新服务或依赖。图像识别失败则上传回执标记失败，保留原件，不能冒充已编译成功。
- 真实 DOCX/PPTX/DOC/PPT 四格式图片预订字段识别、私有笔记入库、原件字节回读全部通过。16 张不同图片第一次 38.01 秒、重复上传 0.68 秒，全部 16 个字段命中。模型识别不是事实核验；不支持的图像编码、超过 16 张或提取上限明确失败。证据 office-all-vision.txt、office-batch-16.txt 与可重复运行 harness。
- iOS：真实客户端十轮改行程，每次后端回读匹配；重启后显示第十轮，旧版本按钮包含十轮理由。61.463 秒的独立测试完成全站 503 模拟断网、离线修改、强制退出、重开读取草稿、恢复网络同步、再次重开回读。界面截图 client-offline-relaunch.png、client-ten-edits.png；/tmp/travel-real-client-ui5.xcresult。
- 验收发现并补齐离线入口：复用 InboxFileManager 的 Application Support 存储缓存工作流列表、详情、执行快照和成果索引；不缓存写操作。仅网络/502/503/504 回退，切换凭据或缓存用户中止，403/404 使该快照失效。保留原有会话过滤和行程正文哈希检查。
- 验收发现并修复新建任务“添加资料”空按钮，复用 APIClient.uploadDocument(at:)、原件保存与入库；澄清和原生上传也调用该入口。附件上传复用已有 200 秒长请求会话，避免普通 15 秒超时提前终止视觉解析。
- 验收发现首次客户端任务创建缺少会话登记（register_client_session 没有调用方）。在共享 _create_workflow 入口复用原有登记方法，仍拒绝同租户其他用户认领，继承租户/用户校验。旅行及文档任务共用修复，未新增绑定表或放宽权限检查。
- 最新后端交叉回归：204 passed、1 skipped、6 warnings、24.91 秒，准确命令见 backend-final-regression.txt；此前 Office 分支增加后较宽运行 270 passed、1 skipped。跳过项为此前已独立实测通过的 Office 预览。iOS 完整回归 186 passed；其后上传超时与缓存撤权两个针对性测试各通过。
- 平台真实 HTTP 澄清→规划→批准→启动→dispatch→真实 Hermes/公开搜索→行程阶段批准→持久笔记回读，五次独立串行均成功。p50 133.06 秒，最近秩 p95 249.61 秒；只有 5 个样本，不能当作生产 SLO。慢样本行程节点 141.61 秒。公开检索后端为 DDGS，正文提取不支持，生成内容仍包含待核实项，不能称来源全部核实。详细分段 platform-performance.json。
- 本机真实 HTTP 20 轮读取及版本保存：读取 p50 58.72 ms、p95 95.82 ms；保存 p50 32.41 ms、p95 122.87 ms，全部回读成功。不是公网或真机延迟。见 edit-performance.json。
- 当前仍 LOCAL_ONLY：完整客户端新建到真实模型成果的自动化验收进行中；Chrome 只读登录态再次 30 秒后报 nodeRepl.fetch request failed，未读取账号收藏/社交内容。真实网页截图回退尚无成功记录。未授权提交、push 或部署。
- 本轮新增修改文件：scripts/hermes_bridge.py、scripts/hermes_bridge_runtime/endpoints.py、backend/services/workflow_session_scope.py、ios/AIPlatformAppUITests/CleanupMergeUITests.swift；其他修改扩展既有本任务文件。receipt harness 只用隔离临时库及合成测试身份。

## 客户端最终确认修复

- 澄清选项复用消息 ID 与选项位置/文本作为稳定身份，防止重绘导致选中状态失效；不同消息或已变更选项不会误提交旧选择。复用 UIModels 和原工作流消息，无新增状态容器。
- 修复最终阶段审批仍筛选 DOCX 的遗漏：旅行采用现有 travel_plan_v2 成果，并沿用既有 review-stage 批准。最终稿继续调整则复用已有 request-revision，带成果 ID/hash 与历史基线保护。
- 新增模型失败保护：Hermes failed/error/completed=false 不可被当作研究正文存储。实际错误由误用系统 SDK 1.14.1 触发，已恢复仓库锁定 2.24.0 环境；此错误样本不计入此前五个有效性能样本。README 和模型验收脚本显式检查运行环境。
- iOS 完整回归 188 项、零失败、16.915 秒（full7 中单元测试部分）；Provider 失败与图片处理 5 项通过、7.75 秒。真实客户端全流程继续单独运行；full7 的 UI 点击因确认按钮部分在底栏后方，误点附件选择器，此次不计通过。UI 自动化现在先滚动使确认按钮完全可见并断言已选择，再点击。

- 真实配图平台 API → 既有 durable worker → 公开图片下载 → 私有 JPEG 回读已通过，1.78 秒，字节哈希一致；同租户另一用户读取 404。使用 Python 官方 logo 作为传输测试素材，不算旅行摄影资料。见 image-api.json / image-api-harness.py。
- 笔记保存、退出、重开后在“阅读”页搜索并打开通过（48.516 秒），截图 client-saved-note-relaunch.png。该次截图的配图连接失败来自隔离验收环境未配置配图地址和 worker；随后已补齐同一现有服务、独立运行库与内部密钥，配图 API 已单独验证。不是通过改写产品路由绕开服务。
- 最后后端回归 205 passed、1 skipped、6 warnings、96.50 秒；当时同时运行模拟器与模型，不和前次耗时作性能对比。

## 最终修改文件核对

- `backend/api/chat.py`
- `backend/api/documents.py`
- `backend/api/workflows.py`
- `backend/contracts/product-capabilities/capabilities.yaml`
- `backend/services/document_sources.py`
- `backend/services/note_illustrations.py`
- `backend/services/presentation_renderer.py`
- `backend/services/upload_text_extractor.py`
- `backend/services/workflow_executor.py`
- `backend/services/workflow_planner.py`
- `backend/services/workflow_session_scope.py`
- `ios/AIPlatformApp/Models/UIModels.swift`
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformApp/Services/InboxFileManager.swift`
- `ios/AIPlatformApp/Views/Chat/Cards/ClarifyCard.swift`
- `ios/AIPlatformApp/Views/Chat/Components/ChatStatusCards.swift`
- `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
- `ios/AIPlatformApp/Views/Chat/NativeClientActionHost.swift`
- `ios/AIPlatformApp/Views/Chat/PlusMenuSheet.swift`
- `ios/AIPlatformApp/Views/Knowledge/KnowledgeView.swift`
- `ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
- `ios/AIPlatformAppUITests/CleanupMergeUITests.swift`
- `scripts/hermes_bridge.py`
- `scripts/hermes_bridge_runtime/agent_execution.py`
- `scripts/hermes_bridge_runtime/contracts.py`
- `scripts/hermes_bridge_runtime/endpoints.py`
- `scripts/hermes_bridge_runtime/memory.py`
- `scripts/hermes_bridge_runtime/workflow_artifacts.py`
- `scripts/hermes_bridge_runtime/workflow_runtime.py`
- `tests/test_chat_stream_api.py`
- `tests/test_document_presentation.py`
- `tests/test_memory_capabilities.py`
- `tests/test_note_illustrations.py`
- `tests/test_upload_text_extractor.py`

另有本任务新增的 `backend/services/travel_plan.py`、`tests/test_travel_plan.py`、设计文档、盘点文件与本目录验收材料；未混入其他任务变更。

## 当前验收结论

- **LOCAL_ONLY**：本地功能与主要链路已通过，但外部登录态与真实页面截图回退仍未通过；不能把整项标为 TESTED，更未上线。
- Office DOCX/PPTX/DOC/PPT 内嵌图片理解、私有原件与编译结果回读通过；16 张不同图片批次 38.01 秒，缓存重传 0.68 秒。超过 16 张不同图片、25 MB 解压图片或不支持编码明确失败，保留原件；不承诺无上限处理。
- 最终实际 iOS 客户端 + 本机平台 + 真实 Hermes 模型的完整创建链路，以及保存后冷启动搜索回读，两项 XCTest 均通过，合计 236.771 秒。三轮澄清、需求确认、方案批准、行程阶段批准、最终采用均通过 UI 点击；后台终态 completed。使用合成测试身份，未验真实登录流程。日志 client-full-final-results.txt，xcresult /tmp/travel-real-client-full12.xcresult。
- 客户端十轮修订逐轮后台回读、旧版本、断网草稿、强制退出、离线重开、恢复网络同步此前均通过。iOS 188 项回归零失败；最终 Python 205 passed、1 skipped（Office 预览已独立实测）。Ruff 与 git diff --check 通过。
- 实际旅行笔记自动配图产生两张 Seedream 2048×1152 JPEG，已核验文件与 SHA。公开图片完整 API/worker 归档链路 1.78 秒、跨用户读取 404。网页截图项失败，保留 failed_indices，未冒充成功；详见 client-illustration-results.json。图片下载测试采用公开测试 logo，不算旅行摄影素材。
- 性能验收范围为本机隔离环境：五个真实平台串行样本 p50 133.06 秒、p95 249.61 秒；20 轮读取 p50/p95 58.72/95.82 ms，保存 32.41/122.87 ms；另有 Office 四格式、16 图冷/热批次和真实客户端耗时。不是生产负载、广域网、物理手机或登录态站点的性能承诺；没有以五个样本宣称生产 SLO。
- 外部阻塞：Chrome 扩展已安装、用户已授权只读，但当前 tabs.list 仍在约 30 秒后 nodeRepl.fetch request failed。工具执行本身正常。尚未读取收藏/社交资料，未验证真实登录态导入；不再要求重复安装。真实网页截图回退也没有成功证据。公开搜索正文提取后端不支持，未核实内容保留待确认，不能声称资料事实全部核实。
- 未提交、未 push、未部署；remote_sha 未核验，server_before/server_after/health_check 不适用。回滚只针对本任务工作树的 diff，基线 c1c5788c7a94a25f8f4cb6ed81c50614b4feeba1，不覆盖主工作区或其他任务。


## 云端 Google Maps 更正与实测（2026-09-27，本节覆盖此前本机 Chrome 阻塞判断）

- task_id: travel-notes-20260927
- status: LOCAL_ONLY（本轮代码相关测试通过；旅行整体尚未在生产客户端完成验收）
- branch: codex/travel-notes-20260927
- worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-notes-20260927
- head: c1c5788c7a94a25f8f4cb6ed81c50614b4feeba1
- local_commit: 未提交，用户未要求提交
- remote_sha: 未核验；未授权 push
- server_before: a8cc2954e13a40732fc36444df6beaf81f05b80b，/opt/releases/ai-lab-platform-a8cc2954e13a.swjper
- server_after: 0704ddf5a54bf9739e506652e7b60fa2f22f564c，/opt/releases/ai-lab-platform-0704ddf5a54b.IXeolO。验收期间外部流程更新了线上版本，本任务未部署、未重启服务、未执行 apt install；不能将该新版本归功于本任务
- health_check: 云服务器访问 https://t-react.com/health 返回 status=ok/version=0.8.0；Bridge/Worker active
- functional_check: 独立云端 Hermes 浏览器读到地点地址、当下及指定日期公交线路；官网截图归档函数成功。不是线上 App→API→Worker 完整闭环
- rollback_point: 本任务没有生产切换或已建立的部署回滚点；后续发布必须重新盘点最新 release 并建立回滚点。本地仍以本任务基线及可审查 diff 回退
- manifest: ops/change-manifests/travel-notes-20260927-completion.md

### 原因与复用修复

原先把 Codex 本机 Chrome 连接当成云端旅行功能前提是错误验收方向。既有架构明确 Hermes 集中托管。云端直连 Google 超时，但服务账号已有代理请求 Maps HTTP 200（1.59 秒）；Node 在 Hermes 管理目录，默认 PATH 未包含，agent-browser/Chrome 及 12 个直接动态库缺失。agent-browser 0.26.0 安装 Chrome for Testing，Hermes 的旧自动检查只认识 Playwright 缓存，需要显式 executable。

复用现有主路径，未新增地图服务、数据库、MCP 或浏览器框架：
- scripts/hermes_bridge.py：云模式下统一共享二进制 PATH、明确 Chrome 执行路径、可写 socket/cache 和现有服务代理；Worker 通过同一 composition root 生效；桌面模式不改变。
- scripts/configure_hermes_web_extract.py：增量 --prepare-browser，固定 agent-browser 0.26.0、禁 npm 生命周期脚本、子进程剥除模型凭据、有限超时、实际 Chrome --version 验证后原子链接；必须以 Hermes Home 的所有者执行。Chrome stable 动态版本未完全锁定，发布时记录版本和 SHA。
- scripts/install_agency_hermes.sh：Linux 安装复用上述预置步骤；Mac 原路径不变。
- backend/services/travel_plan.py：研究节点明确服务器 Maps 地点/公交 URL、实际页面取证、指定日期/时区及失败处理；私人收藏使用可访问分享清单或用户资料。
- tests/test_travel_plan.py、tests/test_agency_integration.py：云/桌面隔离、显式配置优先、代理和写目录、固定安装与失败不替换旧链接。
- ops/runbooks/hermes-bridge-network.md：记录服务器安装和验收步骤、系统库清单与正式发布边界。

### 云端实证

使用 deploy 账号的既有可信运维连接；以 quantumn-hermes 运行独立 /tmp/travel-cloud-browser-r3pqziwo 环境。npm/Chrome 与 Ubuntu 动态库仅下载解包到该目录，未安装到系统、不加载个人登录、不改线上配置。每次浏览器测试均调用 cleanup_browser；目录保留供后续复现。

- agent-browser 0.26.0；Chrome 154.0.8037.57；库取自服务器已配置的 Ubuntu 24.04 官方镜像，未运行包脚本。
- 东京站检索 + snapshot 16.51 秒；公交方向查询 + snapshot 8.66 秒。读到东京站、新宿站的实际地址，中央线约14分钟和¥260，以及丸之内线备选。不是性能 SLO。
- 页面操作 Leave now → Depart at → next day → 09:00，明确显示 Mon, Sep 28 与中央线 09:03 AM–09:17 AM，¥260；另有09:08–09:21等备选。
- 浏览器一次 ERR_CONNECTION_CLOSED，测试有界重试恢复；不能宣称无失败率。
- 原样执行本任务 archive_web_reference + _normalized_image，对 https://www.hitou.or.jp/ 输出 page-screenshot JPEG 213822 bytes，SHA256 005f69cee0b6a34d8bded0e5a453a3978ac32ef848a5bc17f5d4d9f1338bfc9d，16.15秒。临时环境无视觉模型凭据，辅助分析返回错误，但已捕获的图片路径和归档字节有效；不宣称视觉模型分析成功。
- Google Maps 的 screenshot 归档尝试因本地 DNS 返回2001::1而被既有 SSRF 检查拒绝；未豁免域名、未关闭检查。浏览器地点/交通查询成功与截图下载的 DNS 安全限制分别记录。
- 证据：ops/acceptance/receipts/travel-notes-20260927/cloud-maps-result.txt、cloud-maps-date-result.txt、cloud-reference-result.txt、cloud-reference.jpg、cloud-server-version.json；附对应隔离探针。
- 最终相关回归：69 passed / 6 existing warnings / 5.23秒；Ruff、bash -n、git diff --check 通过。没有重复宣称先前测试涵盖生产发布。

### 剩余

正式运行环境仍需按获准发布安装系统库、预置浏览器、采用代码并验证线上真实客户端流程；尚未获得提交、push、部署授权。云端社交登录资料、私人收藏导入和生产性能/SLO仍未完整验收。本机Chrome扩展恢复不再是云端公共查询的依赖。

截图人工回看：主要页面、温泉图片及地图可见；临时环境缺 CJK 字体，部分文字为缺字符号，外链图片也有未加载项。截图字节归档通过不等于最终配图视觉质量通过，正式安装步骤补列 fonts-noto-cjk，发布后需要重验。

## 发布授权与整合（2026-09-27）

用户回复“授权”，明确授权本任务提交、推送与服务器部署。发布基线 origin/main=0704ddf5a54bf9739e506652e7b60fa2f22f564c；先在本任务独立分支整合，保留他人改动，测试通过后才推送和切换。先前“未授权”字段为历史状态，本节取代其授权判断。

## 发布前整合验收

旅行功能提交 2930bde8，合并最新主分支提交 56a10118；主分支全部变更保留，冲突仅为两组追加测试，均保留。整合后后端 237 passed、产品契约 36 passed、iOS WorkflowLifecycleDTOTests 194 passed，0 failures。日志 release-*.txt。服务器发布前仍为 0704ddf5a54bf9739e506652e7b60fa2f22f564c；浏览器依赖安装前的包清单和配置已备份到 /opt/ai-lab-shared/rollbacks/travel-browser-20260927。

## 正式云端部署与前置检索缺陷

- 用户明确授权提交、推送、部署，并进一步授权与笔记验收及出版两个任务协调。并行21250发布期间预检自动退出，无覆盖；确认其发布锁释放后，以21250为before继续。收到暂缓消息时容器切换已启动，由更新器完整结束，随后停止进一步版本切换并同步两任务。
- 从GitHub codeload精确SHA下载，源码归档SHA256=5feeca107a7b77c5423b7cba2bd298e44b4f42d894159984eda48aab299efd84。包锁与父镜像匹配、pip check、候选导入、运行契约检查通过。
- agent-browser=0.26.0；Chrome for Testing=154.0.8037.57；Chrome SHA256=e528b77a8b250c48a5bbd7aeeabbc2813940c0a2fe39b1b11fbaf1f01fb04f18。系统库40个新装、0升级0删除，Noto Sans CJK JP生效。调用现有prepare_browser，不修改provider配置或个人浏览器。
- 指定日期查询：正式环境9月28日09:00条件，实际页面显示中央线09:03–09:17、14分钟、¥260，dated_route_verified=True。是服务账号的独立验收进程，尚不能代替正式Bridge完整研究流程。
- Bridge生产研究 wfr_cloud_maps_6fa3ec745271 21.53秒失败，未执行浏览器。直接空知识范围网关请求200、27.0秒，超过已有20秒超时。最小修复在现有Workflow入口：空requested_scope不发起知识网关搜索；非空范围与联网权限保持。63项测试通过（含空/非空×联网/离线四组合），未部署此修复，等待共享窗口。
- 今晚publication-6d65e4fff6f4ae7734d1585c3a05a80a只读验证：唯一staged，release_at=2026-09-27T12:00:00+00:00，actual_release_at=null，正文/plan SHA=076cbb867c99609ea8ff09322ffcdf5f391990a6df7960c7f708f6776d5c5c9f，3图计划保持；没有改变cron/额度账本。
