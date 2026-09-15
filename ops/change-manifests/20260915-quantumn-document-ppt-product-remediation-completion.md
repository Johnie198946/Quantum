---
task_id: 20260915-quantumn-document-ppt-product-remediation
status: in-progress
branch: main
baseline: 58d212f18ed1edd71d0a95d18b12fc0b820eb277
started_at: 2026-09-15T11:21:20+08:00
---

# Quantumn 文档与 PPT 产品化修复完成记录

## 当前状态

- 开发已启动。
- 当前阶段：Batch 1–5 的本地实现、真实本地后端 UI E2E、完整 Python 回归、iOS 单元测试及离线模拟器 UI 验收已完成；Batch 1 人工视觉确认、生产矩阵、真机/TestFlight、发布与 Batch 6 前置门禁仍未满足。
- 发布门禁保持 NO-GO。

## 开工门禁

- `main == origin/main == 58d212f18ed1edd71d0a95d18b12fc0b820eb277`
- `git fetch origin main`：成功。
- `git merge --ff-only origin/main`：Already up to date。
- 批准方案文件为本任务输入，纳入本任务文件范围。

## 变更

截至 2026-09-15T11:50:34+08:00：

- 新增伊斯坦布尔不可变原文 fixture 与 15 条确定性 claim golden trace。
- 新增 `presentation_source_trace.py`：精确 span、SHA-256、审批状态、session scope、slide binding、完整覆盖和 manifest。
- 新增 Draft 2020-12 `source-trace.schema.json`，禁止未知字段。
- 文本材料进入 Bridge 前绑定确定性 `source_id/content_hash/source_client_session_id`；缺少会话的旧任务标记为 `legacy_isolated`。
- Bridge 在分析节点注入紧凑事实索引和完整原文，禁止静默截断。
- 批准大纲必须携带 `source_claim_ids`；最终 PPT 生成前强制所有原文 claim 均已批准并映射到页面。
- source trace 写入最终 artifact metadata；未覆盖、未知 claim、篡改 hash 或跨 session 均 fail closed。
- 更新 presentation scenario 指令，禁止 analysis→outline→design 链路丢失 claim ID。
- 新增素材验证与确定性缓存：PNG/JPEG/SVG magic bytes、解码、尺寸、许可、HTTPS/凭据、SVG active content/外链和缓存碰撞均 fail closed。
- 新增素材 manifest JSON Schema；仅允许明确商业使用或用户提供素材。
- 新增 Schema 驱动结构化审核文档与不可变 revision 表；审核状态由服务端持久化。
- 新增 create/read/save/undo API，返回 quoted ETag；保存和撤销强制 `If-Match`，陈旧版本返回 `412` 且不覆盖远端。
- 结构化审核严格绑定 workflow owner，并从服务端 requirements snapshot 继承 source client session；同租户其他用户不可读取。
- PCM 注册 `structured_review` renderer 及 ready/saved/conflict 事件，为 iOS 统一组件保留旧 artifact fallback。
- iOS `APIClient` 新增保留 `HTTPURLResponse` 的兼容请求路径；原 `request` 调用保持只返回解码值，结构化审核专用路径读取 quoted ETag 并发送 `If-Match`。
- iOS 新增统一 `StructuredReviewView`，按服务端 Schema 渲染 text、textarea、choice、number、toggle，并支持必填校验、保存与 Undo。
- Workflow 的 Word/PPT 成果审核入口已接入统一组件；审核文档只在服务端明确返回 `404` 后创建，避免网络错误触发覆盖式初始化。
- `412` 冲突显示本地/服务端逐字段 Diff；服务端同时返回 `remote_etag`，用户可选择载入远端或以远端最新版为 CAS 基线保留本地同名字段后再次保存。
- Chat 请求现在建立服务端可验证的 tenant/user/client-session 注册；workflow 创建拒绝未注册会话及同租户 owner 冲突，不再只校验客户端字符串格式。
- Workflow 将服务端派生的 session binding ID 与 source session 持久化为一等字段，并提供加法式启动迁移；legacy row 不从可变 JSON 反推可信归属。
- Workflow/execution owner 检查改为 fail closed，`clarification_session_id` 为空也不再变成租户级可见；QCP 幂等重放返回已有 execution 前校验 workflow 身份。
- active activity/execution API 支持精确 source-session 过滤；iOS 只请求当前会话并以服务端权威快照替换本地 active cache，不再永久累加旧 activity。
- iOS 使用不可变 `ownerIdentity + clientSessionId + generation` scope token；切换账号/会话时递增 generation、取消 monitor 并清空 scope cache。
- lifecycle SSE、polling、clarification、execution、artifact preview、structured review、deep link 与直接创建均在异步写 observable state 前复核 scope；迟到写入丢弃并写入本地 `workflow-scope` 日志。
- 没有精确 source-session provenance 的 legacy workflow 不进入当前聊天 activity 投影，仍可在独立 Workflow 历史入口处理。

