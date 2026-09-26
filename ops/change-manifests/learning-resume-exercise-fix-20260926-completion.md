# 当前交付记录（2026-09-26 第二轮修复）

task_id: learning-resume-exercise-fix-20260926
status: TESTED（第二轮本地测试通过；首轮 6129442 已 DEPLOYED，真机发现后续 schema 规则遗漏，尚未 VERIFIED）
branch: codex/learning-resume-exercise-fix-20260926
worktree: /Users/dengzhaoyu/Documents/AI Lab/.worktrees/learning-resume-exercise-fix-20260926
head/local_commit: 首轮 6129442f6d72b45adb56152f2afa55c9eb54b96b；已 fast-forward 到并行任务 2d893130d629615144a8319e7ca25b04073dc7e5，待提交第二轮
remote_sha: 首轮 git ls-remote origin refs/heads/main=6129442f6d72b45adb56152f2afa55c9eb54b96b；后续主线=2d893130d629615144a8319e7ca25b04073dc7e5
server_before: 9d45436c1474c79583090fcf7a19e5f2f706b7b8
server_after: 首轮部署 6129442f6d72b45adb56152f2afa55c9eb54b96b，/opt/releases/ai-lab-platform-6129442f6d72.OqURKC
health_check: 标准 update.sh 成功退出；API ready、Bridge ok、runtime contract audit passed、全部 8 容器 healthy
functional_check: 真机 Build 63 恢复书籍与16%进度；读取题组200；出题 Bridge200，但判断题缺失 options/correct_ids/option_explanations 导致校验502，第二轮待验收
rollback_point: /opt/releases/ai-lab-platform-9d45436c1474.s7PYde；旧镜像 bdd366f914fd；备份 /opt/ai-lab-shared/rollbacks/learning-6129442.IZjzeC 与 update-6129442f6d72-units.1790433992.2784724
remaining_risks: 第二轮待推送部署真机验证；AI计划生成耗时保留；首轮验收被另一项部署/回滚打断，用户现已暂停其他部署。

## 第二轮依据与验证

- 首轮发布精确源码归档 SHA256=dad0cd1d5ecf5803ca861de6bf97c7b182bbbdbb288ba9e9c35eecff5d307abd；镜像 sha256:e2d8d0b52e678bd0d1266bcff68709268a1eacb7c0b5d5052653b832632ce581，三处运行时文件哈希与 Git 一致。
- UTC14:56:16 真机 GET learning-exercises 200；14:57:19 Bridge POST /v1/chat 200；14:57:20 出题502。模型输出3196字、finish_reason=stop，非截断；GeneratedSet 对 questions[1] 报 invalid options/key。
- 真实输出 judgement 缺少三个默认空字段。JSON schema 没有表达 Python after-validator 的条件要求。第二轮仅给既有 Question 四个字段补描述，显式说明选择/判断选项与答案、逐选项解释、主观题评分规则；严格校验保持不变。
- 追加 backend/api/learning.py、tests/test_learning_exercises.py。回归模拟真实缺字段错误并验证失败记录可重试，检查实际发送给模型的 schema 带规则；39项 learning/chat_reasoning/publication_handoff 测试通过，包含最大prompt预算；全仓库Ruff和diff检查通过。
- 第二轮修改前盘点：工作区干净，branch如上，HEAD=6129442；origin仍为Quantum仓库；worktree列表与历史记录一致。Fast-forward到2d89313，保留其他任务的publication_handoff改动，不改写历史。

---
以下为第一轮各阶段历史记录；当前状态以上方及后续实际验收记录为准。

# 修复学习恢复慢与混合练习 502

task_id: learning-resume-exercise-fix-20260926
status: TESTED（216 项相关回归、全仓库 Ruff 与 diff 检查通过，待发布）
branch: codex/learning-resume-exercise-fix-20260926
worktree: /Users/dengzhaoyu/Documents/AI Lab/.worktrees/learning-resume-exercise-fix-20260926
head/local_commit: 02a322873fee46fbfbac29fb13692840f8e2a5ac；本任务未提交
remote_sha: 已 fetch origin main 得到基线 02a322873fee46fbfbac29fb13692840f8e2a5ac；未执行推送及 ls-remote，不声称 PUSHED
server_before: 上轮只读核对 .deployed-sha=02a322873fee46fbfbac29fb13692840f8e2a5ac
server_after: 未授权、未执行部署；本任务未修改线上代码或服务
health_check: 未执行部署后健康检查（没有部署）
functional_check: 定向回归与真实公共书籍的隔离前后对比通过；真实模型出题、真机端到端未执行
rollback_point: 02a322873fee46fbfbac29fb13692840f8e2a5ac 源码基线；无线上修改，无生产回滚点需求
manifest: ops/change-manifests/learning-resume-exercise-fix-20260926-completion.md
remaining_risks: 待推送、部署与真机验收；客户端自动计划生成耗时仍保留。

