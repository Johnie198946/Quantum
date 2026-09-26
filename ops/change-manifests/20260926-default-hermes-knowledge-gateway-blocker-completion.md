# Completion Manifest

- task_id: `20260926-default-hermes-knowledge-gateway-blocker`
- task_goal: 交付服务端拥有、可审计的 Workflow Schedule，复用现有 Workflow/QCP/worker 执行链；禁止匿名/public 降级、密钥复制、第二 Runtime/Knowledge 实现及 legacy 自动转换。
- status: `TESTED`（本地候选；未 commit/push/deploy）
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/quantum-2.0-publication-main`
- head/local_commit: `9d40bdcadb6e291deee6aba4ad280d267b4676bb`（未 commit）
- remote_sha: `origin/main=9d40bdcadb6e291deee6aba4ad280d267b4676bb`（`git fetch origin main` 后 ahead/behind=`0/0`）

## 治理盘点

- 当前分支为 `main`；主 worktree HEAD 与 `origin/main` 一致。
- 既有父任务修改 `config/quantumn-daily-publication.json`、`docs/prompts/quantumn-editorial-v2.md`、`ops/change-manifests/20260926-publication-autorecovery-runtime-repair.md` 未覆盖、未还原、未暂存。
- 未跟踪 `build_20260924_issues.py` 与 `data/` 未读取、未修改、未暂存。
- 父任务已删除三条临时 one-shot、暂停本地 `ai-toolkit` 作者 Cron，并让 watchdog 自然调度回读 `awaiting_platform_author`；未 commit/push/deploy，未伪造 publication content handoff。
- 按仓库规则尝试加载 `ponytail`，子 Agent scope guard 返回 `CHILD_SKILL_SCOPE_VIOLATION`，未绕过限制。

## 已验证事实

1. `backend/services/agent_scheduler.py` 读取 legacy `backend.models.agent.Agent` 后，直接向 `/v1/chat` 发送 `{"goal": ...}`；未传 `session_id`、`knowledge_capability`、`knowledge_policy_version` 或 server-owned `agent_config`。
2. `scripts/hermes_bridge_runtime/endpoints.py::chat()` 在上述请求中把缺失 session 降为 `anonymous`，且在没有任何签名 claims 时进入 `_legacy_nonstream_chat()`；这不满足定时任务必须 fail closed 的要求。
3. Bridge 的 `_build_in_process_agent()` 只有在 capability 存在且 `agent_config.allowed_tools` 包含 `knowledge_search`/`user_note_search` 时才注册并装配 `knowledge_gateway`；只补 capability 仍不会得到知识工具。
4. 现有可信 Agent 合同是 `backend/services/agent_capabilities.py::resolve_agent()`/`EffectiveAgent.bridge_config()`；它从基线 registry 或 tenant-owned `TenantAgentModel.composition_manifest` 派生 allowed tools，且校验 tenant、private owner 与 active 状态。`Agent.skills`、prompt 与历史 `template_key` 都不属于该合同。
5. 现有完整授权主链是 `workflow_executor.dispatch()`：`TenantMapping → resolve_policy(compute_catalog()) → policy.restrict() → mint_capability() → trusted_task_agent_config() → /v1/workflow-runs`。Bridge 请求同时携 capability、policy version、tenant execution context 与 server-owned agent config。
6. legacy `Agent` 表只有 `tenant_key`、`created_by`、prompt/skills/template 等历史字段，没有 `workflow_id`、`tenant_agent_id`、PCM capability ID/version、handler binding 或已批准 plan/execution binding。当前 `/api/agents` 也已在 `96defe0` 删除 legacy CRUD/生命周期，现为透明即时执行入口；不存在可产生可信 scheduler binding 的现行认证写入口。
7. 因此无法从 legacy row 唯一、安全地选择 `resolve_agent()` 的 `agent_id` 或既有 Workflow/handler。把 `DEFAULT_AGENT_ID`/knowledge tools 写死、复用 `skills/template_key`、按 prompt 猜绑定或仅凭 created_by 签发 capability，都会越过 PCM/QCP server-owned binding。
8. `TenantMapping` 能验证 `created_by ↔ tenant_key`，但只能证明主体归属，不能补出缺失的能力/handler/Workflow 授权；伪造一个成功请求会把身份认证误当成执行授权。

## 反例与失败边界

- **跨租户/伪 created_by**：必须用 `(TenantMapping.user_id == Agent.created_by AND TenantMapping.tenant_key == Agent.tenant_key)` 精确验证；当前 scheduler 未做。但仅加此检查仍没有 capability binding。
- **失效 policy**：必须在每次触发时重新走 `resolve_policy`、限制当前 scope，并把当前 policy version 与短时 capability 一起交给 Bridge/Gateway；不能复用持久 token。当前 legacy row 不保存可信 scope 来源。
- **缺知识工具**：capability 本身不会启用工具；allowed tools 必须来自 `EffectiveAgent.bridge_config()` 或 `trusted_task_agent_config()`，不能硬编码或从 legacy fields 派生。
- **错误成功回写**：当前 scheduler 仅以 reply 是否以 `⚠️` 开头判成功，无法证明 Bridge 使用了签名路径、知识工具或当前 policy；任意普通文本甚至空合同响应均可能被回写 `ok`。
- **协议缺失**：`GoalRequest` 禁止额外字段；不得自造 tenant/user JSON 字段。现有 chat 合同通过 capability claims + subject-bound session 建立 sandbox，Workflow 合同则显式携 tenant/execution/idempotency。

## 阻塞结论与所需上游变更

不应给 legacy scheduler 增加 capability 拼装补丁，也不应复活已删除的通用 Agent CRUD。安全实施的前置条件是把“定时触发”绑定到现有 Workflow/QCP handler：

1. 由现有认证入口创建一个明确、server-owned、可审计的 schedule → `WorkflowDefinition`（或既有已登记 handler）绑定；绑定必须包含稳定 capability/handler version，不能借用 `skills/template_key/prompt`。
2. 触发时验证 schedule row、Workflow、`created_by`、`tenant_key`、active/frozen plan、primary Agent owner/tenant 全部一致，然后创建/领取现有 `WorkflowExecution`，沿用其幂等键、receipt/event 和状态机。
3. 让现有 workflow worker 调 `workflow_executor.dispatch()`；不要在 scheduler 内复制 policy、agent resolution、Bridge payload 或成功判定。
4. 缺 identity、mapping、Workflow/handler binding、active plan、Agent ownership、current policy/scope、Bridge protocol/version、capability 或 receipt 时，稳定失败并写 error，禁止进入 `/v1/chat` legacy/anonymous 路径。
5. 该绑定需要 PCM/QCP manifest、handler、迁移/写入口和 lifecycle 验收；当前仓库没有 product-capabilities manifest 或可复用 scheduler binding schema，超出“只修 legacy scheduler”可安全承载的范围。

在上述 binding 获批并存在前，没有真实成功主链可供跨租户、伪 created_by、失效 policy、Bridge request 完整字段和 success writeback 测试。添加 mocked happy-path 测试会伪造不存在的授权关系，故本次未修改 scheduler/Bridge/Gateway 源码，也未添加误导性测试。

## 验证

- 聚焦 pytest：`/usr/local/bin/python3 -m pytest tests/test_agents_api.py tests/test_hermes_bridge.py tests/test_knowledge_policy_v2.py -q` → `49 passed, 8 warnings`。
- 首次使用 Hermes venv 的 `python -m pytest` / `python -m ruff` 分别因未安装 pytest/ruff 失败；改用仓库可用的 `/usr/local/bin/python3` 后 pytest 通过。
- Ruff（scheduler、agent contract、policy、workflow dispatcher、Bridge contract/execution/endpoints）→ 仅命中 `backend/services/knowledge_policy.py:172` 既有 `F841 entitlement_version`；该文件无本任务 diff，未越界修改。其余目标无新增 Ruff 问题。
- `git diff --check` → passed。

## 交付状态

- server_before: N/A（未连接服务器）
- server_after: N/A（禁止部署）
- health_check: N/A
- functional_check: BLOCKED（缺 server-owned schedule → Workflow/handler/Agent capability binding）
- rollback_point: N/A（除本 manifest 外无本任务源码改动）
- manifest: `ops/change-manifests/20260926-default-hermes-knowledge-gateway-blocker-completion.md`
- remaining_risks: legacy scheduler 仍能发起 `/v1/chat` anonymous/legacy 请求并可能按文本前缀错误回写成功；在完成 Workflow/QCP binding 前应从部署配置停用该 scheduler，而不是扩大其权限。该停用属于生产配置变更，本任务未获部署授权，未执行。

## 2026-09-26 架构阻塞解除：Workflow Schedule 本地候选

### 实现

- 新增 `workflow_schedules` 持久模型：绑定服务端派生的 tenant/owner、Workflow、冻结 plan id/hash/activation revision、cron/timezone、enabled/next run、last trigger/result/error/execution、schedule version，以及固定 `workflow.schedule@1 → workflow_executor.dispatch@1` 合同。
- 新增 authenticated Workflow 子资源 API：list/create/update/pause/delete。请求 schema `extra=forbid`，不接受客户端 tenant、owner、workflow/plan 或 handler 注入；更新会重新绑定当前已批准冻结 plan。
- 将原 `start_workflow` 的 QWS binding、approval/PlanContract、primary TenantAgent、current policy/scope、DSL/NodeRun、active execution 与幂等创建提取到 `workflow_execution_start.py`；API 与 scheduler 共用同一事务及错误语义。
- 到期 scanner 在每次 fire 重验 schedule contract、owner/tenant、非归档 Workflow、active frozen plan、plan approval、QWS binding、primary Agent active/owner/tenant/origin、current policy/allowed scope；以 `schedule id + scheduled_for + plan id + activation revision` 构造确定性 request key，只创建普通 queued `WorkflowExecution`，由既有 worker/`workflow_executor.dispatch()` 消费。没有 `/v1/chat` 调用或 Bridge payload 复制。
- 每个 schedule 使用独立事务；失败写 `last_result=error/last_error` 并继续其他行。行锁、`(tenant_key, idempotency_key)` 唯一键与每 Workflow 单 active execution 部分唯一索引共同覆盖跨租户、并发和重启重放；重启落后时从 observation time 计算下一次，避免 catch-up 风暴。
- worker dispatch 再次 fail closed 校验 execution→Workflow/plan/primary Agent 与完整 current knowledge scope，防止排队后撤权或归档继续执行；随后通过 `resolve_agent_capability()`/`SAFE_GLOBAL_TOOLS` 生成 server-owned Bridge config，携带 `base_agent_id/name/prompt/allowed_tools/capability_agent_ids/knowledge_scope/allow_network`，并将 Agent、plan、current policy scope 取交集，确保 `knowledge_search` 可用且 tenant metadata 不能注入 `terminal` 等越权工具。
- shared start authority 与 worker dispatch 前都重新对 `plan.dsl` 计算 `canonical_plan_hash` 并与持久 `content_hash` 比较；DSL 被篡改而旧 hash/approval/schedule binding 未变时稳定 fail closed，worker 写 `authorization_failed` event。
- startup migration 创建/验证新 schedule 表，并为既有 `workflow_executions` 增加 tenant-scoped 幂等、单 active execution 及 schedule provenance 约束；它不读取或转换 legacy Agent 行。回滚必须先恢复旧 execution 约束，再删除 `workflow_schedules`，不能只删新表。

### 最强反例与兼容窗口

- 生产只读盘点显示仍有 2 条 active legacy 独立业务任务（“德国队情报雷达”“政策研究雷达”，均 18:00；一条 last ok、一条 error）。应用始终启动新 Workflow scheduler；legacy scanner 只有在服务端 `LEGACY_AGENT_SCHEDULE_ALLOWLIST` 明确列出精确 ID 时才同时启动，默认关闭且绝不自动转换旧行。该兼容窗口仅保活已盘点任务，迁移仍必须经 authenticated Workflow API 重建并审批可信绑定。
- legacy `_scan_due`/`_run_agent_once` 另加 `LEGACY_AGENT_SCHEDULE_ALLOWLIST` 精确 ID 门禁，默认空即不查询、不执行；inventory 仍可只读显示 active row 与 allowlisted 状态。源码与示例配置不硬编码用户或任务 ID；若运维在兼容窗口手工启用 legacy scanner，生产只可配置已盘点的两条精确 ID。
- cron 计算改用 APScheduler `CronTrigger` 作为统一语义；DST fallback 的重复 wall-clock instant 按两个 fold 各触发一次。当前正式 `Asia/Shanghai` 无 DST 转换。
- publication 本地作者入口由父任务 watchdog 改动暂停：无 active manifest 时返回 `awaiting_platform_author`，不再触发已暂停本地 author job；对应脚本/测试及 `~/.hermes/scripts` hash 回读由父任务负责，本候选未改写或回退这些文件。由于本地尚无经 authenticated Workflow API 创建的可信 publication Workflow/plan/Agent binding，本任务未伪造 schedule row，也未改 Cron。

### 测试与证据

- `tests/test_workflow_scheduler.py`：timezone/due/DST fold、空表无持久副作用、并发 fire/restart 幂等、plan drift、DSL tamper、disabled/archived、失败隔离、伪 owner、current policy、inactive Agent、真实 `claim_next()` worker enqueue、真实 `/v1/workflow-runs` payload（含 `knowledge_search` 且剔除 `terminal`/越权 scope）、legacy 默认空 allowlist 不执行、legacy 不自动转换、重复迁移及 DROP rollback。
- `tests/test_workflows_api.py`：schedule API 从 JWT 上下文派生身份、拒绝伪 tenant/owner、跨租户不可见、pause/delete，并保留既有 start/active execution 行为。
- 最终聚焦验证：`pytest tests/test_workflow_scheduler.py tests/test_hermes_bridge.py tests/test_workflows_api.py tests/test_document_presentation.py tests/test_ordinary_knowledge_tool_availability.py tests/test_server_deployment_contract.py tests/test_publication_scheduler_watchdog.py tests/test_publication_editorial_remote.py -q` → `349 passed, 8 warnings`；相关 Python `compileall` 通过；Ruff → `All checks passed!`；`git diff --check` → passed。全仓测试在当前未锁定的本机 `httpx`/Starlette TestClient 环境出现既有兼容错误，未用作通过证据。

### 更新后的交付状态

- task_id: `20260926-default-hermes-knowledge-gateway-blocker`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/quantum-2.0-publication-main`
- head/local_commit: `9d40bdcadb6e291deee6aba4ad280d267b4676bb`（未 commit）
- remote_sha: `origin/main=9d40bdcadb6e291deee6aba4ad280d267b4676bb`
- server_before/server_after: N/A（未部署）
- health_check: N/A
- functional_check: 本地真实 DB/worker queue 路径通过；生产未验收
- rollback_point: 当前 `origin/main`；回滚需同时恢复旧 `workflow_executions` 幂等约束/索引并删除 `workflow_schedules`，禁止只回滚应用镜像而遗留半迁移 schema。
- remaining_risks: 两条 legacy active 行只有在生产注入只含其精确 ID 的兼容 allowlist 后才继续触发；ID 不提交源码。两条任务后续仍需经 authenticated Workflow API 显式重建并移出 allowlist。publication 仍需建立并批准可信 Workflow/Agent/plan，再创建 schedule 并取得生产 receipt；当前仍是未提交本地候选。
