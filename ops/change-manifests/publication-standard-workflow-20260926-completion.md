# Publication standard workflow completion

- task_id: publication-standard-workflow-20260926
- goal: main 与 Story 无监督选题、写作、审核和发行；程序字段与可增删内容主题解耦。
- status: VERIFIED（部署代码3ad0ec0；真实定时恢复、独立审核、自动发行、正文/五图回读及全库回归均通过。后续仅提交验收文档。）
- branch: codex/publication-standard-workflow-20260926
- worktree: /Users/dengzhaoyu/Documents/AI Lab/.worktrees/publication-standard-workflow-20260926
- head/local_commit: 3ad0ec084fbefc8f439617da73bde67c3846fae9；其后仅验收证据本地更新。
- manifest: ops/change-manifests/publication-standard-workflow-20260926-completion.md。
- evidence_note: VERIFIED针对固定3ad部署代码与下述已完成验收；验收文档提交不冒充新服务器部署。13:58交接时10cron启用且Story下一期作者在途，后续任务已接手暂停/排空/升级责任；本任务不再双写运行环境。
- remote_sha: 任务分支=3ad0ec084fbefc8f439617da73bde67c3846fae9；origin/main=0775c6bd0dfb0682f64addacf61e70fbde28a1ce（并行任务后续提交）；均经git ls-remote核验。
- server_before: c030b9cbba7a2d16e7d94bbb6541a069ae7442e8。
- server_after: 3ad0ec084fbefc8f439617da73bde67c3846fae9；/opt/releases/ai-lab-platform-3ad0ec084fbe.Gn6VEJ；本机10正常cron同版源码。
- health_check: 独立八容器healthy、四后端image revision一致、API ready、Bridge ok、部署锁释放；部署后磁盘2.1GB，复查健康。
- functional_check: main教程r2已自动prepare、独立复跑一正四负、关闭旧缺口、自动暂存并发行；Story13自动配图/审核/发行通过；25本正文与82媒体全部200且哈希一致，匿名401；新教程11节/12代码块字节保留；指定旧刊五图真机可见。
- rollback_point: /opt/releases/ai-lab-platform-c030b9cbba7a.8k10j1；/opt/ai-lab-shared/deploy-backups/publication-standard-workflow-20260926/c030b9cbba7a（版本/镜像/attestation/在线SQLite备份）；磁盘故障后实际回滚健康已验证。
- remaining_risks: 历史9本媒体不完整（1本仅两封面、8本无媒体），未改冻结旧刊；本任务未上传TestFlight，后续联合客户端由并行任务负责；磁盘仍约96%，长期清理策略未实现，三份历史临时镜像包本地保全于/tmp/publication-disk-recovery-20260927；外部工具与本机Hermes须可用。



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


## 2026-09-27 11:08 当前部署与验收进度（覆盖前文历史状态）

- status: DEPLOYED。
- commit/remote_sha: b07e2cc4fd6c0bcd299990ec58d474761134e577；已用 git ls-remote 核验 origin/main 与任务分支同 SHA。包含媒体修复0028eec与上游清理兼容34b94f6。
- server_before: 5cd60e418d7b462568469d49782bb90f9d78e381。
- server_after: b07e2cc4fd6c0bcd299990ec58d474761134e577，release=/opt/releases/ai-lab-platform-b07e2cc4fd6c.NVjqCO。
- health_check: 8服务healthy；4后端镜像c7b2d80e8af09bd8a0a4f0335256fce0983026c548ae3b3198d40a0e33c755c3，revision=b07e2cc；既有前端b9688d499424保留；API ready、Bridge ok、部署锁释放。
- rollback_point: /opt/ai-lab-shared/deploy-backups/publication-standard-workflow-20260926/5cd60e418d7b，部署前8镜像标签、版本/attestation、2,584,576字节publication SQLite在线备份。
- functional_check: 部署后隔离ASGI回读20本正文200、已有57媒体200且哈希匹配、匿名取图401；不等于真实登录UI。模拟器6测试及PCM/后端相关检查通过；合并上游后115项回归通过。
- runtime: default/story/supervision规范入口已备份同步；10个正常job固定b07源码且启用，旧重复job b43保持暂停。toolkit精确旧耗尽claim经CLI校验冷却、owner证死、全局无活动任务后审计rearm，保留历史；未清空账本。
- 新临时单次定时job ea82a8f53a00：计划10:58:43.151644+08，实际10:58:53.264412，execution22526fd5a46d4c69b6a2c97ca4901ffc于10:59:23完成且无error；仅恢复既有控制器并调用既有watchdog。回执归档后临时job/script已删除。
- toolkit12点原生author execution1c34236dfafc4cc38acd647f350cb439，11:06:24已输出内容artifact；Story13点原生author execution66c843a7ee514c4d83510e5a3fe14302仍进行。当前不能声称本轮新稿自动配图、独立审核、按时发行已全部通过。
- 真机已解锁，保留登录并安装本轮debug构建。旧UI验收脚本依赖已删除导航标题，正对齐现有知识分段/书架容器/搜索入口；尚无真实五图UI通过结论。TestFlight旧Build66不包含本轮媒体修复，不能混称客户端已交付。
- remaining_risks: 本轮新稿完整自动链与真机媒体待验；9本历史缺图冻结刊物未补齐（1本双封面、8本无图），不能宣称20本均五图齐全。回滚代码用上述release/images，默认不回退数据库以免丢失新增稿件。


