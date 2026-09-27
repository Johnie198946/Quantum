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
- runtime_after: a8cc2954e13a40732fc36444df6beaf81f05b80b；10cron与wrapper绑定一致，原enabled/prompt/schedule保持；controller wrapper SHA256 06b11a807c2428cadc465fa30c8b36435d22479acccdccf34d95df0c85de18c8。先前74c自然取稿已通过，联合a8cc包含相同修复。
- server_before: b696d13bdcef18cc23b1707dc00501ca012ee224
- server_after: a8cc2954e13a40732fc36444df6beaf81f05b80b；与阅读优化/笔记修复共同交付，由阅读优化任务独占部署。release=/opt/releases/ai-lab-platform-a8cc2954e13a.swjper。
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
