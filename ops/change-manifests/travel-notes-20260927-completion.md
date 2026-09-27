# Travel notes implementation and cloud release record

- task_id: travel-notes-20260927
- status: DEPLOYED（共同后端b9发布及版本/健康/功能检查通过；整体笔记语义、私人资料和性能门槛未全部完成）
- branch: codex/travel-notes-20260927
- worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-notes-20260927
- head/local_commit: b9e4d128dd5839bae89cff39790fb8240297e23e（共同发布源码；本任务文档提交见git log）
- remote_sha: origin refs/heads/main=b9e4d128dd5839bae89cff39790fb8240297e23e；发布前后git ls-remote独立核对一致
- server_before: d228c06d6865bdbca9329f264acfe4cf0e8fc5f7
- server_after: b9e4d128dd5839bae89cff39790fb8240297e23e；/opt/releases/ai-lab-platform-b9e4d128dd58.gR3lJT
- health_check: 8容器healthy；4个Python运行镜像revision=b9；Bridge/ChatWorker active；ready/Bridge/public health均200；6进程配额12000000保持
- functional_check: 图片上传下载/422/跨用户404/doc图片工作流/PCM确认通过；CSV/JSON/TXT/MD真实API导入原件文本私有笔记及跨用户404通过；已发布新刊正文/bundle/5媒体前后一致
- rollback_point: /opt/releases/ai-lab-platform-d228c06d6865.CbxC2W；/opt/ai-lab-shared/rollbacks/chat-travel-pcm-b9e4d128dd58（PG、SQLite、稿件文件、env、8旧镜像，hash和integrity通过）
- manifest: ops/change-manifests/travel-notes-20260927-completion.md
- remaining_risks: 笔记完整语义复测仍待额度答复；真实私人收藏/社交资料未输入；部分时延目标和完整端上性能矩阵未通过；Build72据Apple日志已上传，但整体验收未完成、可安装状态未由本任务核验；出版10cron已独立核验pin b9并恢复，active=[]

本节与文末记录为当前状态；中间各节保留当时发现、失败与授权历史，不代表当前仍未部署。

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

### 正式 Worker 图片验证

自动模式官网截图任务 c644ba991d6241d28382d30a57a6afdb 完成：15.13秒，provider=web-reference，model=page-screenshot，JPEG223681字节，SHA256=c58a17665842b14a97e81662eef12ebb83c0456211919696585c78407fe34d89；服务端API字节读回一致，另一用户404。production-reference.jpg已目视检查：日文清晰、主照片/地图/说明完整可见，部分底部远端资源未加载，作为带来源网页截图而非精修旅行照片。

前一手动模式任务 ee72563062a545b1bb85feb9c190a0dc 实际为生成图（openai-codex/gpt-image-2-medium），48.12秒，350327字节；不当作官网截图证据。两类返回provider/model区分真实，均完成跨用户404验证。

### 浏览器交互预算修复（待协调发布）

真实模型通过已有旅行research节点操作服务器Google Maps，在6轮工具上限触发强制摘要后失败。仅该scenario的KNOWLEDGE_RETRIEVAL节点上限提高到12，其他节点沿用原配置；提示直接进入含起终点地址的路线页，减少重复地点搜索。66项相关回归和Ruff通过，覆盖旅行研究/其他研究/旅行推理构造器实际获得的预算，正在独立服务账号进程实测12轮。未切版、未重启、未修改其他任务临时配额。

### 最终候选状态与真实模型复测