11:11真机证据校正：v8通过真实书籍身份、正文非空和双封面AX“图片已加载”断言，但导出PNG经肉眼复核均为iPhone镜像占用时的锁屏，不构成视觉通过；目录菜单测试失败。已退出Mac iPhone Mirroring，devicectl确认passcodeRequired=true，请用户再解锁。未把AX或合成触摸当作视觉通过，三插图尚未验。


11:20追加：v9真实XCTest通过（151.265秒），验证原登录/订阅、正文、11节目录首中末导航及五图AX加载；所有系统截图仍为镜像占用锁屏，独立镜像窗口视觉复核继续。不能将测试通过等同视觉通过。素材首轮已自行处理非git目录和只读权限错误，保留日志；11:20:55同一次assetclaim重启可写沙箱，未人工触发生图。旧等待曾以kill -0误判僵尸存活（工具timeout600有界），规范修正要求原进程句柄/退出码/回执，禁止PID轮询。提示词增量经独立review认可和本机CLI帮助核对，尚未提交同步运行态。


11:25 真机C层验收完成（仅指定完整媒体刊物）：v9 XCTest TEST SUCCEEDED，正文/11节目录前中末/五图加载断言通过；随后通过 computer-use 的 iPhone Mirroring 窗口逐一查看真实竖封面、横封面、三插图，保存 ops/reports/publication-media-ios-20260927/{shelf,shelf-cover,reader-cover,illustrations-all-three}.png，SHA见审计JSON。没有改变订阅、发送Chat或生成测试图片。系统锁屏PNG不作为视觉证据。当前安装b07 debug版，旧TestFlight Build66不包含本修复；9本历史缺图仍保留。设备已向已获用户授权的清理任务释放，服务器完整自动闭环仍待本轮完成。


11:29 增量提交：a5e7b74为本任务提示词/真机验收及证据；合并远端笔记保存同意修复f7e6fa9后HEAD=c1c5788c7a94a25f8f4cb6ed81c50614b4feeba1。origin/main与任务分支经git ls-remote核验同SHA；上游增量回归1passed，diff检查通过。仅提示词/测试/证据及上游iOS改动，不重启服务器；server_after与运行脚本仍b07e2cc。现有素材cron171a125ddb63仅追加已提交的启动/等待参数（prompt SHA ec19160571846a38fbf69bedb3cd8bf420829ab6fcc71ad2fa64ec3478c42652），schedule/script/workdir/model/provider/enabled/通知字段均未改。在途执行未重启，下一次自然调度读取补充。备份与回滚原prompt：~/.hermes/backups/publication-standard-workflow-20260926/assets-launch-c1c5788/job-before.json；细节见审计JSON。整体仍DEPLOYED，当前新一期完整自动发布待完成。


11:40追加构建器修复：真实12点新稿在完成5次原生生图后，被 _native_rejected_revision 使用现行配置解释旧00:01 rejected记录阻断；未prepare/审核/发布。复用冻结bundle期次身份，当前合同优先完整验证；相邻review_input同根因修复。独立review另复现_plan全局待审候选包含退休时隙导致review_scope_not_unique，现按启用主题/现行时隙与review_input保持一致。没有删除旧manifest、篡改图片/作者或清预算。最小新增解析函数仅被两个既有历史扫描复用，无新服务或调度链。

