# Publication standard workflow completion

- task_id: publication-standard-workflow-20260926
- goal: 将选题、写作、审核和发行复用既有主链路标准化，程序字段与可增删内容主题分离。
- status: PUSHED（远端分支SHA已核对；待部署及真实生产验收）
- branch: codex/publication-standard-workflow-20260926
- worktree: /Users/dengzhaoyu/Documents/AI Lab/.worktrees/publication-standard-workflow-20260926
- head/local_commit: 81ab5eef7b2721391fd778718bc1c4fedc3b6cef（出版物实现；上游基线52222059）

## 开工前盘点

实际源码仓库 /Users/dengzhaoyu/Projects/quantum-2.0-publication-main：main，HEAD 2d893130d629615144a8319e7ca25b04073dc7e5；未跟踪 build_20260924_issues.py、data/，未触碰。origin=https://github.com/Johnie198946/Quantum.git。只读 fetch/ls-remote 确认 origin/main cbdea267b06ef086be7e49bfd3313e78e92f70fc，创建独立任务分支及 worktree，开始修改前该 worktree clean。其他 worktree quantum-jev-research-egress-20260923、story-port-review-20260926 保持原状。初始 AI Lab 工作区的用户改动未触碰。

## 修改范围与复用

复用 PublicationStore、现有 JSON 配置、Workflow execution/artifact、交接与 revision outbox、原生审核证明、recovery_claims。修改 8 个已有 Python 主路径和配置；扩展已有测试及新增配置多时段集成测试，更新既有作者/素材/审核提示词责任分工，补一份标准流程 runbook。未增加依赖、第二套服务、调度器或业务数据库。恢复账本仅增加审计历史列。

主题启停/时段/体裁/绑定改为配置；系统字段由程序派生；原作者身份绑定不可被素材 agent 替换；前期期次可回收；正文预检返修有持久化和上限；按期次验收；暂停与耗尽显式失败；精确 claim 可审计恢复。

## 测试与校验

边界回归 tests/test_publication_editorial_workflow.py + tests/test_publication_reader_projection.py：36 passed；Ruff 与 git diff --check 通过。主路径 7 文件回归：232 passed（268.37s）；合计 268 passed，无失败，4 项既有 Pydantic 弃用告警。原生 Hermes 下一分钟自动触发隔离集成：95 passed（11.23s），非生产验收。早期两处旧断言已按新期次字段及未到期语义修正；独立审查发现的问题均按实际调用链补回归，不放宽质量与证明门禁。

## 运行态与外部写入

- remote_sha: 81ab5eef7b2721391fd778718bc1c4fedc3b6cef（origin/codex/publication-standard-workflow-20260926）
- server_before: 本任务未部署；前次诊断记录 .deployed-sha 00a847bb，运行容器 revision cbdea267。最终激活前必须重新盘点，不能当作当前保证。
- server_after: 已授权，等待并发部署恢复；本任务尚未部署。
- health_check: 未执行新版本服务器健康检查。
- functional_check: 本地测试及 Hermes 原生定时隔离验收；生产端到端尚未执行。
- rollback_point: 本地基线 cbdea267；生产部署前必须另建可恢复快照。
- commit SHA: fa4f0d8c9a0331bd72971529dbb1746837935c9b、81ab5eef7b2721391fd778718bc1c4fedc3b6cef。
- GitHub remote/ref/SHA / ls-remote: git ls-remote origin refs/heads/codex/publication-standard-workflow-20260926 返回81ab5eef7b2721391fd778718bc1c4fedc3b6cef，与本地HEAD一致。

## 原生定时验收记录

- 第一次 job db6d7d70e89d，execution e762c3125cbc40429700e515b55b3f9b，于 2026-09-27 00:12:46+08 自动触发；保存报告目录不存在而失败，已清理任务并修正路径。
- 第二次 job 8b86d2bd07a7，execution 9ccbdf85da764536a6cc686cba559fd3，于 00:16:33+08 自动触发；92 passed、3 failed。真实 cron 的 Workflow 绑定环境泄漏进测试，影响期望分支；保留失败证据 ops/reports/publication-standard-timed-check-attempt2.json。已修复测试环境隔离，生产逻辑未改为绕过门禁。

- 第三次 job 05f87e476bf6，execution 8258662f596347dead8b46bb48ac50ec，于 2026-09-27 00:20:07.840698+08 自动触发；00:20:21 完成，95 passed、exit_code=0；原生执行状态 completed。证据 ops/reports/publication-standard-timed-check.json，production_acceptance=false。三个临时任务和本任务安装的临时脚本均已清理。
- 独立审查共 4 轮，最后一轮无新增实质问题；具体修复覆盖真实配置格式默认值、作者会话前缀、前期取稿、未来主题日期与审核策略统一强制。