## 目标与实现

用户起初授权修复；后续明确授权“推送、部署并真机测试”，包括本次修复提交。复用已有接口，无新依赖、缓存服务、数据库模型或第二条模型调用链。

### 混合练习 502

`backend/api/chat.py`：非流式 `_call_hermes` 复用已有 `_bounded_knowledge_query`，发送到 Bridge 的检索字段最多 200 字符；原有完整 goal 独立保留，练习 prompt 已有 11500 字符上限，因此出题 schema/证据不因本修复被截掉。Bridge 非 200 现在抛出 HTTPException，保留上游状态的安全描述，不再把错误文本作为模型答案返回。外层 chat 在既有计费收尾之后保留该错误，题组解析器不会把桥接故障误报成模型 JSON 格式错误。

### 继续学恢复慢

`backend/api/subscriptions.py:learning_resume`：按当前 tenant/user 的 last_read_at 查询已保存的书籍检查点，逐个通过现有 `_available_book_body` 实时授权和完整性门禁。成功时只读取目标书籍，跳过全部书架构建及两次完整出版目录复核。404（下架、无权、正文不可用）尝试下一个检查点；其他故障原样传播。版本变化时复用 `_book_subscription` 清除旧版段落/字符位置。没有阅读记录直接返回空值。

恢复接口使用真正保存过的书籍位置，避免原路径先将连载替换成最新未读一期。书架的“自动显示最新一期”行为仍由原 my_book_subscriptions 实现，本次不更改。

范围说明：当前 GitHub main 的 iOS 尚未包含真机 Build 63 学习页；完整客户端版本存在 reading-selection-build54-20260925 的大量未提交改动中。本任务不混入该任务的前端改动。服务端接口保持原响应结构，已安装客户端可直接受益。前端重复请求、串行正文加载以及每次进入自动生成计划尚未优化，模型计划耗时仍在；本次移除的是已实测的服务端数秒扫描瓶颈。

## 变更文件

- backend/api/chat.py
- backend/api/subscriptions.py
- tests/test_chat_reasoning.py
- tests/test_chat_api.py
- tests/test_book_subscriptions.py
- 本 manifest

## 开工前盘点

- 起始诊断 worktree codex/mixed-exercise-502-20260926，HEAD 9214ada，只有该任务未跟踪 manifest；未覆盖。
- git fetch origin main 成功，FETCH_HEAD=02a322873fee46fbfbac29fb13692840f8e2a5ac，与先前只读确认的服务器版本一致。
- 创建独立 branch/worktree，初始 git status --short --branch 只有 `## codex/learning-resume-exercise-fix-20260926`，干净。
- git branch --show-current: codex/learning-resume-exercise-fix-20260926
- git rev-parse HEAD: 02a322873fee46fbfbac29fb13692840f8e2a5ac
- 用户在当前会话明确要求一任务一分支一 worktree，优先于历史子目录 main-only 文本。
- reading-selection-build54 的前后端未提交修改、其他工作区的报告等均保持原状。

