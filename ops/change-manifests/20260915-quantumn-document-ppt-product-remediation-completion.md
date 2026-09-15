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
- 当前阶段：Batch 0 基线夹具与 Batch 1 来源追踪。
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

## 测试

- 来源追踪、文档/PPT、素材、工作流 API、PCM capability 综合回归：`121 passed, 0 failed, 0 skipped, 8 warnings`。
- 结构化审核覆盖 Schema 校验、持久化、ETag/CAS、缺少前置条件、陈旧写冲突、Undo、新版本收据及同租户跨用户隔离。
- Ruff（本次 Python 文件）：通过。
- `git diff --check`：通过。
- warnings 为既有 FastAPI lifespan 与 Pydantic v2 deprecated 提示；未计作失败，但后续重构需处理。

## 发布

- local_commits:
  - ebc23dccef444264f13cbd5d24ec60ea2df88ce0
  - b86ddb0f650fe9abf739da80d2b29a9b4f1491c5
  - 7486fec37246b9cd8456414cdf04f724cdc9ebd1
- remote_sha: not pushed
- server_before: not captured
- server_after: not deployed
- testflight_build: not uploaded
- rollback_point: 58d212f18ed1edd71d0a95d18b12fc0b820eb277

## 剩余风险

- PPT 内容、视觉、统一编辑组件、串扰与文档类 PCM 尚未完成全量验收。
- 未生成并由用户人工确认新版伊斯坦布尔 PPTX/PDF。
