# 正文与插图继续验收

- task_id: publication-standard-workflow-20260926-body-acceptance
- status: VERIFIED
- verified_scope: 仅controller启动修复；新版插图全链未完成
- branch: codex/publication-standard-workflow-20260926
- worktree: /Users/dengzhaoyu/Documents/AI Lab/.worktrees/publication-standard-workflow-20260926
- head_before: 2f1fb74d06d9b53828258f6360a0dbb54b8cffbf
- remote: origin https://github.com/Johnie198946/Quantum.git
- status_before: 仅未跟踪的 ops/reports/publication-cover-title-20260927/ 私有真机截图；保留且不上传。
- worktree_inventory: main checkout 2d893130d629615144a8319e7ca25b04073dc7e5；本任务 2f1fb74；jev checkout be1b6bf18da36a04ca858392859244f93802836e；story-port-review detached ea7b263d4c38852bbba88ca8f5f5645506d6f1ad。其他工作区未修改。
- upstream_read: 2026-09-27 git fetch origin main，origin/main=b696d13bdcef18cc23b1707dc00501ca012ee224；本次两个代码文件与其一致。

## 问题与最小方案

当前25本已发表刊物都无 illustration_plan：16本为双封面加旧三图，1本仅封面，8本无媒体。存储 bundle 不含 body 字段不代表缺正文，正文由 body_ref 恢复。不能用这些旧版证明新稿按段落插图已完成。

controller 的 native_fetch 连续返回 action_exception。只读执行固定 b696 runtime 的 publication_workflow_handoff.py --help，确定复现 PermissionError errno=13：源文件0644，watchdog直接作为程序执行。prepare/finalize同类Python入口也受影响。

复用 daily_completion/review_input 的 sys.executable 调用方式，仅修改 watchdog 的两个 subprocess argv；不改协议、环境隔离、超时、错误分类、预算、ps或Hermes派发。测试复用现有watchdog套件，补7路径真实0644脚本回归。三轮独立反方审查收敛并批准方案；批准不等于功能验收通过。

变更文件：scripts/publication_scheduler_watchdog.py、tests/test_publication_scheduler_watchdog.py、本记录。

## 已核验材料

- Story20作者终态只读绑定成功：hermes:cron_d3e461e0578c_20260927_135815；正文4751字符；原始内容SHA256 382d219637ff63c9ff170880d68aa34f9216515f526038432dede472533bc1db。
- 该期尚未完成新素材/审核/发行验收。native_fetch位于claim前，不能通过清预算掩盖故障。
- Build69真机：AI实践《AI把会议纪要变成任务表之后，先别点“导入”》可读到第10章来源末尾，阅读封面和文末三图真实显示；本地证据 /private/tmp/publication-body-acceptance-20260927/build69-ai-practice-three-illustrations.png，不上传GitHub。
- 全量接口正文/媒体哈希检查与真机逐本检查须分开记录；当前真机只完成上述样本。

## 交付字段（继续更新）