- 最新运行代码260d0ccb784e51fc44515e871213708ffb01adb7已推送独立分支，远端SHA一致；main/服务器仍f8c7。按最新候选状态记录PUSHED，不能把首轮DEPLOYED当成最新补丁已部署。
- 独立云端验收进程使用原生Agent、12轮预算和最终提示，成功获取指定日期路线、地址、班次、票价、来源链接：98.85秒，12次模型调用；这是单次冷进程样本，不是p95，也不代表已发布Bridge完整HTTP通过。证据production-model-twelve-rounds.txt。
- 已授权跨任务协调，并与笔记验收/出版任务明确共享窗口。笔记用户临时额度及账本由其任务负责；本任务不修改、不重置，不提前重启Worker。发现笔记也有待发布补丁，提议联合一次部署，尚待唯一部署方和最终窗口确认。
- remaining_risks: 最终修复未部署，生产Bridge研究全链路待重测；单次98.85秒不能证明并发/SLO；用户私有社交登录资料未在服务器授权，未宣称访问；iOS整合构建/194测试通过，但本任务未发布新TestFlight二进制。整体旅行验收不能报全部完成。

## 联合发布候选

用户授权协调后，笔记任务明确由本任务作为唯一联合部署方，交付/private/tmp/note70-context-evidence.patch：仅knowledge.py和test_cleanup_capabilities.py，模型侧剔除重复snippet等字段，客户端事件/原始正文不动，逐页保留证据指令；其58项PCM回归通过、真实笔记added/removed/changed均0。已审查并应用于本隔离工作树，未接触脏主工作区。联合152项测试通过7.37秒，Ruff/git diff --check通过。

部署方案增加publication SQLite原生backup、integrity_check、SHA256，以及root-only环境备份，保留既有PG dump与镜像/发布目录回滚。最终暂保持12000000月额度用于用户剩余验收，完整部署后的实际覆盖范围需回读；本任务不更改账本。等待笔记/出版确认暂停与空闲窗口，未执行联合发布。

## 联合生产部署与独立验证

- 收到笔记/出版正式窗口：10个cron备份暂停，三个profile active=[]。唯一部署方按已核验main SHA执行，无共享脏工作区修改。
- GitHub精确SHA源码包SHA256：028699855e1740259c72526be6be710f5504d9c52366e680177024b215cdd535。
- 复用已有运行镜像（依赖锁一致）构建代码层；pip check、候选导入通过。复用update.sh、部署锁与expected-current检查，exit0。前端既有镜像保持0b04edc3，不把本次后端发布宣称为新版网页或iOS发布。
- 完整回滚点chat-travel-pcm-d228c06d6865：PG SHA256 fe855820a4881b442413f4af75126bf799e5ea027c1b4b5f5b3700bdbb010974；publication SQLite fc1c88c33cce4d28a6c51da2b32804e8e6880c1ce6f61573ca6f0f780942835c且integrity_check=ok；126M稿件媒体tar eeb1607e7ee609e79b5b9fc811172d07b96a74846731642fc023dddc64ecba84。另有root-only环境备份和8服务旧镜像标签。
- 独立只读核验：8容器healthy；API/3worker revision=d228；Bridge/ChatWorker active；本地ready、Bridge和公开health均200。今晚唯一稿仍staged，20:00发行，actual_release_at=null，正文/content_hash/plan SHA076cbb867c99609ea8ff09322ffcdf5f391990a6df7960c7f708f6776d5c5c9f完全一致。
- 配额实测：API、3worker、Bridge、ChatWorker均12000000。用户授权的临时12m由笔记任务设置；本任务未改该键、未改或重置账本。完整重启后范围扩大，已明确回报笔记任务，恢复10m需覆盖全部上述进程。
- 已向两协调任务交回窗口，出版任务负责独立检查/pin/runtime/恢复10cron；旅行只继续只读Maps功能验收。
- 回滚应先用旧release/镜像恢复代码；数据库/稿件备份用于确有数据损坏的恢复，不能盲目覆盖部署后的合法用户写入。

### 正式生产 Maps HTTP 功能通过

