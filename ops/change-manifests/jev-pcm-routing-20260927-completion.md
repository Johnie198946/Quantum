# jev-pcm-routing-20260927

task_id: jev-pcm-routing-20260927
status: TESTED
branch: codex/jev-pcm-routing-20260927
worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/jev-pcm-routing-20260927
head/local_commit: ae11b9bd8e30c89269ea8c59da7cf239fac86920 (baseline; no new commit)
remote_sha: 未执行本任务 push 或 ls-remote；不得视为已推送
server_before: 先前只读诊断记录 c5331384d0f895ddd94cc385d6ef69b7d4d9d9cf；本次修改未重新读取服务器
server_after: 未部署
health_check: 未执行生产健康检查
functional_check: 312 项相关测试通过；最终六条分类用例全部符合预期（4 条真实模型、2 条本地拒选）；客户端端到端未验证
rollback_point: 本地基线 ae11b9bd8e30c89269ea8c59da7cf239fac86920；无服务器变更，服务器回滚不适用

## 目标及架构命中

原有 JEV 已实现 Skill/Agent 选择，PCM 原生工具和 Gateway 已实现，但两者没有产品能力候选投影。扩展同一 JEV schema/cache/resident shortlist，复用现有 app_* 工具、QCP 确认和工作流处理器，没有新路由器、服务或依赖。92 个 implemented 合约全部可投影；请求候选与实际开放工具取交集，不扩大权限。最近四条原生历史用于续聊；模型只能返回当前候选 ID。选中动作须有匹配工具结果或有效澄清，纯文本不能作为执行证明。工具线程通过共享请求记录回传结果。

旅行依然使用 workflow.create(output_kind=travel) -> existing travel planner -> travel_research / travel_itinerary / travel_notebook / travel_plan_v2。未改旅行工作流内部执行与确认逻辑。

离线模型发现合并长描述会稀释触发示例，因此 PCM 示例单独编码、按最高相似度匹配。同一 capability 去重后参与既有总数五个候选限制。Skill/Agent 编码方式保持原有行为。补充 note.create 中文触发示例，语义模型仍负责最终选择。

## 开工前盘点

按用户当前明确的一任务一分支一 worktree 要求执行，优先于仓库历史 main-only 规则。原 Quantum 主目录存在其他任务改动，未修改或暂存。managed worktree 工具绑定旧 showroom 仓库且无法解析 Quantum ref，故使用 git worktree add 建立本任务目录。

- 新 worktree 初始 status: clean (`## codex/jev-pcm-routing-20260927...origin/main`)
- branch: codex/jev-pcm-routing-20260927
- HEAD: ae11b9bd8e30c89269ea8c59da7cf239fac86920
- baseline: fetched origin/main
- remote: origin https://github.com/Johnie198946/Quantum.git; source https://github.com/Johnie198946/ai-lab-platform.git
- worktree 盘点记录见下方；任务目录为独立新建，未混入其他任务文件。

## 变更文件

```
agency/hermes-plugins/ai-lab-capabilities/capability_router.py
agency/hermes-plugins/ai-lab-capabilities/jev_resident.py
agency/hermes-plugins/ai-lab-capabilities/jev_selector.py
backend/contracts/product-capabilities/capabilities.yaml
backend/services/capability_catalog.py
backend/services/capability_projection.py
config/pcm-routing-contract.yaml
docs/product-specs/capability-gateway.md
scripts/hermes_bridge_runtime/agent_execution.py
scripts/hermes_bridge_runtime/knowledge.py
tests/test_jev_selector.py
tests/test_pcm_jev_routing_contract.py
tests/test_pcm_semantic_capabilities.py
tests/test_product_capabilities.py
ops/change-manifests/jev-pcm-routing-20260927-completion.md
```

## 校验

Python: /private/tmp/quantum-image-venv/bin/python