- tests: 新回归旧实现7/7 PermissionError；修复后7/7通过；完整watchdog套件116 passed（初次沙箱ps受限，升级权限重跑通过）；独立复核9 passed。git diff --check通过。
- commit: 74c23c574cbef7a7aa8224829448b0ed7c9fd5af
- remote_sha: git ls-remote origin refs/heads/codex/publication-standard-workflow-20260926 = 74c23c574cbef7a7aa8224829448b0ed7c9fd5af；已独立核对。
- runtime_before: b696d13bdcef18cc23b1707dc00501ca012ee224
- runtime_after: 0704ddf5a54bf9739e506652e7b60fa2f22f564c；10cron与wrapper绑定一致，原enabled/prompt/schedule保持；controller wrapper SHA256 06ae83b4e1d50898b8a6492e8c8156d87028a136f8de6a56611e1311c9380872。先前74c自然取稿、a8cc自然配图重试已通过，0704保留相同修复。
- server_before: b696d13bdcef18cc23b1707dc00501ca012ee224
- server_after: 0704ddf5a54bf9739e506652e7b60fa2f22f564c；本轮共享Chat修复由cleanup任务独占部署。release=/opt/releases/ai-lab-platform-0704ddf5a54b.IXeolO。
- health_check: 三个Python入口--help通过（handoff/editorial仍0644）；最终a8cc runtime _status生产只读调用成功，今日计划7期已发行6期、20:00期未到时。独立核API镜像revision和服务器.deployed-sha=a8cc、/ready返回ready；首次误查/health/ready为404，改用代码声明/ready确认通过。协调任务8容器healthy、回滚备份哈希通过，记录 /private/tmp/bookshelf-functionality-20260927/server-verification.json 已读取。
- functional_check: 自然controller 32fee8d7a885459cb797b6677566b9af 于16:09:27完成native_fetch；生成Story20目录且作者SHA256一致，body SHA256 076cbb867c99609ea8ff09322ffcdf5f391990a6df7960c7f708f6776d5c5c9f。16:10:42自然素材任务566d2ea508784ed1b48deea4a47e1f1f已启动，新稿完整链待验收。
- rollback_point: /Users/dengzhaoyu/.hermes/backups/publication-fetch-74c23c574cbe 保存原10任务设置与所有切换wrapper；旧b696不可变release保留。导出时安全拒绝仓库tools绝对符号链接，保留.incomplete-export后排除唯一tools链接重新导出，未跳过任何出版源码。回滚需先暂停并自然清空任务，再恢复原绑定与原enabled；不得覆盖业务台账。
- remaining_risks: 新版illustration_plan尚无实际发行及真机位置证据；旧刊不静默重排；书架加载性能由阅读优化任务负责。

## 继续验收证据

- 新的隔离ASGI进程对当前生产数据回读：25/25正文200，266章节正文文本完整（除排版空白规范化）、标题顺序和代码块字节全部保留；82/82媒体200且SHA256一致；匿名封面401。未修改线上auth；本测试不是用户真实登录认证验收。完整私有结果在 /private/tmp/publication-body-acceptance-20260927/full-body-readback.json。
- 真机浅水原：阅读封面、正文至第11章来源末尾、3张文末图片均已加载；前两张完整显示，第三张仅上半部在截图可见，底部滚动/裁切待阅读优化任务继续验收。不能把部分画面写成完整第三图验收。手机16:03归还该任务。
- 新插图必须随真实素材/审核/到期发行/客户端位置验收补证；当前25本旧计划不能证明新版完成。

## 16:30 补充

- 唐史第三图完整性补证已独立查看：/private/tmp/build69-tang-three-images-complete.png；三图完整且第三图下边缘与页面底部可见。旧版真机样本验收通过；不计为新版段落图通过。
- 素材执行566d2ea508784ed1b48deea4a47e1f1f于16:20:28自然完成，但业务结果失败：Codex工具宿主连续3次 timed out negotiating with the code-mode host，无图片/manifest/prepare。只用1次assets恢复预算，未清除或重置。失败原始记录本地保存在 /private/tmp/publication-body-acceptance-20260927/assets-attempt1/。
- 独立只读Codex探针先遭遇WebSocket超时，随后自动回退HTTPS并真实执行printf，exit0/tool-host-ok。仅证明该只读工具连接恢复，不能证明image_generation恢复。
- 为联合修复部署已再次备份并暂停10cron，三个profile无活跃出版执行；部署由阅读优化任务独占，最终远端main a8cc2954e13a40732fc36444df6beaf81f05b80b已经git ls-remote核实。暂未切本机到a8cc或恢复，需服务器健康/功能通过。切换前备份 /Users/dengzhaoyu/.hermes/backups/publication-fetch-878744d9d3a2；该目录名字为最初候选SHA，最终actual after必须另记。

- 已建立当前对话的20:10一次性heartbeat续查（automation id=automation，target_thread_id=01a0de5e-9632-7743-afa8-91eba7176326）；通过app工具创建并回读本地automation.toml确认。用于20:00正常发行后的新计划、真实审核/发行和手机位置验收；不提前发行，不把旧刊或人工生成计为自动成功。

## 最终联合运行状态

