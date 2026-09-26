# Publication standard workflow completion

- task_id: publication-standard-workflow-20260926
- goal: main 与 Story 无监督选题、写作、审核和发行；程序字段与可增删内容主题解耦。
- status: DEPLOYED（0832 真实双链路验收通过；临时时隙清理已 TESTED，最终部署与运行态恢复待完成）
- branch: codex/publication-standard-workflow-20260926
- worktree: /Users/dengzhaoyu/Documents/AI Lab/.worktrees/publication-standard-workflow-20260926
- head/local_commit: 0832e95ae252a99ecf8e17b44f85b67346e6f783；后续配置清理与验收记录待提交。

## 开工前 Git 盘点

实际源码仓库 /Users/dengzhaoyu/Projects/quantum-2.0-publication-main：main，HEAD 2d893130d629615144a8319e7ca25b04073dc7e5；status 含未跟踪 build_20260924_issues.py、data/，未触碰。origin=https://github.com/Johnie198946/Quantum.git。只读 fetch/ls-remote 确认 origin/main cbdea267b06ef086be7e49bfd3313e78e92f70fc，随后创建独立任务分支及 worktree，开始修改前任务 worktree clean。其他 worktree quantum-jev-research-egress-20260923、story-port-review-20260926 保持原状。初始 AI Lab 工作区用户改动未触碰。上游学习、清理 b74 和笔记 05a 改动均保留。

## 复用与变更范围

复用 PublicationStore、既有 JSON 配置、Workflow execution/artifact、交接和 revision outbox、原生审核证明、recovery_claims、原生 Hermes cron。未新增依赖、第二套调度器、服务或业务数据库。恢复账本仅增加审计历史列。

主要文件：config/quantumn-daily-publication.json；backend/services/knowledge_publication_store.py、publication_review_provenance.py、publication_editorial.py、publication_workflow_handoff.py；scripts/publication_editorial_remote.py、publication_operator.py、publication_scheduler_watchdog.py、publication_workflow_handoff.py 及既有发行入口；既有作者/素材/审核 prompts、相关 tests、docs/runbooks/publication-standard-workflow.md 和本任务 ops/reports。精确文件与演进由任务分支提交记录核验。

- 作者只交标题、摘要、正文、来源和必要的真实执行材料。主题、期次、身份、brief/objectives、权利及控制字段由程序派生；素材角色不能替换原作者身份。
- 主题启停、体裁、时段、角色绑定统一配置；下线用 enabled=false，保留历史。正常主栏目 12:00，Story 08:00/13:00/20:00，共七个每日期次。
- 采集至少一个可用候选即可成功，saved/queued/compiled 分开。01:00 采集，目标02:00收据、03:00编译；作者实际开工冻结输入，新候选未编译可用既有授权知识，不能以采集收据冒充正文。
- watchdog 每2分钟按期次接力，素材每5分钟、独立审核每10分钟、到期发行每5分钟；固定作者 cron 为额外唤醒。拒稿回原作者，有界返工；基础设施重试不冒充内容修订。
- main 使用默认独立审核，Story 使用真实 story 作者与 supervision 审核。启动器固定 Python、profile 和同版源码；通知保持 local。

## 根因与修复证据

1. 系统字段与内容合同混用，导致作者被反复要求修补控制信息；现由既有主路径生成。
2. 本机原生 cron 与服务器 Workflow 身份、角色暂停状态、恢复预算、通知路由及运行环境不一致；现按真实 profile 执行账本接力，暂停和耗尽明确报错。
3. 历史坏稿、非中午期次退化、共享角色选错目标会阻塞后续稿；现使用精确 issue_key、材料哈希和配置路由，历史记录保留。
4. 图片调用入口、大小规范和真实生成记录缺少统一约束；现五图及生成证据进入联合审核目标。
5. 重投曾把旧审核缺口直接标 resolved；现冻结合同保留 open，独立签名 review 逐项提供 gap_resolutions（补证或正文明确收缩范围），全部通过后才关闭服务端账本。真实 main 第3版被发现 EOF 字节导致脚本哈希不一致，自动返修第4版后通过。
6. Story 审核将北京时间 05:35 误标为 UTC，系统错误信任模型 reviewed_at，导致未来时间拒收。0832 修复为完整验签后从 native_ended_at 生成 UTC。原 review/proof/合同/正文哈希完全不变；历史已发布稿重试保留冻结 envelope。
7. 来源 URL 提取中文括号边界问题已修复；不回写旧冻结材料。

## 真实原生定时验收