```text
origin	https://github.com/Johnie198946/Quantum.git (fetch)
origin	https://github.com/Johnie198946/Quantum.git (push)

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/build49-recovery.git
bare

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/build49-learning-quality
HEAD ed85a752074008a743f360d44be6e205dafea9c0
branch refs/heads/codex/build49-learning-quality

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/continue-learning-latency-20260926
HEAD 9214ada52566e191485a1329c24e86e0a44f1dc9
branch refs/heads/codex/continue-learning-latency-20260926

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/learning-endpoints-20260925
HEAD 9214ada52566e191485a1329c24e86e0a44f1dc9
branch refs/heads/codex/learning-endpoints-20260925

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/learning-resume-exercise-fix-20260926
HEAD 02a322873fee46fbfbac29fb13692840f8e2a5ac
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

## 验证

1. 首轮 `PYTHONPATH=. python3 -m pytest -q tests/test_chat_reasoning.py tests/test_book_subscriptions.py tests/test_learning_exercises.py --tb=short`：37 passed。
2. 扩展到 test_chat_api.py、test_chat_stream_api.py、test_chat_status.py、test_daily_publication.py、test_publication_reader_projection.py：209 passed / 2 failed。两项分别为 test_stream_records_exact_usage、test_stream_cancel_keeps_reservation_pending。
3. 以 `git archive HEAD` 导出未修改基线到 /private/tmp/learning-fix-baseline-l5nwvggh，运行同组命令：205 passed / 同样 2 failed。说明四个新增测试通过，合跑失败在基线已存在。
4. 两项失败测试单独运行于修复工作区：2 passed。未宣称全套合跑全绿，未改动不相关计费逻辑。
5. 修改文件的 Ruff、compileall、git diff --check：通过。
6. 全仓库 `python3 -m ruff check backend/ scripts/ tests/`：仅既有 backend/services/knowledge_policy.py:172 F841 entitlement_version 未使用。未修改基线同文件复现同一告警。
7. 新增覆盖：实际 Bridge GoalRequest 模型验证 200/201 字符及真实题组 schema 场景；完整 goal 不变；非 200 不进入答案解析且不泄漏错误体；HTTP 层保留安全错误；恢复接口不构造全目录、只读最近账号检查点、用户/租户隔离、下架回退、换版清除锚点和非 404 故障传播。

## 性能对比方法与结果

在生产 API 容器内的独立诊断 Python 进程中，读取同一本已公开书籍；数据库接口替换成只读内存检查点 fixture，不访问或修改用户的实际检查点。新函数仅在诊断进程的独立 namespace 中执行，没有写入线上源码、注册到在线路由或重启服务。通过包装 PublicationStore.published 计数，旧函数和新函数依次读取同一公开内容。

| 轮次 | 原函数 | 新函数 | 原全目录扫描 | 新全目录扫描 |
|---|---:|---:|---:|---:|
| 1 | 2.190s | 0.081s | 2 | 0 |
| 2 | 2.358s | 0.132s | 2 | 0 |

两轮均断言完整返回对象相等。此数据证明已定位公共出版书籍路径的扫描成本被消除，不是端到端手机速度或真实数据库延迟承诺；未包括网络、SwiftUI 渲染、AI 计划生成。若是旧 Wiki 书籍，其现有正文读取门禁仍可能构建书目；本任务未扩展该不同来源路径。

## 交付与后续边界

本地修复可审查，未 commit/push/deploy；不声称已上线或手机已生效。部署前需按用户 AGENTS 要求取得明确授权、处理/确认既有门禁失败、建立回滚点、核对远端 SHA，并进行真实出题及读取验收。由于没有生产写入，本次回滚仅涉及本任务上述文件的补丁，不涉及任何用户数据。

## 2026-09-26 真机验收准备（用户已授权发布）

- 真机连接：iPhone 17 Pro，CoreDevice CFE79F35-1270-527D-8BD7-9AB60449B6DF，Quantumn 1.0.3 (63)。镜像已由用户解锁。
- 发布前其他任务已部署 9d45436c1474c79583090fcf7a19e5f2f706b7b8。已 fetch 并以 fast-forward 将本分支同步到该 SHA，保留 workflow 空知识范围修复，本任务未改写历史。
- 实际发布前 rollback baseline：/opt/releases/ai-lab-platform-9d45436c1474.s7PYde；API 镜像 sha256:bdd366f914fdfe207dff93df43e89d10742e23908fee924f35e3644d7ad8d16a，标签源码版本与 marker 一致。
- 合跑失败经 pdb 定位为 inference_quota_exceeded：前面用例耗尽共享 user_id=1 的额度。仅给两个流式计费测试独立测试账号，保留真实额度检查与计费逻辑。追加修改 tests/test_chat_stream_api.py。
- 删除 backend/services/knowledge_policy.py 两处无任何读取的 entitlement_version 局部赋值，消除全仓库 Ruff F841；不改变权限计算。追加修改该文件。
- 重新完整合跑相关 8 个文件：211 passed；test_knowledge_policy_v2.py：5 passed；全仓库 Ruff：All checks passed；git diff --check：通过。既有合跑失败已解决。
- 不修改或重装客户端；沿用手机已安装的 Build 63 连接即将部署的修复服务端。