- 远端main经本任务git ls-remote独立确认a8cc2954e13a40732fc36444df6beaf81f05b80b；原修复74c已由协作任务cherry-pick为9d1e2f02并纳入a8cc。
- 本机最终10cron全部恢复原enabled=true，最后resume回读active=[]；controller next=16:38、assets next=16:40。prompt、schedule、script、deliver、failure_deliver、model、provider经逐项比较保持。未建立额外出版scheduler、未直接派发素材或提前发行。
- 最终本机rollback_point=/Users/dengzhaoyu/.hermes/backups/publication-fetch-878744d9d3a2（receipt.after=a8cc，before=74c，目录名保留）；server rollback_point=/opt/ai-lab-shared/rollbacks/bookshelf-functionality-a8cc2954e13a，PG/SQLite哈希检查通过。
- remaining_risks：当前8本历史无媒体、1本仅封面，未静默改写冻结历史；新版按段落插图仍待自动重试、独立审核、20:00正常发行和真机位置验收。20:10续查已安排。VERIFIED仅针对controller修复及既有正文/媒体验收，不代表新插图全链完成。

## 最终恢复后的自然触发

- a8cc runtime原生controller执行082640b3d7b7455aa86dfb415954821a，于16:39:10完成并返回phase=assets/action=triggered；材料哈希仍为382d219637ff63c9ff170880d68aa34f9216515f526038432dede472533bc1db。
- 原生素材执行a01a6b179ebc4189b8f393a46ee4ef26于16:39:10.117315启动，查询时running。确认自然有界恢复已继续，不将running当作生成成功；新计划媒体和发行留待20:10续查及后续证据。

## 17:00 新计划素材及独立审核补证

- 第二次素材执行a01a6b179ebc4189b8f393a46ee4ef26已成功，16:52:33回执为await_review；首次失败后由自然controller派发，没有人工配图或改正文。
- 原生Codex线程01a0e206-0c31-7a31-a26c-b19ee3e26407的rollout中核验5次实际tools.image_gen__imagegen调用（16:41:42至16:46:18），不能只看exec JSONL摘要中的command/file_change事件。返回原图路径、保留原图哈希、最终5JPEG哈希均匹配image-manifest；双封面尺寸1440x2560/2560x1440，3插图1600x900，全部小于2MiB。五图已独立目视检查。
- illustration_plan=3图，body SHA256绑定通过，3个完整普通段落锚点均唯一；计划文件SHA256=74daf26acf7e50bf238aa9130bd270a9acf957c8aa8e462ee92101721a0a471f。image-manifest SHA256=8d62a7ee25735a76e57e08569375b5df1ac7ab6d3789425a96d84bb7f1d86b12。
- 独立审核hermes:cron_0dd3884f173c_20260927_165323，decision=approved，target=adb79173012b430d64fee1f7effa754fbb348ede1ffb1f273de00bf4f5b753d3；review SHA256=51ac8dd8148b49228432268d4755730c3326a97c9c49e859ff4172c21840acef，proof SHA256=cfe45cef704d4df5dad8ee8f9ae2413536d85f01168f78b2ff5f0df9411cb8f3。
- 本地冻结receipt edition-bd22b975b1adbff7ddf1c3eadf515a6b，publication-6d65e4fff6f4ae7734d1585c3a05a80a，state=staged，release_at=2026-09-27T12:00:00+00:00（20:00 CST）。未提前发行；发行后API与手机实际位置仍待验证。
- 追加共享Chat后端修复协调：曾因目标SHA未确定短暂停后立即恢复10cron；0704ddf5a54bf9739e506652e7b60fa2f22f564c最终push并经本任务ls-remote核验后再次暂停，active=[]。本轮唯一服务器部署者改为cleanup，恢复点=/Users/dengzhaoyu/.hermes/backups/publication-chat-followup-0704ddf5；等待其部署验收再pin/恢复。

- 已准备 /private/tmp/publication-planned-reader-readback.py（py_compile通过），供20:10在隔离ASGI进程读取真实生产数据：从required_publication_media和illustration_plan推导数量，逐项比较caption/alt/完整段落/section_id/content_version/URL和媒体哈希，不固定3图。尚未对暂存稿调用读者接口，不提前发行；实际功能运行结果需发行后补记。

## 0704 最终部署后恢复与新稿保存检查

