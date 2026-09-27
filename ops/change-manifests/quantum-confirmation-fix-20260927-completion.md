# Chat 确认会话与工作流解析修复

task_id: quantum-confirmation-fix-20260927
status: TESTED
branch: codex/quantum-confirmation-fix-20260927
worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/quantum-confirmation-fix-20260927
head/local_commit: b9e4d128dd5839bae89cff39790fb8240297e23e / 本任务未提交
remote_sha: 本任务未推送，未执行 ls-remote；origin/main 仅作为 fetch 后基线
server_before: 未访问，本任务未核验
server_after: 未部署（无授权）
health_check: 未执行（无部署）
functional_check: 本地后端 163 项、iOS 模拟器 6 项通过；线上和真机未验
rollback_point: 本地基线 b9e4d128dd5839bae89cff39790fb8240297e23e；无本任务服务器回滚点

## 目标与已验证原因
截图 IMG_3355 的 Confirmation session mismatch 由 capability_gateway 在执行前校验 proposal.session_id 时返回。Chat 的两个入口注册过客户端会话（0704ddf5），但转发到 Hermes 的普通和 SSE 请求没有传递既有 client_session_id 字段；runtime 在没有 transcript 时回退内部隔离会话，导致与 iOS 消息的原始 sessionId 不一致。未取得本次线上 proposal 记录，不声称已核验其实际 ID；新增回归证实此路径存在。
iOS 另将能力业务错误包装成 APIError.network，造成“网络不可用”误报；旧错误卡未将 session mismatch 作为重新提案条件。
截图 IMG_3354：compositionManifest.planId 为强制 String，缺失导致整个工作流列表解码失败；服务端持久化 manifest 原样输出，planId 没有执行消费者，改成可选兼容缺失与 null。

## 复用与变更文件
- backend/api/chat.py：复用普通/流式转发及 recorded wrapper，显式传递 req.session_id 为 client_session_id；内部隔离 session_id 保持独立。
- ios/AIPlatformApp/Networking/APIClient.swift：WorkflowAgentCompositionDTO.planId 可选；既有 QCPErrorDTO 实现 Error/LocalizedError，保留业务错误并提示重新确认。
- ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift：复用新提案恢复路径，识别旧英文和新中文 mismatch；不自动确认新提案。
- tests/test_chat_stream_api.py：扩展现有注册会话测试，覆盖两入口、有/无 transcript，并验证实际 HTTP 转发体。
- ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift：解码兼容、错误提示、旧卡重新提案及必须再次确认测试。
- 本 manifest。
无新依赖、服务或平行调用链；gateway 会话/token/租户/版本校验未放宽。未执行真实笔记删除。

## 协调与开工盘点
用户明确授权“你协调吧”。已与图片、清理联合交付、笔记任务协调编辑范围，相关任务让出文件。联合协调任务指定以 b9e4d128 为当前联合基线，保护图片 doc_/ga_ 上传和旅行/阅读能力。
用户直接给出的一任务一分支/Worktree要求优先于仓库旧 main-only 文本；按协调结果隔离修改。
Codex create_worktree 绑定本 chat 的旧 AI Lab 仓库且无目标仓库参数，无法在 Quantum 仓库使用；因此对目标仓库使用 git worktree add。
规范目录 /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0 原状为 main@21250c7b8a5290abcf649b9279bbd91b9af1db88，behind origin/main 19；有图片/笔记/工作流等多任务脏文件，未更新、还原、暂存或提交它们。
fetch origin main 成功后，在新 Worktree 开工盘点：
- git status --short --branch: ## codex/quantum-confirmation-fix-20260927...origin/main；无修改
- git branch --show-current: codex/quantum-confirmation-fix-20260927
- git rev-parse HEAD: b9e4d128dd5839bae89cff39790fb8240297e23e
- git remote -v: origin=https://github.com/Johnie198946/Quantum.git；source=https://github.com/Johnie198946/ai-lab-platform.git（均 fetch/push）
- git worktree list --porcelain（本任务建立后）：
```
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

```
之前在旧 ai-lab-platform 检出的 workflow-notes-fix 补丁已被本任务在正确联合基线上实现的修复取代；旧补丁未提交、未发布，不应合入。