## 测试

- 来源追踪、文档/PPT、素材、工作流 API、PCM capability 综合回归：`121 passed, 0 failed, 0 skipped, 8 warnings`。
- 结构化审核覆盖 Schema 校验、持久化、ETag/CAS、缺少前置条件、陈旧写冲突、Undo、新版本收据及同租户跨用户隔离。
- Ruff（本次 Python 文件）：通过。
- `git diff --check`：通过。
- warnings 为既有 FastAPI lifespan 与 Pydantic v2 deprecated 提示；未计作失败，但后续重构需处理。
- iOS 模拟器 `WorkflowLifecycleDTOTests`：`146 passed, 0 failed, 0 skipped`；覆盖混合 JSON scalar、响应 Header/quoted ETag、`If-Match`、typed `412`、404 后创建及五类字段渲染。
- iOS 模拟器渲染附件 `Structured-review-all-schema-fields` 已导出并人工检查：浅色、五类字段、版本、进度、Undo/保存均可见，无重叠或截断。
- Xcode 工程 `plutil -lint`：通过；iOS Debug simulator build：通过。
- 本批后端 scope/chat/presentation 综合回归：`170 passed, 0 failed, 0 skipped, 8 warnings`。
- 本批完整 `AIPlatformAppTests` 模拟器目标：`207 passed, 0 failed, 0 skipped`；xcresult 为 `Test-AIPlatformApp-2026.09.15_14-33-10-+0800.xcresult`。
- 新增的聚焦测试覆盖跨 session tracking 拒绝、generation rollover 清缓存、迟到旧 generation 响应丢弃、直接创建透传 session、deep-link 拒绝和 artifact preview 拒绝。
- Batch 1 新版伊斯坦布尔产物：7 页、7 类布局、6 个可编辑 SVG 图标、5 个可编辑地标、5 张经来源页核验的 Wikimedia 照片，以及带 ODbL 署名的真实 OpenStreetMap 底图；PPTX/PDF/渲染结构门禁 `10 passed, 0 failed, 0 skipped`。
- Batch 2 本地真实后端模拟器 UI E2E：双客户端 CAS 编辑、服务端并发写、HTTP `412` 冲突、载入服务端版本、再次保存、杀 App 重启后持久化，`1 passed, 0 failed, 0 skipped`；xcresult：`/tmp/StructuredReviewLocalE2E.xcresult`。
- Batch 4 离线模拟器 UI：小屏、键盘、折叠底栏、失败原因/重试、渐进披露和 Agent 描述，`6 passed, 0 failed, 0 skipped`；xcresult：`/tmp/AIPlatformAppUITests-fixtures.xcresult`。
- 当前完整 `AIPlatformAppTests`：`208 passed, 0 failed, 0 skipped`；xcresult：`/tmp/AIPlatformAppTests-remediation.xcresult`。
- Batch 5 三条可持久复核的文档 E2E：`3 passed, 0 failed, 0 skipped`；DOCX 与逐版本收据在 `artifacts/acceptance/document-e2e/`。
- 完整 Python 回归最终结果见 `ops/acceptance/quantumn-document-ppt-local-evidence.yaml`；skipped 项单列，未计作通过。

## 发布

- local_commits:
  - ebc23dccef444264f13cbd5d24ec60ea2df88ce0
  - b86ddb0f650fe9abf739da80d2b29a9b4f1491c5
  - 7486fec37246b9cd8456414cdf04f724cdc9ebd1
  - 6e4f099eb66c5bf7e432fc97ee9253a4de1e29fa
  - a1dc239de8166119450b25afdf145ca6241a546c
  - 5ee9049384813029f7d535d40d7c079379611940
- remote_sha: not pushed
- server_before: not captured
- server_after: not deployed
- testflight_build: not uploaded
- rollback_point: 58d212f18ed1edd71d0a95d18b12fc0b820eb277

## 剩余风险

- 新版伊斯坦布尔 PPTX/PDF/montage 已生成并通过自动门禁，但用户人工视觉确认仍为 `pending`；自动规则不能代替该产品门禁。
- Batch 3 本地 owner/session/generation 代码、后端双账号双会话矩阵及模拟器迟到响应测试已通过；生产环境双账号×双会话、四任务并发、快速切换、退出/重登、冷启动、网络延迟和 legacy 混入仍缺真实生产回执。
- Batch 5 生产处理链的确定性 E2E 已生成最终 DOCX 和版本收据，但 clean-room 生产收据仍为 `unverified`。
- 真机当前在 Xcode 中为 offline；TestFlight 未上传，服务器未部署，数据库迁移、监控和回滚演练未执行。
- Batch 6 按方案禁止提前启动；必须等待 Batch 1–5 人工/生产门禁通过。
- 因此整体验收继续 **NO-GO**。