- git ls-remote origin refs/heads/main独立核验0704ddf5a54bf9739e506652e7b60fa2f22f564c；共享后端干净快照110 passed/6 warnings日志已读取。
- health_check: 本任务独立核API镜像revision、服务器.deployed-sha均0704，/ready返回ready；同版本本机_status通过（今日6/7，20:00尚未到期）。协作server-verification.json为8容器healthy，server-functional.json为session_registration/owner_isolation/tenant_isolation/owner_conflict全部pass、production_user_writes=0，两份原记录均已读取。
- runtime_after: 0704；原10cron全部恢复原enabled，prompt/schedule/script/deliver/failure_deliver/model/provider逐项保持。恢复回读active=[]。
- rollback_point: 本机 /Users/dengzhaoyu/.hermes/backups/publication-chat-followup-0704ddf5；服务器 /opt/ai-lab-shared/rollbacks/bookshelf-functionality-0704ddf5a54b，数据库及publication SQLite备份哈希通过，a8cc原release保留。
- functional_check: 直接只读生产publication.sqlite3，publication-6d65e4fff6f4ae7734d1585c3a05a80a仅一个edition-bd22b975b1adbff7ddf1c3eadf515a6b，state=staged、actual_release_at=null、release_at=2026-09-27T12:00:00+00:00；正文文件/content_hash/plan.body_sha256均076cbb...c9f一致，计划3图、assets5项。部署没有回退稿件。
- remaining_risks: 新版自动配图、独立审核、暂存已通过；正常到期发行、发行后读者API与实际手机段落位置未验证，20:10自动续查保持ACTIVE。8本历史无媒体、1本仅封面的冻结缺口仍存在，未静默覆盖。

## 分页修复联合部署后的出版恢复（21250）

- server_before: 0704ddf5a54bf9739e506652e7b60fa2f22f564c。server_after/runtime_after: 21250c7b8a5290abcf649b9279bbd91b9af1db88；release=/opt/releases/ai-lab-platform-21250c7b8a52.rS7UdR。cleanup独占服务器部署，本任务独占出版cron切换。
- remote_sha: 切换准备时独立git ls-remote确认main=21250；安装前main前进至f8c7d064c959312e54fcb1dcaf3a08f5bbf19dfe，精确保护阻止安装且未修改绑定。fetch/diff确认包含其他功能变更，git merge-base --is-ancestor确认21250为其祖先；与部署方协调后固定已部署21250，不引入未部署main代码。
- health_check: 本任务独立核对服务器.deployed-sha、API镜像revision均21250，/ready返回ready。已读取pages-server-verification.json：8容器healthy、数据库和publication SQLite备份哈希通过。
- functional_check: 生产SQLite只读确认目标publication仅一个edition，state=staged，actual_release_at=null，release_at=20:00 CST；正文文件/content_hash/plan.body_sha256一致为076cbb867c99609ea8ff09322ffcdf5f391990a6df7960c7f708f6776d5c5c9f，计划3图。catalog-functional.json记录136正文/5页/hash一致、note_mutations=0；semantic_review_complete=false，不能称136笔记语义审核完成。
- cron: 备份暂停10任务，三profile active=[]后交接部署；最终10任务原enabled全部恢复，提示词/计划/script/model/provider/delivery逐项保持，runtime=21250，恢复回读active=[]。
- rollback_point: 本机/Users/dengzhaoyu/.hermes/backups/publication-pagination-followup-21250c7b；服务器/opt/ai-lab-shared/rollbacks/bookshelf-functionality-21250c7b8a52。
- status: VERIFIED仅针对此次版本恢复及已完成检查；新刊到期发行与读者端段落位置仍未验收，20:10一次性续查保持。历史9本媒体缺口未改写。

## 旅行并行部署后最终同步（f8c7）

