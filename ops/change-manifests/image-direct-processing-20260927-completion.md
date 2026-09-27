# 图片直接处理：本地完成记录

task_id: image-direct-processing-20260927
status: TESTED（仅本地；未提交、推送或部署）
branch: codex/image-direct-processing-20260927
worktree: /Users/dengzhaoyu/Documents/AI Lab/.worktrees/image-direct-processing-20260927
head/local_commit: b9e4d128dd5839bae89cff39790fb8240297e23e（基线；本次未提交）
remote_sha: 本次未 push、未建立新远端交付；基线 b9 由协调任务提供
server_before: 未操作；协调任务报告生产 b9，本次未独立核验
server_after: 未部署；与本次改动无关联
health_check: 生产未执行；本轮仅本地验证
functional_check: 见下方测试记录；本轮未占用真机，未声称完成新版真机验收
rollback_point: 未部署，无服务器回滚点；本地差异独立保留在本任务 worktree，基线 b9

## 范围与授权

原版图片处理已另行完成真机链路，本轮实现后续“上传＋一句话需求，直接得到成品”的简化。通过已获授权的笔记协调任务对接确认修复任务。当前交付范围只允许本地修改/验证，不提交、不推送、不部署、不上传 TestFlight，也不操作已交还的真机。

用户当前提供的 AGENTS.md 要求一任务一分支一 worktree，优先于仓库历史 main-only 文件。先调用 app list_artifacts（空）与 create_worktree；app 绑定 AI Lab 仓库无法解析 Quantum 的 b9 ref，返回 invalid reference。经既有协调确认后，从 Quantum 主仓库用 git worktree add 建立此隔离目录，未修改 canonical main 的既有脏文件。

## 开工盘点

- 初始 status：`## codex/image-direct-processing-20260927`，无修改。
- branch：`codex/image-direct-processing-20260927`。
- HEAD：`b9e4d128dd5839bae89cff39790fb8240297e23e`。
- origin fetch/push：`https://github.com/Johnie198946/Quantum.git`。
- source fetch/push：`https://github.com/Johnie198946/ai-lab-platform.git`。

```text
worktree /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
HEAD 21250c7b8a5290abcf649b9279bbd91b9af1db88
branch refs/heads/main

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/knowledge-ui-refresh-20260927
HEAD b9e4d128dd5839bae89cff39790fb8240297e23e
branch refs/heads/codex/knowledge-ui-refresh-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/quantum-confirmation-fix-20260927
HEAD b9e4d128dd5839bae89cff39790fb8240297e23e
branch refs/heads/codex/quantum-confirmation-fix-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-notes-20260927
HEAD b2742530ebf81748a22d8c7f8310f509af7c0ad5
branch refs/heads/codex/travel-notes-20260927

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/image-direct-processing-20260927
HEAD b9e4d128dd5839bae89cff39790fb8240297e23e
branch refs/heads/codex/image-direct-processing-20260927

```

## 架构与改动

部分实现：图片已有 owner-bound 上传、原图哈希、标准工作流、Mantis/UIKit/Vision 端侧像素处理及设备回执。新增仅限自动推进现有主链：

- `_create_workflow` 对图片复用草稿创建、build_plan、approve_plan、start_workflow，自动冻结经过校验的计划，使用固定图片执行 request_id；其他输出种类仍返回原澄清流程。
- PCM 仅 `media.process` 免重复确认；catalog 例外要求对应低风险 write、原有 handler/policy、幂等和回执。Bridge 原直接调用白名单纳入该能力，从可信 context 注入 source_client_session_id，覆盖模型自报值。
- 端侧回执验证格式、尺寸、透明度、owner、原图哈希后直接 completed；原图与私有下载鉴权不变。
- 现有 iOS workflow.created 路由已自动打开任务。执行页获取参数后自动唤起设备 action，action 首次出现自动运行；完成后自动预览，失败可重试，保留取消及账号切换校验。图片入口按钮改为“处理图片”。
- 未添加服务、依赖、后台执行链或新状态容器。更新现有合同生成视图与最小回归测试。

变更文件：
```text
backend/api/workflows.py
backend/contracts/product-capabilities/generated_artifacts.yaml
backend/services/capability_catalog.py
backend/services/image_processing.py
docs/product-capability-coverage.json
docs/product-capability-manual.md
docs/product-specs/capability-gateway.md
ios/AIPlatformApp/Views/Chat/NativeClientActionHost.swift
ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift
ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift
ops/acceptance/ios-capability-matrix.json
scripts/hermes_bridge_runtime/knowledge.py
tests/test_image_processing.py
ops/change-manifests/image-direct-processing-20260927-completion.md
```

