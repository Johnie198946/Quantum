# 清理与答题联合真机验收 / TestFlight

task_id: cleanup-exercise-testflight-20260927
status: COMMITTED（联合版本本地提交；发布及完整真机验收待完成）
branch: main
worktree: /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
head/local_commit: 本文件首次所属合并提交，使用 git log --format=%H -- 本文件核验；父提交 5fbd720a7107073d9244b591d2b0e9f837dec28d 与 90c889469c91b2e73a70ddadbaee8cbfcbdae9dc。
remote_sha: fetch origin/main=90c889469c91b2e73a70ddadbaee8cbfcbdae9dc；未推送。
server_before: 90c889469c91b2e73a70ddadbaee8cbfcbdae9dc；/opt/releases/ai-lab-platform-90c889469c91.PXiHjd
server_after: 尚未部署。
health_check: 只读检查 API /ready=ready。
functional_check: 后端202项通过；iOS192项单元测试及1项提示UI测试通过；Build65已安装真机，真实笔记候选/筛选/归档列表已读取，执行链路待后端部署。
rollback_point: 本地5fbd720a；真机原Build64；线上release见server_before，API镜像sha256:ee27040979967d06024b7b8786cfc9230e5b6ddee4eee1d51310ea0eaa581940。
remaining_risks: 线上PCM接口404，尚不能完成清理写入验收；TestFlight未上传；需服务器部署授权及与出版任务协调。

## 开工盘点与授权

用户要求“帮我完成真机验证，完成后与刚刚开发的答题能力一起合并上传testflight”。明确授权整合答题功能、真机安装验证与TestFlight上传。沿用规范仓库main；已识别AGENTS.md既有改动及未跟踪quantum-2.0-hermes-gate-i0-20260909-completion.md，保持原样。
开工HEAD=5fbd720a7107073d9244b591d2b0e9f837dec28d，status main ahead107/behind23；fetch后origin/main=90c8894，behind25。
origin=https://github.com/Johnie198946/Quantum.git；source=https://github.com/Johnie198946/ai-lab-platform.git。本次发布目标origin/main。
唯一worktree=/Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0，branch main。
答题源任务“继续学这里加载很慢，你帮我定位一下原因。”已完成Build64与后端90c8894。此次保留其全部已提交答题、提示、阅读器功能；在其iOS基线上应用清理提交差异，避免界面倒退。

## 合并及验证

- 合入origin/main的25个提交；冲突保留WorkflowClientSessionBinding与WorkflowSchedule两个不同职责模型、出版失败重验/原生审核/已绑定图片校验两侧能力。
- iOS保留Build64基线及清理领域执行，版本1.0.3(65)。真机发现首页旧固定12条文案，改为“查看整理建议”；长同名笔记候选不再重复显示两遍标题，列表限制三行，确认页保留全文。
- 202后端回归涵盖清理、答题、PCM、出版远端/流程/日刊；202 passed / 293.88s。
- 192 iOS单元测试、1提示UI测试，均0 failures。Ruff冲突文件与Python编译、git diff --check通过。
- 已签名Debug构建成功并覆盖安装com.ailab.AIPlatformApp，设备iPhone17Pro/iOS26.6，保留原账号数据。
- 真机读取9组同名笔记建议、3条已归档笔记；尚未更改用户笔记、对话或提交练习答案。线上capabilities接口404，因此执行验证不能假定通过。
- 与出版任务协调：其工作在独立worktree，当前尚无生产代码修改；双方部署前核验expected-current-SHA与发布锁，不覆盖彼此发布。

证据目录：/private/tmp/cleanup-exercise-testflight-20260927/。后续更新生产部署、Archive、上传及Apple回执。

## 2026-09-27 后续发布实录（覆盖上方初始待办状态）

用户已明确授权“推送和部署配套后端”。联合提交 52222059ce1750891d07635366826480392a9d4d 已推送 origin/main，并以 git ls-remote 核对一致。
Release 1.0.3(65) Archive /private/tmp/Quantumn-1.0.3-65.xcarchive 构建成功、codesign 验证通过、已安装真机；可执行文件 SHA256 f4d1dd45aeaf34d28e5887f1259f09996b0613469b5c9d731711f5be814e39f0。TestFlight 尚未上传。

首次标准部署失败并自动回滚，不能标记 DEPLOYED/VERIFIED：generated_artifacts.py 顶层引用 reportlab，但 requirements.txt 与哈希锁缺少此依赖，导致 API 无法启动。旧 release 90c889469c91b2e73a70ddadbaee8cbfcbdae9dc 已恢复，/ready=ready，Bridge /health=ok，全部 Compose 容器 healthy。
回滚点 /opt/ai-lab-shared/rollbacks/cleanup-exercise-52222059：release.before、api-image.before、offline-images.attested.before、database-before.sql.gz；数据库备份 SHA256 d2f0e48446024fb1bb3fcf7813e9248250653a9bdec7c71e25ed1f149b73c43f。旧 API 镜像 sha256:ee27040979967d06024b7b8786cfc9230e5b6ddee4eee1d51310ea0eaa581940。

依赖修复只添加已使用的 reportlab==4.4.5 及 resolver 生成的 wheel/sdist 哈希，保持全部原锁版本。wheel SHA256 849773d7cd5dde2072fedbac18c8bc909506c8befba8f088ba7b09243c6684cc。补充依赖契约测试；答题路由检查从 app.routes 内部枚举改为真实 HTTP 未认证请求返回401，兼容生产嵌套路由并验证实际入口。
隔离镜像 ai-lab-platform-api:cleanup-deps-check 已通过 pip check、import backend.main、5项清理测试、11项PDF/依赖测试、2项实际学习路由/提示测试。完整仓库测试首次因 API 镜像不含架构上独立的 hermes_cli 而不能收集；不得宣称全仓库通过。跨 Bridge 回归采用已有 Hermes 源模块只读挂载，网络禁用、空临时DB/vault/HOME，无生产数据挂载；发布相关完整回归结果随后补记。

此次修复开工盘点：HEAD/main=52222059；origin/main一致；唯一worktree为规范路径；origin/source见上；保留 AGENTS.md、既有hermes manifest以及并行笔记UX任务五个Swift文件和其manifest，不暂存或混入Build65。本修复只涉及requirements.txt、requirements.lock、tests/test_backend_dependency_contract.py、tests/test_learning_exercises.py及本manifest。