- run_id: wfr_cloud_maps_671946da0bcc，实际已发布Bridge /v1/workflow-runs；使用隔离验收tenant、合法空knowledge capability和正常旅行plan构建入口，不读取私人笔记/收藏、不改额度账本、不修改系统权限。
- travel_research 第1次成功，完整run到awaiting_review（本测试仅包含research节点），error=null；87.83秒，10次模型调用，gpt-5.6-sol/openai-codex。真实工具事件browser_navigate、browser_click、browser_snapshot、browser_type、browser_console。
- 实際页面日期9月28日(月)、出发09:00；东京站〒100-0005東京都千代田区丸の内1丁目；JR中央线09:03东京站→09:17新宿站，14分钟，¥260；来源URL包含8j1790586000。工具事件及最终产物已保留，不把模型单独回答替代真实工具执行。
- 本次为空知识范围正式HTTP路径验证，先前20秒gateway超时未复现；既有12轮旅行研究上限足够完成。本次仅研究节点，不宣称重新跑完生产研究→审批→完整行程→所有客户端场景。
- 证据：joint-production-maps-http.txt、joint-production-maps-workflow.json、joint-http-check.py；独立部署核验：joint-production-verification.txt、joint-server-verify.py。
- 发布后再次git ls-remote确认main=d228c06d6865bdbca9329f264acfe4cf0e8fc5f7。笔记任务独立catalog验证通过；出版任务独立验证d228、备份哈希、唯一staged/20:00/actual=null、3plan/5assets保持，10cron/runtime/wrapper已pin d228恢复，active=[]。
- 不再切换运行版本；后续只把验收文档与回执提交推送本任务分支，不推进main或重启服务。

### 当前边界

云端公共Maps查询及官网截图/生成图正式服务链路已验证，无本机Chrome依赖。Office实际文件、多轮修改、断网恢复及冷启动证据见此前完整回执，合并后194项iOS回归通过；本任务未发布新TestFlight二进制。私人社交登录/Google收藏未在云端建立已授权会话，不能宣称已验收；可访问分享清单和用户上传资料走现有路径。87.83秒是单样本，不能作为生产并发或p95/SLO达标结论。临时12m配额保留供笔记任务验收并由该任务协调恢复，账本从未由本任务更改。

## 导出资料补齐与统一 TestFlight（后续）

用户要求TestFlight合并分发并继续完成剩余项。由既有笔记任务唯一负责归档上传；旅行不单独发布Build70。最新共同main=167fba5c956ade6daba6568fc70c35d7f679406b（图片任务，未部署），将从本隔离分支整合；共享主工作区不动。

架构命中：已有extract_uploaded_text支持CSV/JSON/TXT/MD，但documents白名单和客户端选择器拒绝；JSON原文件会误入OCR envelope。扩展现有documents/私有笔记/贡献编译通路，不新增服务、凭据库或第二个导入器。新增格式保留原件和哈希、按原权限入库；UTF-8 BOM去除，不用替换字符悄悄损坏资料，编码失败保留原件并提示重新导出UTF-8。

改动：backend/api/documents.py、services/document_sources.py、services/upload_text_extractor.py；iOS PlusMenuSheet/NativeClientActionHost/TenantSessionCoordinator的现有选择器和后缀校验；复用test_document_presentation及WorkflowLifecycleDTOTests。

验证：相关后端76 passed/1原有Office预览skip；最终编码错误回归9 passed；iOS194 passed/0 failures（20.259秒，/tmp/travel-export-ios.xcresult），实际客户端上传DOCX/CSV/JSON/TXT/MD原字节保持；Ruff、diff检查通过。API测试覆盖JSON包含data/content_type/extracted_text的普通文件不误解包、CSV BOM、原件下载哈希、同租户跨用户和跨租户404、真实贡献队列回执、编码失败原件保留。未宣称真实用户私人账号资料已读。

性能：正式Bridge澄清30次/并发2，0失败，p50=5.296秒、p95=8.547秒；内部工作流读取+非法内部token拒绝30次/并发4，p95=.063秒。后者是内部认证合同，用户所有者边界由外层API验证。GoogleMaps原生浏览器30次全部读到公共路线，p50=13.694秒/p95=27.388秒；冷15次p50=17.974秒，热15次p50=5.783秒，存在长尾和两次清理超时日志，不宣传稳定低时延。尚不含端上/广域网和完整模型研究总耗时。