测试：relay相关21passed（117.79秒）、watchdog相关16passed（沙箱ps被拒的既有测试获得权限后同命令通过）、独立relay5passed、ruff/diff通过。两个实际新稿目录只读历史扫描通过，证据/tmp/publication-builder-real-history-readback.json。当前构建器增量尚未部署；10角色未来调度已备份暂停且active=[]，计划部署后由临时定时任务恢复。新rollback_point=/opt/ai-lab-shared/deploy-backups/publication-standard-workflow-20260926/b07e2cc4fd6c，8镜像/版本/attestation/2,584,576字节在线DB备份；预算attempt1保留，剩余5次可正常恢复。


## 11:50 最新交付事实（覆盖前文历史版本）

- commit/remote_sha/server_after/runtime: 7414b4e77303ee2aee217a57200806be97ce8ef2；git ls-remote确认origin/main及任务分支同SHA。
- server_before: b07e2cc4fd6c0bcd299990ec58d474761134e577。
- server_after release: /opt/releases/ai-lab-platform-7414b4e77303.QdpNjt。
- health_check: 8容器healthy，后端镜像a3f10610bc2a3d12827f2f9b504bdc1f9324c78d41665e714414c89e3d936610，APIready/Bridgeok，部署锁释放；前端b9688d保留。
- rollback_point: /opt/ai-lab-shared/deploy-backups/publication-standard-workflow-20260926/b07e2cc4fd6c（8镜像标签、版本、在线DB快照）。
- 本机全部10角色固定7414b4e源码与新提示词。临时no_agent任务82f150bfae99计划11:50:51.038336+08自动核对源码并恢复10角色、调用现有watchdog；未手工运行作者/生图/审核/发行，未重置预算。
- functional_check: 21 relay+16 watchdog相关测试、10独立测试、实际两个新稿历史扫描通过；此前真机五图显示已验。本轮新期完整自动恢复/独立审核/发行待确认，因此仍DEPLOYED，不能宣称全程未中断。


11:57 自动恢复进展：单次任务82f150bfae99实际11:51:50.616670→11:52:05.055644，execution544a2582450047749fa7ab80e3545fd1 completed/error=null；已归档回执并删除临时job/script。既有素材cron自动启动execution7bf74d6c2ebb49cebbafef5833ff32a2，同一素材claim合法累计attempt2，未清预算。自动复用经校验的同一期五图，11:56:54 build/prepare完成，issue-dc6e2ea2dc24a3999ba01da33613d4db处于await_review；尚不算审核或发布通过。


12:04 真实分支验收：12点到期发行cron自动发布ai-history、ai-practice、concept-fables三期；只读隔离ASGI验证三篇正文和15媒体200、哈希一致，原代码块保留，不代表在线登录测试。toolkit独立reviewer以真实Python反例拒绝：文中七必填字段与校验器行为不一致。保留拒稿与缺口，等待原作者自动修订；没有绕过审核。Story13点素材cron已自动启动。10个正常job均启用且固定7414源码。


12:17 Story真实自动配图→送审：原生素材execution ad547213a3a747798d353bdec32d8afb在12:00:59启动、12:16:17完成；首次Codex启动即使用可写沙箱/非Git目录参数，thread01a0e108-0eee-7aa0-af81-481d53a415e8内五次真实imagegen返回原图。最终五图尺寸及SHA和清单一致、原图与工具返回一致，无人工生图。进程工具曾误报exited/null，agent自行改用540秒有界等待，未伪称进程成功。远端issue-8040b6323c0ad848e2e84b036a38cbf4已prepare；控制器自动派发supervision execution7825be20baf34685b1e9333bcc16fcac进行独立审核，尚未批准/发行。八服务持续healthy、server仍7414b4e。


12:30 Story暂存恢复检查：12:20控制器和常规发行出现通用remote command failed(exit1)，12:27控制器再次失败；没有可靠stderr可认定根因。随后独立DB及原transport连续3次只读status确认唯一edition-220ff2b0c89f611a49f119d9422f8d63、publication-8040b6323c0ad848e2e84b036a38cbf4处于staged，release_at=13:00，content_hash=c489480888766bd7d373a0a2560368d366839bf6619197177b50696a0ee884e1；三个status均exit0且stderr空。远端审核/暂存已自动成功，本地manifest仍await_review，等待既有重试收敛；没有手动finalize或清预算。