- 初始真实下一分钟任务 a8a830958fb6：01:57:34 自动执行，触发 main 与 Story 原生作者。较早一次隔离触发因报告目录缺失失败，修复后重测；隔离 fixtures 不冒充生产验证。
- 维护恢复任务 8ff246d01888、6c4c454890e9 与 ea574986acc4 均归档回执后删除。过程中发现系统问题、暂停修复并定时恢复，因此不声称原测试全程未中断。
- main：原生作者 b52aa900ac12，独立审核 fbd1cd1217d7；同一期自动拒稿返工至 revision4，签名批准后自动发行。publication-234c61fdd8aacdf10057f6d6c6434fc8，edition-8ea548b0e71c58c6389c6a1e0f996ee7，2026-09-27 05:20:44+08 发布。
- Story：原生作者 d3e461e0578c，supervision 审核 0dd3884f173c，revision1、attempt-a026c48ee0014404ba4524de2daaacf3。时间修复恢复任务计划06:04:14、实际06:04:32启动；控制器7d7c955f30394f239f18be6fb871c392完成，发行9aa0d52317464a8fae4745284a2a9577完成。publication-40380deb936907737fda3763801a2a5c，edition-da58df44faaaa3a4730e02402da4cb94，06:05:56+08自动发布。
- Story 程序审核时间为2026-09-26T21:36:14.858036+00:00，来源为已签名 native_ended_at；未改原审核错误时间，未重置失败次数，未伪造通过。
- 两篇各11节，尾节完整，正文API与全部10媒体返回200、哈希一致；main7个代码块字节完全保留。两次重复发行均无新版本/发布，前后edition与审核记录完全相同。
- 回读使用隔离 ASGI 进程读取生产数据；未修改在线认证，未验真实用户登录或手机UI。
- 测试成功后移除两个00:01时隙，文章历史记录保留；最终清理后回读待执行。

## 测试与审查

已有主链路268项、隔离定时95项、早期修复202项记录保留，不将重叠测试相加。缺口修复：82项审核/Store、7项原生修订、131项控制器/交接通过；合并上游笔记19项、能力手册和iOS矩阵检查通过。时间修复：92项provenance/Store、85项完整relay、后补9项时间边界、6项旧稿幂等兼容通过；独立复核10项通过，Ruff与diff检查通过。最终配置清理3项针对性测试通过。部分测试首轮因沙箱禁止ps而失败，获得只读进程权限后通过，未以改断言掩盖。

日志：ops/reports/publication-gap-contract-tests.txt、publication-native-clock-tests.txt、publication-final-slot-tests.txt；完整真实执行、媒体哈希、回滚与运行态证据：publication-production-activation.json；定时stdout：publication-native-trigger-receipts.json。

## 版本、部署与回滚

- remote_sha: 0832e95ae252a99ecf8e17b44f85b67346e6f783，git ls-remote origin refs/heads/main refs/heads/codex/publication-standard-workflow-20260926 两者一致。
- server_before: 5266d737de37aec0e33155c24d9e6914518d044c（时间修复部署前）。
- server_after: 0832e95ae252a99ecf8e17b44f85b67346e6f783，/opt/releases/ai-lab-platform-0832e95ae252.sKcoYr。
- health_check: 8容器healthy，4后端镜像e4c25453a7a7且revision一致；前端既有b9688d499424不变；APIready、Bridgeok、runtime契约审计通过、部署锁释放。
- functional_check: main与Story真实自动发行、正文/媒体回读、重复发行幂等通过；最终配置清理待部署。
- rollback_point: 最终清理前 /opt/ai-lab-shared/deploy-backups/publication-standard-workflow-20260926/0832e95ae252，含8镜像标签、版本、attestation、两篇已发布稿的SQLite在线备份。
- 部署使用既有锁与update.sh，核验expected_before，保留上游提交。回滚代码优先使用旧release与镜像；正常回滚不倒退数据库，以免丢失发布后新增记录。数据库备份只用于明确的数据恢复。
- 自动审批曾拒绝合并推送（已证明远端原有笔记改动后放行）和宽范围重复发行检查（只读证明没有其他到期稿、暂停相关写入后放行）。没有绕过审批。

## 边界与未完成项

- 待最终清理部署、同版运行态恢复、配置/历史读回核验完成后才能将整个任务标为 VERIFIED。
- 无监督不等于无条件发表：事实证据不足、独立审核拒绝、返工预算耗尽或关键外部能力不可用时，系统保留现场并阻断，不伪造内容或审批。
- 已签名但结构非法的批准文件保持失败关闭，目前不自动重写该冻结审核；需针对原attempt诊断恢复。签名保护目标与字节绑定，不防持有签名私钥或可修改原生DB的可信管理员。
- 未验真实登录/iOS界面、阅读进度和随书问答；这些不计入本次程序自动出版验收。
- 持续运行依赖本机Hermes及所需外部服务可用；新增主题需配置并同步服务端/本机，不承诺模型对任意未来主题都能产出合格内容。