本机独立A/B仅5对澄清样本：minimal中位5.651秒、none中位5.247秒，收益不足且小样本；没有为此改变生产模型或推理配置。局部草案30次正式HTTP验收继续执行，最多并发2，19:31后停止新增任务以避开出版窗口。


## 联合候选与性能收据归档（2026-09-27 19:18 CST）

开工盘点：独立旅行工作树 clean；branch=codex/travel-notes-20260927；HEAD=31f46ac4169c0e650f565368e5d39745ec3eed6f；origin=Quantum.git、source=ai-lab-platform.git。共享main工作树HEAD=21250c7b8a5290abcf649b9279bbd91b9af1db88，阅读工作树HEAD=1914bce542cc268476a63064ddb456cd98e785c4；本任务未修改其他工作树。

5a3b8b7f为导出补丁，31f46ac4自动合并图片167fba5c。联合后端214 passed / 1原有Office预览skip（24.41秒）；iOS WorkflowLifecycleDTOTests 194 passed（19.077秒），独立ImageProposalContractTests 1 passed（0.026秒），合计195。单项合同通过不代表相册入库语义通过。

生产局部草案30次全部成功、并发2、两个隔离测试用户：原时间和独立资料标记保持，无外部工具调用。接收p50=.476秒 / p95=1.428秒 / max=1.430秒；草案p50=9.341秒 / p95=13.504秒 / max=18.635秒。草案p95达到15秒目标；接收p95超过1秒，草案p50超过5秒。澄清p50=5.296秒 / p95=8.547秒亦超过3/8秒目标。原生Maps冷/热30次结果有效，但两次cleanup超时警告保留在原日志中。所有本批生产负载已结束，未改模型配置、额度或账本。

这些是已部署d228的正式Bridge/原生浏览器结果；不包含iOS首屏、广域网、TTFT或完整研究工作流的30次统计。不能据此宣称整个性能矩阵完成或全部SLO通过。首次内部只读脚本错误地按X-User-ID判断内部Bridge拒绝，已纠正为内部共享凭据合同，未当作产品跨用户缺陷；外层API所有者隔离由真实认证回归验证。

联合语义审计发现：相册attachPhoto只生成ga图片引用，未走attachDocument/private note/compile/source_refs。与用户“全部上传附件入库编译”的需求不符。已通知统一协调任务，由图片任务唯一负责复用既有路径修复，注意/images也承载临时编辑结果，不能全部无条件入库。旅行未同时修改该入口。阅读候选1914bce4暂缓发布，等待图片补丁与真机全流程。

收据和有界复现探针位于本任务receipts目录：production-clarification-30.jsonl、production-maps-30.txt、production-itinerary-30.jsonl及对应probe.py；export-image-joint-backend.txt、export-image-joint-ios.txt、image-proposal-contract.txt。探针需要原有服务运行环境，未存入任何凭据值；仅供显式验收执行，不是定时任务。私有收藏验收输入尚未收到，分享清单/导出资料路线可用并不等于已验证真实私人账号数据。


## 附件缓存与弱网补充（本机隔离验收）