1. pytest tests/test_jev_selector.py tests/test_pcm_jev_routing_contract.py tests/test_pcm_semantic_capabilities.py tests/test_product_capabilities.py tests/test_capability_gateway.py tests/test_travel_plan.py tests/test_hermes_bridge.py tests/test_cleanup_capabilities.py -q: **179 passed, 14 subtests passed**。HTTP 模拟仅使用 localhost；已批准本机端口。
2. pytest tests/test_agency_integration.py tests/test_agent_os_runtime_acceptance.py tests/test_client_session_notes.py tests/test_knowledge_run_adapter.py tests/test_qws_hermes_context.py -q: **133 passed**。
3. git diff --check: passed；所有修改 Python 文件 ruff: passed。
4. 全仓 pytest --maxfail=5: 417 passed, 5 failed。将 HEAD 导出至 /private/tmp/jev-pcm-baseline-20260927 后同样五项均失败：notifications_flow、layered_architecture、hermes_bridge_modules_stay_cohesive_and_static、workflow usage snapshot、chat in-flight。原因包括已有模块超长/分层违规、可信配置缺失、/opt 本地权限与通知 fixture。
5. 全仓 ruff: 11 F811；同一 HEAD 基线复现全部 11 个，位于未修改的 agent_config/endpoints/session_runtime 等文件。未擅自修复无关问题。
6. 本地固定 ONNX 模型离线检索：92 PCM + 273 Agent，当前本地 skill catalog 为 0；无网络、无生产操作。结果如下，仅证明 shortlist 可达，不等于最终语义模型正确选择。

```json
[
  {
    "q": "规划七天旅行，公共交通，看海、火山、森林和温泉",
    "shortlist": [
      "agency:geographer",
      "agency:spatial-data-scientist",
      "workflow.create",
      "knowledge.navigation",
      "presentation.create_from_text"
    ]
  },
  {
    "q": "把以上做成攻略",
    "shortlist": [
      "agency:geographer",
      "agency:spatial-data-scientist",
      "workflow.create",
      "knowledge.navigation",
      "presentation.create_from_text"
    ]
  },
  {
    "q": "查找我的项目管理笔记",
    "shortlist": [
      "agency:meeting-notes-specialist",
      "knowledge.note.archive",
      "project.list",
      "knowledge.note.search",
      "knowledge.note.illustration.status"
    ]
  },
  {
    "q": "把文章存成笔记",
    "shortlist": [
      "knowledge.note.compare",
      "knowledge.note.search",
      "knowledge.note.merge",
      "knowledge.note.create",
      "knowledge.note.illustration.status"
    ]
  }
]
```

## 权限及未完成项

- 自动审批拒绝真实辅助模型分类验证：会发送测试文本及 PCM 元数据到尚未确认可信的辅助服务。拒绝命令未执行；没有绕过，改为本地离线检索。若继续真实模型验证，需用户明确授权并确认目的服务。
- 真实模型完整语义选择、iOS 实际 chat -> 确认 -> workflow -> notebook 端到端尚未验证。不能声称用户截图场景已在生产修复。
- 未授权/未执行 commit、push、部署；没有远端新 SHA 或服务器回滚点。
- JEV 既有低置信度/超时回退仍保留；候选可见不保证每次均选中，不能保证全部 92 项语义准确率。
- 全仓既有失败如上。没有前端改动，未执行 frontend build。
- 回滚：仅撤销本任务列明文件中的修改；不要覆盖其他 worktree 或用户内容。

## worktree 盘点（交付时）

```
worktree /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
HEAD 21250c7b8a5290abcf649b9279bbd91b9af1db88
branch refs/heads/main

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/image-studio-v4-20260927
HEAD ae11b9bd8e30c89269ea8c59da7cf239fac86920
branch refs/heads/codex/image-studio-v4-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/jev-pcm-routing-20260927
HEAD ae11b9bd8e30c89269ea8c59da7cf239fac86920
branch refs/heads/codex/jev-pcm-routing-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/knowledge-ui-refresh-20260927
HEAD ae11b9bd8e30c89269ea8c59da7cf239fac86920
branch refs/heads/codex/knowledge-ui-refresh-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/quantum-confirmation-fix-20260927
HEAD b9e4d128dd5839bae89cff39790fb8240297e23e
branch refs/heads/codex/quantum-confirmation-fix-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-notes-20260927
HEAD 370bd4c479e0f71fd7fed1c7743dc4291d73a7b5
branch refs/heads/codex/travel-notes-20260927

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/image-direct-processing-20260927
HEAD b9e4d128dd5839bae89cff39790fb8240297e23e
branch refs/heads/codex/image-direct-processing-20260927
```

## 2026-09-28 授权后的真实分类验收

用户明确回复“允许”，授权现有 Hermes 辅助服务接收合成文本和 PCM 候选元数据。没有使用生产会话、没有执行能力写入，也没有获得 push/deploy 授权。之前审批限制已解除。