12:32 自动恢复收敛：Story controller第三次finalize execution45b081e1b0734f489df163c86060ac7a于12:31:39完成，原claim completed/attempts3；本地manifest已staged且error清除，远端唯一edition及review_hash一致。12:30常规release也已completed。未人工重跑/改账本；前两次远端错误根因尚未独立复现，不宣称已修复一个未经证实的代码问题。Story等待13:00；toolkit退稿自动修订仍待验。


12:36 并行部署版本核验：另一获授权任务于12:31完成c030b9cbba7a2d16e7d94bbb6541a069ae7442e8部署；本任务独立ls-remote与服务器读取确认，7414为祖先，出版程序文件无变化，8容器healthy/APIready/Bridgeok/部署锁释放，release=/opt/releases/ai-lab-platform-c030b9cbba7a.8k10j1。任务分支快进c030并保留仅本任务两个验收文件修改；PCM手册/矩阵check及diff通过。本机cron仍固定7414，出版脚本与新服务端字节不变，不能宣称两边Git SHA相同。新版本回滚点由协调任务记录为7414 release及/opt/ai-lab-shared/rollbacks/chat-cleanup-pcm-c030b9cbba7a；本任务原b07快照仍保留。Build67包含媒体修复且归档，尚未TestFlight上传，真机媒体验收仍指此前debug构建。部署窗口可能影响远端重试，但12:20初次错误早于已知完成时间，未据此武断归因。


12:41 自动内容返修接力：原toolkit作者job b52aa900ac12由控制器因native_content_rejected自动派发execution6d273d025a6a425ab1c96a2642544053/session cron_b52aa900ac12_20260927_123252；原生工具消息546638实读required_claim_fields_not_enforced。12:39:43交付r2内容，只有schema_version/title/summary/body/source_documents/execution_documents六字段；12:40:42程序接收新artifact29874ecde8d0c1133417cc2eea45d809baddc25b3a5d8c8d46e63a14c35a4e87至独立冻结目录，仍为当天12:00同一期，waiting_assets。没有人工修改内容或填系统字段。


13:00 真实r2送审发现新接口错配：execution_negative_fixture_missing_fields长度41，作者artifact/本地manifest允许64，远端_receipts仅40，prepare明确invalid execution.kind。冻结作者内容及五图不改；仅共享存储校验40→64，复用既有64字符合同，规范同步边界。开工HEAD=c030b9cb、分支/worktree同前，仅本任务两份证据文件原有修改，其他worktree未动。素材/控制器未来调度备份暂停，正常发行保留。独立三轮复核无阻断，新增source/execution×旧短/41/64/65共8项通过，65仍拒绝；artifact_id上限及哈希/签名/媒体角色检查均不变。更广相关回归进行中，新增修复尚未部署。


13:05 修复验证与部署准备：116项daily/handoff回归全部通过（首次5项仅受沙箱ps拒绝，同命令授权复跑通过），新增边界8项及独立8项通过，Ruff/diff通过。server_before=c030b9cb，新增rollback_point=/opt/ai-lab-shared/deploy-backups/publication-standard-workflow-20260926/c030b9cbba7a（8镜像/版本/2,584,576字节出版SQLite在线快照）。10角色已备份暂停，active=[]。Story13已13:01:20自动发表且10节正文/五图回读200、SHA一致；本次后续修复仍待部署。

## 2026-09-27 13:28 磁盘满部署故障与恢复中

- source/local_commit: 3ad0ec084fbefc8f439617da73bde67c3846fae9；首次部署失败，不能视为上线。
- 根盘49G、剩余44MB、inode使用30%；PostgreSQL明确报`could not write pg_logical/replorigin_checkpoint.tmp: No space left on device`，导致内部恢复循环。未证实内存不足。
- 自动回滚指针恢复c030，但因数据库当时unhealthy，五个应用容器停留Created。清理可重下载APT缓存后余471MB，数据库自行恢复healthy，再启动这五个已创建的回滚容器。未重启或删除数据库，未删卷或刊物。
- 只读独立核验通过：c030版本、八容器healthy、API ready、Bridge ok、部署锁释放。回执`/tmp/publication-disk-rollback-health.json`。
- 全部10个正常出版cron仍暂停，无新临时启动任务；本机runtime已固定3ad但尚未启用。Story13已自动发行并回读通过；toolkit r2保留原稿及五张真实生成图，等待kind修复部署后由正常控制器接力。
- 正在保存两个2026-09-19历史/tmp镜像传输包到本地，只有大小/完整SHA256一致后才释放对应服务器副本；保留当前/回滚镜像、release、数据库、备份。