- 真实FastAPI/SQLite旅行版本API，普通网络、350ms响应延迟、成功提交后模拟503丢失响应并以原request_id重试，各30次，全部通过。每次只增1版本，旧版本、手记和起始时间保持。p95分别.0158/.3844/1.0439秒；此为应用层确定性故障注入，不代表移动无线网络/真机UI。测试服务已停止，没有生产负载。
- 扫描PDF与40页/16不同内嵌图片PPT各30次，同一内容1次冷识别+29次用户私有缓存读取。真实Hermes视觉首轮分别18.435/31.113秒；每次核对图片可读编号、原件字节、私有笔记、另一用户不可读。冷热分离结果见office-cache-summary.json。PDF为1页21,943字节，PPT为181,706字节；不能把多页样例当25MB文件上传或冷启动p95。未包含公网上传、知识贡献编译或端上渲染。
- 独立沙箱本机30次：无profiler p50=.131秒/p95=.160秒，首次.972秒；profile中模板遍历和哈希占约94.6%函数总耗时。但本机结果不能直接解释服务器ack长尾，因此没有擅自改变共享沙箱、安全检查或缓存失效语义。
- 本批没有产品代码修改。可复现输入和日志均入本任务receipts。新增证据不能替代最终统一候选的真机全流程、真实私人资料或完整性能矩阵。


## 最终联合候选复验与当前阻塞（2026-09-27 19:29 CST）

统一协调任务已将相册修复整合为6a935b01b17fd4355152aead7aa0ba02283672eb（父1914bce5）；相册复用一次文档原件上传及doc引用用于编辑，临时处理结果仍使用ga引用。由图片任务137项与协调任务133项后端检查验证，旅行未重复改入口。

旅行只读该冻结候选的源文件，在独立DerivedData/模拟器补跑完整iOS合同：196 passed、0 failures，18.176秒（WorkflowLifecycleDTOTests194 + ImageProposalContractTests2）。日志final-6a-ios.txt，原日志与xcresult位于/tmp。没有修改阅读候选树。依赖锁、compose与update.sh相对d228无变更，原发布wrapper bash -n通过；未执行新服务器发布。

当前运行代码仍d228；新联合候选未推main、未部署、未上传TestFlight。图片任务最终真机流程卡在iPhone镜像的本人Mac登录验证；笔记协调任务全量语义复测等待用户临时额度答复（现12m，拟15m）。这些需用户本人处理，旅行不操作登录验证、不绕额度或账本。20:00出版照常，由出版任务在发行完成后回报可用窗口，未提前暂停cron。私人收藏/社交真实资料也尚未获得输入，不能以合成验收替代。

交付状态保持COMMITTED（旅行代码31f46ac4及后续文档提交；最终共同代码6a由协调任务持有）；远端旅行分支f237、main167，服务器d228。当前可以准备归档和上传前校验，但统一TestFlight正式上传的验收门槛尚未全部满足。性能新增实测和未达目标保留如上，不能宣称全部性能达标。


## 统一Build72发布包准备（2026-09-27 21:08 CST）

协调任务已确认图片543候选完整真机流程通过（图库选择由用户本人完成），图片导出扩展名问题已修复；统一Build72 Release归档源e52d8a9f，后续仅manifest记录。共同main最终b9e4d128dd5839bae89cff39790fb8240297e23e，本任务独立git ls-remote再次核对一致。此前镜像解锁/图片真机阻塞已解除；笔记完整语义验收仍待额度答复，正式TestFlight未上传。

按协调要求仅准备、不部署：从GitHub精确SHA下载服务器offline-source，tar根路径校验通过，归档71,379,877字节，SHA256=aaa818f7259da22b865d6374b4842194996f83f39bfd8ec6ee3dda6b664cebff。requirements/requirements-build/requirements-bridge-worker三个lock与当前运行release完全一致，归档project.pbxproj为Build72。前后.deployed-sha均d228c06d6865bdbca9329f264acfe4cf0e8fc5f7；未切镜像、未执行update.sh、未重启、未改cron或配额。

完整回滚wrapper原样复用、bash -n通过。/tmp/travel-build72-release准备发布wrapper和图片server-functional.py；仅新副本fixture绑定b9e4，不改图片任务原件。现有d228回滚点仍有效，新版本的数据库/稿件/环境/镜像备份将在获得正式空闲窗口后、切换前由同一wrapper生成，本阶段未伪造新回滚点。图片HTTP smoke与健康检查尚未针对b9e4执行。记录build72-package-prepared.json；等待出版生产真机验收释放窗口及唯一协调方的发布通知。