- server_before: 21250c7b8a5290abcf649b9279bbd91b9af1db88；server_after/runtime_after: f8c7d064c959312e54fcb1dcaf3a08f5bbf19dfe。其他任务已执行服务器部署，本任务未重启服务器；通过已授权cleanup协调锁归属。
- remote_sha: 安装脚本再次git ls-remote严格确认main=f8c7；源码包含21250，publication/editorial/knowledge/story/scheduler/cron以及main/auth/agreement等所查路径无差异。
- health_check: 独立读服务器.deployed-sha、API镜像revision均f8c7，/ready返回ready；新runtime的_status生产只读请求成功。首次临时importlib探针未注册sys.modules导致dataclass导入异常，修正探针后通过，不是产品故障。
- functional_check: 生产唯一staged稿、20:00 release、actual_release_at=null，正文/plan哈希076cbb...c9f、3图计划、5媒体记录保持；尚未进行新刊发行后媒体验收。状态接口仍提示2026-09-09历史rights_attestation_missing_or_unbound，不伪报全局无异常。
- cron: 暂停仅新触发；当时控制任务2a32dcef0240496fbdf294507e87c298自然completed后切换；10cron原enabled和各配置恢复，active=[]。
- rollback_point: 本机/Users/dengzhaoyu/.hermes/backups/publication-compatible-f8c7d064；服务器/opt/ai-lab-shared/rollbacks/chat-travel-pcm-f8c7d064c959已独立列目录确认PG与版本备份存在，但没有publication SQLite；出版库可使用上一轮bookshelf-functionality-21250c7b8a52已校验备份，不能将本轮目录描述为包含出版库。
- status: VERIFIED仅上述同步/健康/暂存完整性检查；新计划发行及手机位置仍待20:10续查，历史9本图片缺口仍在。

## API临时配额重载窗口结束

- cleanup按其用户授权临时将API配额10000000调整12000000，声明workers未改；本任务未修改配额或账本，仅协调出版空闲窗口。
- server_before/server_after/runtime_after: f8c7d064c959312e54fcb1dcaf3a08f5bbf19dfe保持；独立API镜像revision相符、healthy、/ready返回ready。
- functional_check: 暂停10cron前保存原配置，active=[]；配置重载后10cron全部恢复原enabled且runtime保持f8，恢复active=[]。不把此检查当作新刊发行或配图真机通过。
- rollback_point: 出版设置/Users/dengzhaoyu/.hermes/backups/publication-quota-window-20260927（receipt=resumed）；配额配置备份由cleanup记录/opt/ai-lab-shared/rollbacks/note70-quota-20260927/env.before，本任务未读取其敏感内容。
- remaining_risks: 临时配额待cleanup复测后协调恢复；旅行新补丁尚未部署；20:00新刊发行和20:10续查仍待执行。

## 联合d228部署后的最终出版恢复

- server_before: f8c7d064c959312e54fcb1dcaf3a08f5bbf19dfe；server_after/runtime_after: d228c06d6865bdbca9329f264acfe4cf0e8fc5f7；release=/opt/releases/ai-lab-platform-d228c06d6865.CbxC2W。cleanup协调、旅行唯一服务器部署、本任务仅出版调度窗口与运行时同步。
- remote_sha: 本任务独立git ls-remote在暂停前和安装时均确认main=d228。
- health_check: 独立服务器.deployed-sha及API镜像revision=d228、API healthy、/ready返回ready；协作方回报8容器healthy。
- functional_check: 独立只读生产SQLite核目标publication仅一个edition，staged，20:00 CST release，actual_release_at=null；正文/content_hash/plan.body_sha256一致076cbb867c99609ea8ff09322ffcdf5f391990a6df7960c7f708f6776d5c5c9f，3计划图和5媒体记录保持。10cron配置及启用状态恢复、runtime/wrapper=d228、active=[]，未提前发行。
- rollback_point: 本机/Users/dengzhaoyu/.hermes/backups/publication-joint-d228c06d；服务器/opt/ai-lab-shared/rollbacks/chat-travel-pcm-d228c06d6865含PG、出版SQLite、媒体稿件tar、环境配置及旧版本引用；独立sha256sum -c三份备份全部OK。旧release f8保留。
- status: VERIFIED仅本轮部署恢复及已完成验收范围。remaining_risks: 新刊到期发行及手机段落位置仍未验收，20:10续查保持；临时12m配额由cleanup后续协调恢复；历史9本图片缺口和历史版权绑定阻塞仍如前。
