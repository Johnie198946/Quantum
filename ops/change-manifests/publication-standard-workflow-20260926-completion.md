# Publication standard workflow completion

- task_id: publication-standard-workflow-20260926
- goal: main 与 Story 无监督选题、写作、审核和发行；程序字段与可增删内容主题解耦。
- status: TESTED（2026-09-27 配图与协议追加修复本地检查通过；真机UI与部署后无人值守验收待完成，前一版5cd60e4部署证据不代表本轮已部署）
- branch: codex/publication-standard-workflow-20260926
- worktree: /Users/dengzhaoyu/Documents/AI Lab/.worktrees/publication-standard-workflow-20260926
- head/local_commit: 5cd60e418d7b462568469d49782bb90f9d78e381。
- manifest: ops/change-manifests/publication-standard-workflow-20260926-completion.md。
- evidence_note: 本文件与 publication-production-activation.json 的最终部署后事实更新保留本地未提交；程序/配置已提交、推送并部署同一 SHA，验收记录不冒充服务器版本。

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
- 测试成功后移除两个00:01时隙，文章历史记录保留；最终清理后再次回读通过，结果与清理前完全一致。

## 测试与审查

已有主链路268项、隔离定时95项、早期修复202项记录保留，不将重叠测试相加。缺口修复：82项审核/Store、7项原生修订、131项控制器/交接通过；合并上游笔记19项、能力手册和iOS矩阵检查通过。时间修复：92项provenance/Store、85项完整relay、后补9项时间边界、6项旧稿幂等兼容通过；独立复核10项通过，Ruff与diff检查通过。最终配置清理3项针对性测试通过。部分测试首轮因沙箱禁止ps而失败，获得只读进程权限后通过，未以改断言掩盖。

日志：ops/reports/publication-gap-contract-tests.txt、publication-native-clock-tests.txt、publication-final-slot-tests.txt；完整真实执行、媒体哈希、回滚与运行态证据：publication-production-activation.json；定时stdout：publication-native-trigger-receipts.json。

## 版本、部署与回滚

- remote_sha: 5cd60e418d7b462568469d49782bb90f9d78e381，git ls-remote origin refs/heads/main refs/heads/codex/publication-standard-workflow-20260926 两者一致。
- server_before: 0832e95ae252a99ecf8e17b44f85b67346e6f783（最终临时时隙清理前）。
- server_after: 5cd60e418d7b462568469d49782bb90f9d78e381，/opt/releases/ai-lab-platform-5cd60e418d7b.FqF0Eq。
- health_check: 8容器healthy，4后端镜像1b11225fa2c2且revision一致；前端既有b9688d499424不变；APIready、Bridgeok、runtime契约审计通过、部署锁释放。
- functional_check: main与Story真实自动发行、正文/媒体回读、重复发行幂等通过；最终配置清理后两篇历史回读通过；容器确认7个正常期次，本机10个角色启用且workdir同版，仅废弃重复发行任务暂停，全部本任务临时job删除。
- rollback_point: 最终清理前 /opt/ai-lab-shared/deploy-backups/publication-standard-workflow-20260926/0832e95ae252，含8镜像标签、版本、attestation、两篇已发布稿的SQLite在线备份。
- 部署使用既有锁与update.sh，核验expected_before，保留上游提交。回滚代码优先使用旧release与镜像；正常回滚不倒退数据库，以免丢失发布后新增记录。数据库备份只用于明确的数据恢复。
- 自动审批曾拒绝合并推送（已证明远端原有笔记改动后放行）和宽范围重复发行检查（只读证明没有其他到期稿、暂停相关写入后放行）。没有绕过审批。

## 边界与未完成项

- remaining_risks: 下述质量/外部依赖和未测试UI边界仍存在；本次约定的程序自动出版与临时定时验收无未完成项。
- 无监督不等于无条件发表：事实证据不足、独立审核拒绝、返工预算耗尽或关键外部能力不可用时，系统保留现场并阻断，不伪造内容或审批。
- 已签名但结构非法的批准文件保持失败关闭，目前不自动重写该冻结审核；需针对原attempt诊断恢复。签名保护目标与字节绑定，不防持有签名私钥或可修改原生DB的可信管理员。
- 未验真实登录/iOS界面、阅读进度和随书问答；这些不计入本次程序自动出版验收。
- 持续运行依赖本机Hermes及所需外部服务可用；新增主题需配置并同步服务端/本机，不承诺模型对任意未来主题都能产出合格内容。

非核心协调通知：向其他任务同步维护结束的消息被自动审批以缺少明确消息授权拒绝，未发送、未绕过；不影响出版功能验收。


## 2026-09-27 后续：流程协议固化与20本刊物图片诊断