- 启动环境修正：Hermes 源码优先于项目同名 tools 包；仅加载既有 .env 代理变量，不修改持久配置、不打印密钥。
- 完整本地目录：92 个 implemented PCM、307 个 Skill、273 个 Agent。修正了上次离线环境漏载 Skill 的验证范围。
- 真实模型首轮暴露旅行续聊漏选、笔记检索候选被挤出；扩展既有 workflow.create / knowledge.note.search 合约触发说明，并明确 JEV 结合前文生成交付物的语义要求。未新增路由、未放宽输出校验或超时。早期 INVALID_OUTPUT 原始响应未捕获，不能宣称已单独解释该错误。
- 最终六条用例全部符合预期：旅行首次规划与续聊 -> workflow.create；笔记检索 -> knowledge.note.search；保存文章 -> knowledge.note.create；闲聊与火山知识问答 -> 无产品动作。四条正例使用真实 openai-codex/gpt-6-luna，两个负例走既有本地低相似度拒选。所有 cache_hit=false。
- 最后针对 metadata/prompt 修改复测：75 passed，1 个 localhost HTTP 用例 deselected（该项此前已通过，此次没有修改对应路径）。修改文件 ruff 与 git diff --check 通过。
- 证据：ops/acceptance/jev-pcm-routing-20260927/live-classification.json，包含最终原始选择及校验后结果。
- 状态仍为 TESTED，HEAD/branch/worktree 未变，无新 commit；remote_sha 未推送；server_after 未部署；health_check 未执行；rollback_point 仍是本地 ae11b9bd 基线。
- remaining_risks：样本仅六条，不能代表全部能力准确率；网络/model 超时仍可能回退；iOS chat -> 确认 -> workflow -> notebook 端到端尚未验收。

## 2026-09-28 部署请求预检（尚未发布）

用户要求部署。当前工作树仍为本任务隔离分支，未提交；修改文件的 ruff 和 git diff --check 通过。GitHub main 只读验证为 457abcd4284f5ab0910df1d138475894b963a782，比本任务基线 ae11b9bd 多一个编辑内容提交，文件不重叠。服务器 /opt/ai-lab-platform 软链指向 /opt/releases/ai-lab-platform-ae11b9bd8e30.K1hkwb，hermes-bridge.service active；此为可识别的部署前版本，不代表已建立部署回滚点。

仓库根 AGENTS.md 明确要求仅 main 修改、当前非 main 或 main 有其他任务改动时停止协调。当前 main 工作树落后远端 22 个提交，且有数十个未提交文件，其中 capabilities.yaml、capability_catalog.py、agent_execution.py、knowledge.py 与本任务重叠。不得覆盖、暂存或混入这些内容。由于用户此前明确要求一任务一分支/worktree，现有隔离分支的创建与仓库根规则冲突；发布路径需用户明确选择/授权。此时状态仍 TESTED；未 commit、push 或 deploy，remote_sha 为既有 main 而非本任务 SHA，server_after/health_check/functional_check 未执行。

部署前只读核验：/opt/ai-lab-platform/.deployed-sha = ae11b9bd8e30c89269ea8c59da7cf239fac86920；/opt/ai-lab-platform -> /opt/releases/ai-lab-platform-ae11b9bd8e30.K1hkwb；hermes-bridge.service 与 hermes-chat-worker.service 均 active；http://172.18.0.1:9118/health 返回 status=ok。曾以 127.0.0.1 测试端口失败，原因是服务仅绑定 172.18.0.1；已用实际 bind 地址完成健康基线。最新 GitHub main 通过 git ls-remote 核对为 457abcd4284f5ab0910df1d138475894b963a782。

基于该远端 main 的临时目录补丁 `git apply --check` 成功，相关 179 tests + 14 subtests passed，未修改共享 main。

## 2026-09-28 隔离发布授权与快进复测

用户明确选择“授权隔离发布（推荐）”，授权绕过 Quantum 根 AGENTS.md 的 main-only / 共享 main 停止规则；其他安全约束仍执行。隔离 worktree 从 ae11b9bd 快进到 GitHub main 457abcd4284f5ab0910df1d138475894b963a782，remote 只修改了 publication_editorial 等五个与本任务不重叠文件。共享 main 的 dirty 状态完全保留。快进后重新运行相关 179 passed + 14 subtests passed，扩展运行 133 passed；修改文件 ruff 与 git diff --check 通过。发布将仅暂存下列本任务文件；后续按精确 SHA 核验和更新部署结果。