## 本补丁独立验证

- Python 主回归：`pytest tests/test_image_processing.py tests/test_product_capabilities.py tests/test_workflows_api.py tests/test_workflow_capabilities.py tests/test_client_action_capabilities.py tests/test_capability_gateway.py tests/test_workflow_event_projection.py -q`：106 passed；日志 `/tmp/image-direct-regression.log`。
- 邻近边界：`pytest tests/test_image_processing.py tests/test_travel_plan.py tests/test_document_presentation.py tests/test_workflow_artifact_reading.py tests/test_ios_capability_matrix.py -q`：94 passed, 1 skipped；日志 `/tmp/image-direct-boundaries.log`。跳过为既有 PPTX 预览渲染进程 exit -6，不计通过；定位日志 `/tmp/image-direct-skip.log`。
- iOS 独立模拟器 ABF1D802-4EA9-40D8-873F-F4AAB977F409：WorkflowLifecycleDTOTests + ImageProposalContractTests，198 passed，0 failures；`/tmp/quantum-image-direct-tests2.xcresult`。首次 sandbox 构建因缓存写权限失败，获工具升级执行许可后成功；未操作真机。其后修改图片入口两条文案，最终增量构建与4项相关测试通过：`/tmp/quantum-image-direct-final.xcresult`。
- Ruff、两份 PCM/iOS 生成器 --check、git diff --check 通过。

关键测试：
- `test_upload_to_image_workflow_and_downloadable_jpeg`：Chat/显式 workflow × ga/doc 原图，共4例；不调用人工确认接口即生成执行；设备回执完成后直接下载验证 JPEG 字节；错误结果、跨用户回执被拒，同一设备回执幂等。
- `test_image_direct_bridge_uses_trusted_session_and_replays_once`：真实 Bridge 工具直接进入 PCM；模型伪造 session 被覆盖；缺 session/缺原图/其他用户绑定 session 被拒；重复请求复用执行，不发 proposal。
- `test_image_exception_does_not_remove_other_mutation_confirmation`：笔记删除、通用工作流创建/启动、PPT创建、图片生成仍需确认；缺图、无效图与越界参数不能成功。
- `testDirectImageWorkflowEventOpensWithoutProposalAndRejectsForeignSession`：普通 SSE workflow.created 自动开页，外会话拒绝，重放不重复卡片。
- 既有真机 opt-in 测试已更新为读取 completed，不再手工 review；本轮未运行该真机测试。

## 集成依赖与组合验证

本补丁基于 b9；**不能单独宣称 Chat 全链路可发布**。必须同时集成确认修复任务的：
1. `backend/api/chat.py` 两种 transport 的 client_session_id 透传；否则 Bridge 缺可信客户端会话会失败关闭。
2. `APIClient.swift` composition.planId 可选解码；否则现有后端 agent 返回可能导致 DTO 解码失败。

确认修复原目录与已有差异保持冻结。独立临时目录 `/tmp/image-direct-combined-20260927` 从 b9 归档生成，仅应用两份独立 diff，不整文件覆盖：
- 本任务 `/tmp/image-direct-own.patch`。
- 确认修复 `/tmp/image-direct-confirmation-dependency.patch`。
- 初次归档安全过滤拒绝仓库 tools 绝对 symlink；重建只提取普通文件/目录，不跟随该链接。
- 组合后端 `pytest tests/test_chat_stream_api.py tests/test_image_processing.py -q`：44 passed；日志 `/tmp/image-direct-combined-python.log`。
- 组合 iOS：5 passed，0 failures，覆盖图片 SSE 自动打开、composition 缺失/null/存在 planId 解码和图片合同；`/tmp/quantum-image-combined-tests.xcresult`。该组合测试执行时不含随后两条入口文案调整；最终文案已在本补丁独立增量构建和4项测试通过。

## 风险与未完成项

- 新版“无中间确认”的真实 PhotosPicker→Chat→端侧处理→自动预览全链路尚未做真机验收；原版人工确认链的真机证据不能替代本轮。
- 组合模拟器测试验证合同与事件路由，不替代照片交互 UI 全链路或真实模型自然语言解析验收。
- 需由统一发布任务合并本补丁与确认修复、验收最终客户端，再另行执行发布；本轮保持本地，未产生 commit/remote/server 新版本。
- 回滚仅移除本任务精确 diff；不得覆盖确认修复或其他任务文件。未改任何线上数据。

最终差异导出：`/tmp/image-direct-own.patch`（本任务运行代码/测试/合同）与 `/tmp/image-direct-complete.patch`（另含本 manifest）；确认任务补丁仍单独保存在 `/tmp/image-direct-confirmation-dependency.patch`。
