# 学习练习接入 Chat / PCM

task_id: learning-chat-pcm-audit-20260927
status: TESTED
branch: codex/learning-chat-pcm-audit-20260927
worktree: /Users/dengzhaoyu/Documents/AI Lab/.worktrees/learning-chat-pcm-audit-20260927
head/local_commit: 9fbc4e0be46714c093bde3336040cfc9e1e69ca3（基线；本任务未提交）
remote_sha: 本轮未 push / 未执行 ls-remote；不能标为 PUSHED
server_before: 未读取；不推断生产当前版本
server_after: 未部署
health_check: 不适用；本轮未部署或检查生产健康
functional_check: 后端 129 项、Web 事件 1 项、iOS 定向回归通过；最终题号卡片视觉检查通过；未执行生产自然语言 / 真机在线验收
rollback_point: 不适用；未改服务器。仅独立 Worktree 本任务未提交 diff，可逐文件审阅撤销，禁止覆盖其他任务修改。
remaining_risks: 生产模型语义选择、实际端到端时延、真机在线闭环尚未验收；新版客户端与后端需配套发布。

## 目标和架构判定

将已存在的混合练习领域能力接到 Chat 和 PCM，使用户能要求按阅读章节出题、恢复题组、请求真实提示、记录单题答案、提交整组并解释正式成绩。

审计90c8894快照时主线没有完整网关；实施前同步到9fbc4e0b，发现主线已提供正式PCM目录、Capability Gateway及原生Hermes工具编译。因此更新方案：**不新增Skill、Agent、service、数据库表或第二条模型调用链**，只注册6个能力并适配已有领域函数。前次审计关于“必须新增学习Skill”的建议被这一代码证据取代。

复用：backend/api/learning.py的create/get/save_draft/submit、owner_query/owned和public；subscriptions.learning_resume；capability_catalog/gateway的签名身份、提案确认、持久回执与幂等；Hermes原生工具编译；iOS既有确认卡片、MessageBlock持久化和LearningExerciseView。

新增必要边界：learning.yaml契约及薄Handler；Chat题组引用字段纳入已有签名上下文，仅定位、不授予权限；learning.exercise事件和客户端卡片。未生成独立练习状态容器。

## 行为与边界

- learning.resume：读取用户最近实际阅读的书籍/章节/版本。
- learning.exercise.read：读取指定或最近题组；明确要求未完成题组时可过滤。每次复查所有权及书籍授权。未批改不泄漏答案；未请求的hint不向Chat输出。
- learning.exercise.create：按确认提案创建同一正式题组；同一key派生固定UUID，复用领域生成。
- learning.exercise.hint：读取预生成hint并保留其他草稿、将该题assisted置true；无额外模型请求；旧题无hint明确拒绝。
- learning.exercise.answer：合并指定题答案，保留其他题和已有辅助标记；拒绝空答案、非法选项和旧revision；不自动提交。
- learning.exercise.submit：仅提交完整的服务器草稿，复用正式批改和成绩；不替用户补答。
- 所有写能力沿用现有确认卡片与一次性token；模型工具只创建提案。确认后才展示执行结果。重试通过持久回执恢复，不重复消费token。
- Chat卡片持久化题组引用，打开准确ID并回读服务器，保留原有本机草稿冲突处理；明确题号的提示卡片沿用AppTheme。
- 普通API和SSE采用不同keyDecodingStrategy，发现确认提案input可能丢字段；在共同CapabilityProposalBlock解码入口保留原始JSON键后解码，覆盖学习和既有文档确认回归。
- 内部出题/批改ChatRequest没有QCP client_capabilities和客户端上下文，不能获得练习原生工具；保持原模型、配额和鉴权路径。
- Web/QWS复用现有事件注册器输出题组/提示摘要；完整打开题组交互为iOS路径，不声称新增了Web答题页面。

## 验证记录

- /private/tmp/learning-pcm-venv：任务专用venv，安装仓库所需FastAPI版本；系统旧FastAPI/Starlette与httpx0.28冲突，不修改全局环境或仓库依赖。
- 后端回归：tests/test_learning_exercises.py、test_product_capabilities.py、test_capability_gateway.py、test_ios_capability_matrix.py、test_qws_hermes_context.py、test_chat_api.py、test_chat_stream_api.py、test_pcm_jev_routing_contract.py；128 passed。后补签名题组引用篡改拒绝1项通过，共129项。
- 覆盖真实SQLite领域落库、确认前禁止写、持久回执恢复、hint无模型调用、单题合并、辅助标记保留、旧revision/跨账号/撤权/空题/非法输入拒绝、未完成筛选、内部调用无QCP递归。
- iOS Simulator构建成功；新增卡片解码/持久化/签名引用DTO、答案提案重试字段保真；既有题型、文档提案、QCP事件和确认API回归通过（共6个不同定向测试）。结果：/private/tmp/learning-pcm-unit.xcresult、/private/tmp/learning-pcm-ui-final.xcresult。
- SwiftUI ImageRenderer视觉验收：320pt宽卡片文字可读、提示和入口完整；最终题号版测试 /private/tmp/learning-pcm-final-card.xcresult 通过；截图 /private/tmp/learning-pcm-final-card-attachments/D834FA08-2A35-4294-AA1F-C44C5AA5325B.png。
- node --test frontend/tests/learning-capability-events.test.mjs：1 passed，覆盖事件内容、版本fallback和错误renderer拒绝。
- scripts/generate_product_capability_manual.py --check 与 generate_ios_capability_matrix.py --check 通过；新增6项生产回执保持partial，未伪造线上证据。
- git diff --check 通过。模型路由使用现有mock回归，**没有声称真实模型自然语言选择或真机生产验收已通过**。