本轮状态 **TESTED**（仅文档与诊断证据，本轮未提交、未推送、未部署；前述生产版本不变）。沿用同一出版任务分支/worktree。开工状态仅上次本任务的 manifest 与 activation JSON 未提交；branch=codex/publication-standard-workflow-20260926，HEAD=5cd60e418d7b462568469d49782bb90f9d78e381，origin=https://github.com/Johnie198946/Quantum.git。worktree盘点仍包含原main及两个其他任务，均未修改。当前GitHub main与server_before/server_after均为5cd60e418d7b462568469d49782bb90f9d78e381（本轮只读确认，未部署）；rollback_point沿用此前0832备份，本轮无运行态变更所以不新增回滚点。

复用并扩充 docs/runbooks/publication-standard-workflow.md 为统一流程合同，明确10个环节的输入/输出、责任、字段所有权、错误/重试/幂等、图片认证与三层验收。修正兼容schema名称；旧 docs/publication-operations-runbook.md 删除过时的08点作者/10点审稿/中午唯一发行及审稿者stage职责，改为引用统一规范。未新增运行架构、代码、依赖或自动任务；文档尚未同步运行源，不声称已被所有agent加载。

functional_check：真实20本逐本盘点，11本五图齐全、1本仅双封面、8本无图；已有57媒体全部GET200且SHA匹配，20本正文均无内嵌图片，未认证封面请求401。9本缺图均早于2026-09-25T02:17:28Z五图门禁，属于历史兼容保留。iOS源码DTO不接收三个媒体字段，部分封面加载依赖出版接口不存在的coverAvailable，阅读页只消费markdown而未消费illustration_urls；客户端显示链路尚未修复。

health_check：本轮未重跑整体健康检查（无运行修改）；正文/媒体读回通过，上一部署完整健康证据保留。校验规范字段与实际schema/重试上限一致、本地Markdown链接存在、git diff --check通过。证据：ops/reports/publication-protocol-media-audit-20260927.json。

remaining_risks：用户实际客户端/安装版本未确认；真实用户登录和UI显示未测试。后续修复应先补现有iOS DTO/认证取图/书架与阅读渲染及UI验收，再对9本历史缺图稿走受审新版本或补充流程；不得静默改旧冻结正文或仅用占位图宣称配图成功。

## 2026-09-27 配图与协议固化追加修复

基线：任务 worktree 分支 `codex/publication-standard-workflow-20260926`，HEAD/远端 main/任务分支/服务器均 `5cd60e418d7b462568469d49782bb90f9d78e381`；开工已有本任务文档与验收记录未提交，其他 worktree 未动。

已修：iOS DTO 接收书架/阅读封面及插图；复用认证 perform 和既有封面组件，禁止外域/跨书/重定向媒体请求，账号切换与取消清图，真实图完整显示。素材周期 cron 原子领取原有 recovery_claims，六次预算不再被直跑绕过。新原生稿件必须提供与五图字节一致的 image-manifest。PCM 复用 bookshelf.search/open，登记 illustrated_delivery 的 partial 消费状态；AGENTS 引用既有流程规范而不复制合同。

验证：relay 92 passed；watchdog/handoff 140 passed 后加 profile 守卫子集4 passed；PCM6 passed，能力手册/矩阵同步检查及Ruff/diff通过。iOS6项模拟器测试通过，含认证/跨域拒绝/注销取消/错误以及截图颜色像素断言，属于合成数据测试。真实设备测试已编译，UI runner 因 com.apple.sharing.authentication error12 无法初始化，不计为产品失败或UI通过；发现其他任务同时使用设备，待协调。

追加发现：正常 ai-toolkit 作者6次原生执行 completed，但 pre-script 报 issue slot is not configured，未产稿；正追踪删除临时slot后的历史筛选。Story未来期作者NO_NEW_DRAFT重复消耗恢复次数也在核对。

本轮 server_before=5cd60e4；server_after=未执行；health_check/functional_check=待部署后实测；rollback_point=待建立本轮快照。历史9本缺少部分/全部媒体保留原冻结版，不以客户端装饰图冒充补齐；历史补图与正常新期自动化验收须分别记录。

追加结果：retired-slot 修复后真实只读 Story 返回13:00期次；toolkit严格保留原耗尽预算返回NO_NEW_DRAFT，仅进程内模拟精确rearm才返回12:00（无DB变更）。两套相关143passed；随后legacy dispatched恢复兼容 focused17passed，均保留CAS、有效冷却、owner证死、全局无live/unknown和reason审计。PCM与语义投影42passed。独立review复核通过（最终legacy增量待回执）。

运行规范已备份并写入 default/story/supervision 的AGENTS.md；备份 `~/.hermes/backups/publication-standard-workflow-20260926/agent-rules-20260927-103900`，文件哈希见media审计JSON。10:42暂缓控制器及三个作者防止继续消耗已知错误预算；发行保留运行。用户另行授权与“帮我清理”任务协调同一真机/服务器，当前没有并发部署。

本轮rollback_point已建立：`/opt/ai-lab-shared/deploy-backups/publication-standard-workflow-20260926/5cd60e418d7b`，8镜像标签、release/attestation与2,584,576字节SQLite在线备份；server_before确认5cd60e4，8服务当时healthy。新源码尚未部署。