## 2026-09-27 13:42 磁盘恢复后3ad部署成功

- server_before/rollback_point: c030b9cbba7a2d16e7d94bbb6541a069ae7442e8，/opt/releases/ai-lab-platform-c030b9cbba7a.8k10j1；本任务备份/opt/ai-lab-shared/deploy-backups/publication-standard-workflow-20260926/c030b9cbba7a。
- server_after: 3ad0ec084fbefc8f439617da73bde67c3846fae9，/opt/releases/ai-lab-platform-3ad0ec084fbe.Gn6VEJ。独立八服务healthy、四后端image revision一致、API ready、Bridge ok、部署锁释放。
- 三个历史临时镜像传输包先保存在/tmp/publication-disk-recovery-20260927并逐份核对大小/SHA256，随后仅删除服务器/tmp对应副本；完整证据在audit JSON。部署前可用2322186240字节，重试入口先检查>=2GiB及>=100000空闲inode。镜像构建复用缓存。
- 临时原生任务6ca0670987d6，计划2026-09-27T13:43:16.859246+08:00；只恢复10正常cron并运行既有watchdog，不手工prepare/review/release，不重置预算。
- origin/main已被并行任务合法推进0775c6bd0dfb0682f64addacf61e70fbde28a1ce；任务分支远端仍3ad，经ls-remote核验；本轮部署固定已推送3ad。

## 2026-09-27 14:00 最终验收与交接

- 一次性原生恢复任务6ca0670987d6实际13:43:31启动，native57f0baa75867438b9b899be54dd9139d，13:44:52完成。原失败prepare attempt1保留，attempt2自动成功；未清除失败历史或重置预算。临时任务/脚本完成后归档并删除。
- 独立审核native9befac95ed0a44b38f45e5eb774def3e，session cron_fbd1cd1217d7_20260927_134705，43次工具调用，13:52:24完成。工具消息546917真实执行Python3.12.3，一正四负退出码0/1/1/1/1，缺字段负例明确拒绝basis_claim_ids,next_check。审核hash320127f770966aa15bf29c174c48d9d8c4df25b19f05a607e7b09d03eafb372f。
- 服务器revision1仍rejected，revision2=approved且缺口resolved；关闭时间2026-09-27T05:53:29.052985Z。控制器9dc2246d8c8845afa26fc7e640970155自动finalize于13:54:37结束。
- 正常发行native7a6f67a4115c43578aeba7818934769d，13:55:36→13:56:10完成；edition-24d51073b0082da33c8907718a88e819唯一published，publication-dc6e2ea2dc24a3999ba01da33613d4db，actual_release_at=2026-09-27T05:55:58.738742Z。内容hash5b212fca1710acb90a267bfbf00bef623f06a4c073a1489671f9641924c5af2c。
- 只读API回读该教程11节、12个代码块逐字节保留、5媒体200且与冻结hash一致；全库25正文/82媒体全部通过，匿名封面401。全库16本五图、1本两图、8本无图，不能把历史缺图说成已补齐。
- Story13自动发行后，13:45正常发行native7044c695dd054f3bb046a2e959b701d4无重复edition/新增publication。
- 13:58:33交接快照：10正常cron全部enabled且固定3ad，旧b43保持暂停；Story下一期作者69f70d377dc747df8feab27638c13fab在途，其余无在途。已向授权清理任务交接完整回滚/健康/原启用集合，并在当前进度明确后续部署须备份暂停新调度、等作者自然结束再切换。随后联合发布任务已确认接手，本任务不再操作server/runtime/cron。
- 本轮真实运行经历维护暂停与恢复，不能声称从首轮开始全程未中断。修复后的后半程由原生timer及正常cron自动完成；root未代替作者、素材agent或独立审核执行业务步骤。
- 验证沿用已通过的116项相关测试与Ruff；最终证据文件通过JSON解析及git diff --check。后续证据提交只包含本manifest和audit JSON，不再部署新代码。