## 发布状态与授权

本轮用户“那你做吧”按实现任务执行；依据用户当前AGENTS，未要求本地commit默认保留测试后diff。历史“授权完整基线及提示发布”已用于上一轮交付，本任务不将其扩大成未经明确范围授权的新能力生产发布。本轮未commit、push、部署或替换手机现用版本。

## 开工前盘点

用户当前指令“一任务一分支一Worktree”优先于仓库旧AGENTS的main-only规则；使用既有本任务Worktree，未触碰他人worktree。

```text
status: ## codex/learning-chat-pcm-audit-20260927
        ?? ops/change-manifests/learning-chat-pcm-audit-20260927-completion.md
branch: codex/learning-chat-pcm-audit-20260927
HEAD: 9fbc4e0be46714c093bde3336040cfc9e1e69ca3
remote: origin https://github.com/Johnie198946/Quantum.git (fetch/push)
同步: fetch origin main + merge --ff-only FETCH_HEAD，90c8894 → 9fbc4e0b
```

```text
worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/build49-recovery.git
bare

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/build49-learning-quality
HEAD ed85a752074008a743f360d44be6e205dafea9c0
branch refs/heads/codex/build49-learning-quality

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/continue-learning-latency-20260926
HEAD 9214ada52566e191485a1329c24e86e0a44f1dc9
branch refs/heads/codex/continue-learning-latency-20260926

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/exercise-hints-ux-20260926
HEAD 90c889469c91b2e73a70ddadbaee8cbfcbdae9dc
branch refs/heads/codex/exercise-hints-ux-20260926

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/learning-chat-pcm-audit-20260927
HEAD 9fbc4e0be46714c093bde3336040cfc9e1e69ca3
branch refs/heads/codex/learning-chat-pcm-audit-20260927

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/learning-endpoints-20260925
HEAD 9214ada52566e191485a1329c24e86e0a44f1dc9
branch refs/heads/codex/learning-endpoints-20260925

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/learning-latency-feedback-20260926
HEAD cbdea267b06ef086be7e49bfd3313e78e92f70fc
branch refs/heads/codex/learning-latency-feedback-20260926

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/learning-resume-exercise-fix-20260926
HEAD 00a847bbde1a288e053ee60880fe203daa0943b2
branch refs/heads/codex/learning-resume-exercise-fix-20260926

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/mixed-exercise-502-20260926
HEAD 9214ada52566e191485a1329c24e86e0a44f1dc9
branch refs/heads/codex/mixed-exercise-502-20260926

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/reading-selection-build54-20260925
HEAD ed85a752074008a743f360d44be6e205dafea9c0
branch refs/heads/codex/reading-selection-build54-20260925

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/restore-published-catalog-20260925
HEAD 2f62cc4d0a1e7ec83ff0a1c535950d2b0a56eceb
branch refs/heads/codex/restore-published-catalog-20260925

```

## 变更文件

- backend/api/chat.py
- backend/capability_handlers.py
- backend/contracts/product-capabilities/bindings.yaml
- backend/contracts/product-capabilities/events.yaml
- backend/contracts/product-capabilities/ios-scope.yaml
- backend/contracts/product-capabilities/manifest.yaml
- backend/contracts/product-capabilities/policies.yaml
- backend/contracts/product-capabilities/renderers.yaml
- backend/services/capability_catalog.py
- docs/product-capability-coverage.json
- docs/product-capability-manual.md
- frontend/src/features/quantum-workspace/qcpEventRegistry.js
- ios/AIPlatformApp/Models/UIModels.swift
- ios/AIPlatformApp/Networking/APIClient.swift
- ios/AIPlatformApp/Views/Chat/Components/ChatMessageStreamView.swift
- ios/AIPlatformApp/Views/Chat/Components/ChatStatusCards.swift
- ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift
- ios/AIPlatformApp/Views/Chat/Dispatchers/BlockCardDispatcher.swift
- ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift
- ops/acceptance/ios-capability-matrix.json
- scripts/hermes_bridge_runtime/agent_execution.py
- tests/test_ios_capability_matrix.py
- tests/test_learning_exercises.py
- tests/test_product_capabilities.py
- backend/contracts/product-capabilities/learning.yaml
- frontend/tests/learning-capability-events.test.mjs
- ops/change-manifests/learning-chat-pcm-audit-20260927-completion.md

## 授权发布阶段（2026-09-27）

用户明确授权“推送和部署”，本轮提交、推送main、按标准流程部署。开工status为上述27个本任务文件变更，无他人改动。发布前fetch/ls-remote确认main=91b17a0e7d4df579a9e1d36e5ef497084670cc6e；本任务以--ff-only同步该版本，无冲突。
server_before: 91b17a0e7d4df579a9e1d36e5ef497084670cc6e
release_before: /opt/releases/ai-lab-platform-91b17a0e7d4d.LOxwuF
backend_image_before: sha256:41eeb4f2e7a13d88dd6cc8cad32f214fb2555c701bd6d781e318ef09cd571711
frontend_image_before: sha256:434e906683957d5202163205f6cda39e151e95028e13dae690951d92ea2a4e45
8个生产容器healthy。部署将使用共享flock+expected_current_sha；不会回退其他任务已发布内容。同步后129项Python回归通过，1项Linux-only锁测试本机跳过；npm ci --offline和npm run build通过，零新依赖；契约生成检查和git diff --check通过。
当前仍为TESTED，提交/远端SHA/部署证据将在操作后补记。