## 风险与未完成项

1. 用户已授权提交、推送、部署、运行配置与真实定时出版。生产验收前只能报告本地测试通过。
2. 原生 default/Story 作者与 default/supervision 独立审核绑定已经实现并通过回归；运行脚本仍待同版安装，旧无效通知路由与暂停任务须由既有 CLI 修复。
3. 当前临时启用 ai-toolkit/tang-history 的 00:01 发行 slot，真实验收后须移除，不保留额外日常发行。
4. 真实作者、五图、独立审核、发布及读者回读尚未发生；之前定时测试仅合成集成验收。
5. 新增栏目复用配置与既有作者/素材/审核 job；启停保留历史元数据，服务端与本地必须同步同版配置。
6. 并发任务在部署52222059时发现reportlab漏列生产依赖，已回滚至90c8894并修复中；本任务等待其明确释放部署窗口，不能覆盖共享镜像标签。

回滚：保留独立 worktree、已有服务器SQLite在线备份与8镜像保留标签、本机cron/配置/脚本备份。正式部署前根据并发任务最终SHA重新建立回滚点。不得撤销或混入别的任务改动。

## 文件清单

- `backend/services/knowledge_publication_store.py`
- `backend/services/publication_workflow_handoff.py`
- `config/quantumn-daily-publication.json`
- `docs/prompts/quantumn-editorial-v2.md`
- `docs/runbooks/publication-standard-workflow.md`
- `ops/change-manifests/publication-standard-workflow-20260926-completion.md`
- `ops/reports/publication-standard-timed-check-attempt2.json`
- `ops/reports/publication-standard-timed-check.json`
- `scripts/publication_daily_completion.py`
- `scripts/publication_editorial_remote.py`
- `scripts/publication_operator.py`
- `scripts/publication_release_remote.py`
- `scripts/publication_scheduler_watchdog.py`
- `scripts/publication_workflow_handoff.py`
- `tests/test_daily_publication.py`
- `tests/test_publication_editorial_remote.py`
- `tests/test_publication_scheduler_watchdog.py`
- `tests/test_publication_topics.py`
- `tests/test_publication_workflow_handoff.py`
- `ops/reports/publication-standard-tests.txt`

## 授权部署阶段补充

用户明确授权提交、推送、部署、运行配置及真实定时验收。远端新增无重叠学习/iOS提交，任务分支以 --ff-only 快进到 90c889469c91b2e73a70ddadbaee8cbfcbdae9dc，保留本任务修改。服务器并发部署结束后核验当前 release=/opt/releases/ai-lab-platform-90c889469c91.PXiHjd、marker/image revision 同为90c8894。回滚备份 /opt/ai-lab-shared/deploy-backups/publication-standard-workflow-20260926 保存8服务镜像ID及保留标签、attestation、SQLite在线备份；本机备份 ~/.hermes/backups/publication-standard-workflow-20260926。

生产前发现远端 Workflow 原生会话不能满足本机 Story 身份证明；修复改为复用已有原生作者→content-only builder→原生独立审核→store路径，补程序读取真实cron内容与profile派发；不新增Runtime/数据库。日期时隙以程序注入的 PUBLICATION_CONTENT_REQUEST 绑定，作者不能自报。新增原生内容任务 b52aa900ac12 与监督审核 0dd3884f173c，创建后暂停，待同版安装激活。

部署前运行环境补充：Hermes自带Python缺少SQLAlchemy，不能把源码直接交其解释器执行。安装时复用本机已通过测试的 Python 3.12（现有依赖），原生cron脚本以薄启动器exec同版源码，统一PYTHONPATH和子进程Python，不新建依赖环境。

## 最终集成回归（激活前）

基于上游52222059完整运行10个测试文件：396 passed、4 failed、1 Linux-only skipped；4失败均为夹具未指定多时隙/Story审核profile，修正后4用例全部passed。合计400项主回归通过。拒稿修订2与动态主题10项专题回归另行通过。Linux inherited-lock测试在真实服务器隔离临时路径完成6边界case，通过；本地跳过不伪报。Ruff及git diff/check通过。独立原生链路审查3轮收敛、部署脚本审查2轮收敛。

激活前真实目录检查发现9/26旧Workflow waiting_assets残留且无manifest；两本地入口共用当前配置路由过滤，保留旧稿与审计字节，防止迁移后阻塞。17项专项回归通过；实际assets-input只读扫描旧目录返回NO_NEW_DRAFT。运行启动器额外固定并验证profile/HERMES_HOME，6个隔离case通过，二轮复核无新增阻断。
