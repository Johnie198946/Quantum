# 正文与插图继续验收

- task_id: publication-standard-workflow-20260926-body-acceptance
- status: TESTED
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
- commit: 未执行
- remote_sha: 本次修复未推送
- runtime_before: b696d13bdcef18cc23b1707dc00501ca012ee224
- runtime_after: 未执行
- server_before: b696d13bdcef18cc23b1707dc00501ca012ee224
- server_after: 未变更；本修复仅本机controller，服务器无对应代码行为变更。
- health_check: 本次运行态修复尚未执行
- functional_check: 旧刊真机样本通过；新稿完整链待验收
- rollback_point: 尚未切换；切换前备份当前wrapper与cron设置
- remaining_risks: 新版illustration_plan尚无实际发行及真机位置证据；旧刊不静默重排；书架加载性能由阅读优化任务负责。