## Build72共同后端正式部署与功能验收（2026-09-27）

唯一协调方收到出版10cron暂停、三profile active=[]确认后明确放行。发布前再次git ls-remote确认main=b9e4d128，发布后再次一致。执行既有完整wrapper exit0：依赖锁与父镜像一致、候选pip check/import通过；持久部署锁与expected-before=d228检查通过；先建立完整可恢复备份，再复用update.sh切版，不修改生产额度账本。8旧镜像与root-only环境备份保留。数据库迁移projects_to_backfill=0/revisions_written=0。

回滚点chat-travel-pcm-b9e4d128dd58：PG SHA256=12040648ca51849ddbe3f1c8f4ee18009437d6d4a78a34eb95d603fbf824b46e；publication SQLite SHA256=863c14f2bea070089baf2930c794ce5fe21dd6fcef184e5786c0fea18be53209、integrity_check=ok；publication文件tar SHA256=02e9ea55f8852fff51c02b700decea1fbfba99b40d35846714b9da4dfb619642。回滚先恢复旧release/镜像，禁止盲目覆盖部署后的合法用户写入。

独立verify全部通过：server_after=/opt/releases/ai-lab-platform-b9e4d128dd58.gR3lJT，8healthy、4运行镜像精确b9、Bridge/ChatWorker active；API ready/Bridge health/公开health全部200；4容器和2Hermes进程配额均12000000。前端镜像仍0b04edc3，不把后端发布当作网页改版。

已发布新刊保护：原按扩展名枚举媒体的预检失败（媒体实际使用evidence blob），未部署前改为读取既有evidence.private_ref并核对receipt.sha256。正式before/after快照完整相等：唯一publication-6d65e4fff6f4ae7734d1585c3a05a80a仍published，actual_release_at=2026-09-27T12:00:32.674400+00:00，正文/content_hash/plan为076cbb867c99609ea8ff09322ffcdf5f391990a6df7960c7f708f6776d5c5c9f，3插图计划、5媒体实际字节与bundle完全保持。after在恢复cron前采集。

生产功能检查全部通过：合成短期测试身份image-release-acceptance-b9e4d128dd58；图片上传/原字节下载、无效输入422、跨用户404，原生fixture JPEG656x369 SHA80b88ed9b4ba5971591240d2d7f059b5f21c27f60724d3196609ef48e11d3a3c，doc原件与私有笔记、doc引用图片工作流、PCM确认创建wf_8816528c1886c007449e3773320467b6。此服务器fixture尺寸与先前真机1200x675是不同样例，未混作同一证据。CSV BOM、含envelope同名字段的普通JSON、TXT和MD原件/解析文本/私有笔记/跨用户404亦通过。model_calls=0，功能smoke主动opt-out共享编译，因此不把该轮冒烟当真实模型编译验收。

部署窗口已交回笔记协调与出版任务，由出版独立pin b9并恢复10cron；本任务不改cron。Build72上传状态更正：协调任务依据Xcode及ContentDelivery.log确认21:19:03 UPLOAD SUCCEEDED，build id=0e03ed6f-0bde-4ba1-88c5-aa45abb7429c；旅行未执行Apple上传，不重复上传。此前要求笔记语义先通过的门禁顺序未满足，必须保留偏差，不能以已上传反推全部验收完成。正式平台可安装/分组分发状态未由旅行核验。

收据build72-deploy.txt、build72-verify.txt、build72-functional.txt、build72-publication-before/after.json以及校验脚本。没有提交图片fixture、数据库、环境或凭据。

出版最终独立回执：server/API b9 healthy，读者API10章、3插图及5媒体200/hash通过；10cron和wrapper pin b9恢复原enabled，prompt/schedule/model不变，三profile active=[]。保护窗口已关闭，未留下临时暂停。