## 验证命令与结果
后端沿用联合任务已有 /private/tmp/cleanup-test-asgi FastAPI/Starlette 兼容运行目录，无安装或依赖修改。

```sh
PYTHONPATH=/private/tmp/cleanup-test-asgi:. python3 -m pytest tests/test_chat_stream_api.py -q -k 'binds_client_session or transports_preserve_client_session'
```
修复前：6 failed，4 项缺少 client_session_id、2 项传输函数未接收字段。修复后纳入以下通过测试。

```sh
PYTHONPATH=/private/tmp/cleanup-test-asgi:. python3 -m pytest tests/test_chat_stream_api.py tests/test_capability_gateway.py tests/test_product_capabilities.py -q
PYTHONPATH=/private/tmp/cleanup-test-asgi:. python3 -m pytest tests/test_chat_api.py -q
PYTHONPATH=/private/tmp/cleanup-test-asgi:. python3 -m pytest tests/test_cleanup_capabilities.py tests/test_client_session_notes.py -q
```
分别 77 passed、21 passed、65 passed，共 163；日志 /tmp/quantum-confirmation-related.log、/tmp/quantum-confirmation-chat-api.log、/tmp/quantum-confirmation-notes.log。
首次将前两组同进程合跑为 97 passed / 1 failed：test_non_stream_chat_forwards_quote_and_signed_active_document_context 返回 inference_quota_exceeded (429)。单独运行同文件 21 passed，记录测试间共享额度限制，未修改产品额度规避。日志 /tmp/quantum-confirmation-python.log。

```sh
xcodebuild test -project ios/AIPlatformApp.xcodeproj -scheme AIPlatformApp   -destination 'platform=iOS Simulator,id=C284B362-5DB0-498E-A26C-BF0A128D566C'   -derivedDataPath /tmp/quantum-confirmation-derived   -only-testing:AIPlatformAppTests/WorkflowLifecycleDTOTests/testCompositionDecodesMissingNullAndPresentPlanId   -only-testing:AIPlatformAppTests/WorkflowLifecycleDTOTests/testConfirmationMismatchIsActionableAndRefreshable   -only-testing:AIPlatformAppTests/WorkflowLifecycleDTOTests/testCapabilityRetryCreatesFreshProposalOnlyForStaleAuthority   -only-testing:AIPlatformAppTests/ClarifyAnswerPaginationRegressionTests/testSessionMismatchRetryRequiresAnotherConfirmation   -only-testing:AIPlatformAppTests/ClarifyAnswerPaginationRegressionTests/testFailedCapabilityProposalWithoutTokenFailsClosedAndCanDiscard   -only-testing:AIPlatformAppTests/ClarifyAnswerPaginationRegressionTests/testCapabilityCompletionAfterTenantSwitchHasNoSideEffects   CODE_SIGNING_ALLOWED=NO
```
完整编译 + 6 tests / 0 failures。包括断言重试只调用 proposals 且新卡状态 awaitingConfirmation，没有调用 confirm；使用原客户端 session_id。日志 /tmp/quantum-confirmation-xcode-final.log；xcresult /tmp/quantum-confirmation-derived/Logs/Test/Test-AIPlatformApp-2026.09.27_22-01-40-+0800.xcresult。

```sh
python3 -m ruff check backend/api/chat.py tests/test_chat_stream_api.py
git diff --check
python3 -m ruff check backend/ scripts/ tests/
```
前两项通过。全仓 ruff 11 项既有 F811：scripts/hermes_bridge_runtime/{agent_config,endpoints,session_runtime}.py；读取 HEAD 对应原始文件经 ruff --stdin-filename 复核同样失败，未改这些文件。日志 /tmp/quantum-confirmation-ruff.log 与 /tmp/quantum-confirmation-ruff-baseline.log。未运行全仓 pytest 和无关前端构建。

## 剩余风险与回滚
- status TESTED 仅指上述本地相关验收通过；全仓 lint 仍受已有错误阻塞。
- 尚未提交、推送、部署或上传 TestFlight，用户当前安装版本仍未获得修复。
- 旧错误卡需新客户端重新生成提案并由用户核对确认；本补丁不修改历史签名或已有提案记录。
- 需联合发布任务审阅整合；线上真实提案与真机功能仍待验证。
- 本地回滚仅移除本 Worktree 列出的本任务差异；其他 Worktree/main 不变。
