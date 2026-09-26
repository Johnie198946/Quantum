# 练习速度与辅助作答反馈

task_id: learning-latency-feedback-20260926
status: TESTED
branch: codex/learning-latency-feedback-20260926
worktree: /Users/dengzhaoyu/Documents/AI Lab/.worktrees/learning-latency-feedback-20260926
head/local_commit: 基线00a847bbde1a288e053ee60880fe203daa0943b2；尚未提交
remote_sha: ls-remote origin refs/heads/main=00a847bbde1a288e053ee60880fe203daa0943b2；本轮未推送
server_before: 00a847bbde1a288e053ee60880fe203daa0943b2
server_after: 本轮未部署
health_check: 基线API ready，服务被另一部署重启后恢复
functional_check: 本地233项测试通过；真实模型前后基准进行中
rollback_point: 未部署；预定基线/opt/releases/ai-lab-platform-00a847bbde1a.MgL7jI，镜像fc5d2b07cf8c93a4fa26e1593a883b88f89af837df131866d50ec70e4c157658
remaining_risks: 模型时延有波动；基准未完成前不宣称加速比例。

## 目标与架构

用户要求确认辅助作答开关有无实际用途，有用则保留并修复问题；优化出题和提交评阅时间。沿用当前学习修复会话的推送、部署、真机测试授权。

开关通过Answer.assisted保存，attempts_from_row转入学习画像，attempt_stats排除辅助作答，evidence_snapshot使用统计约束后续出题；并非无效功能。保留评分不变，在现有next_step展示明确“不计入独立掌握度”说明，兼容已安装Build63，也能展示历史辅助作答记录，无数据迁移。

仅复用learning.py、既有Hermes聊天/配额/授权路径和现有测试：生成提示减少重复解释；评阅只发送id/body/source_excerpt/reference_answer/rubric和实际答题文本，不重复传输选项、已有解析、显示标签，也不将辅助标记交给模型影响评分。字段、出处、题型、分项评分校验保留。没有新服务、后台任务、模型客户端或依赖。

未混入reading-selection-build54工作区中尚未提交的前端改动。客户端分段显示客观题结果需要另行改其状态机，本轮优化实际模型工作量及现有评阅反馈。

## 变更

- backend/api/learning.py
- tests/test_learning_exercises.py
- 本manifest

## 验证

- 17项练习测试通过；相关10个文件合跑233 passed、6条既有弃用警告、51.79秒。
- 全仓库Ruff和git diff --check通过。
- 辅助作答开关前后分数相同；辅助作答在独立统计中被排除；反馈只出现在辅助作答，重复读取不累加文案。
- 精简评阅输入保留完整题干、原文依据、参考答案、评分标准和用户原文，测试确认数据不截断。
- 首轮真实基准被生产容器重建打断(exit137)，未产生可用对比结果。重测使用共享部署锁，不替换生产代码；模型结果继续校验题型、难度、唯一原文出处和分项分数。

## Git盘点

新worktree创建时工作区干净，分支/HEAD/remote如下；以下status是仅上述两个本任务文件修改后的再次记录。前一任务最终manifest未提交改动保持在旧worktree。用户当前会话的一任务一分支一worktree要求优先于旧版仓库main-only规则。

```text
$ git status --short --branch
## codex/learning-latency-feedback-20260926
 M backend/api/learning.py
 M tests/test_learning_exercises.py

$ git branch --show-current
codex/learning-latency-feedback-20260926

$ git rev-parse HEAD
00a847bbde1a288e053ee60880fe203daa0943b2

$ git remote -v
origin	https://github.com/Johnie198946/Quantum.git (fetch)
origin	https://github.com/Johnie198946/Quantum.git (push)

$ git worktree list --porcelain
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

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/learning-latency-feedback-20260926
HEAD 00a847bbde1a288e053ee60880fe203daa0943b2
branch refs/heads/codex/learning-latency-feedback-20260926

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/learning-resume-exercise-fix-20260926
HEAD 00a847bbde1a288e053ee60880fe203daa0943b2
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

## 同材料真实基准第一轮

通过原有model_json→chat→Hermes路径，使用原真机题组的同一份材料、schema及用户作答，未创建/修改练习行和学习成绩。测试模型调用仍有正常计费和聊天审计副作用。

| 阶段 | 修改前秒 | 修改后秒 | 修改前输出字符 | 修改后输出字符 |
|---|---:|---:|---:|---:|
| 出题 |46.715|27.345|4044|2823|
| 评阅 |26.476|8.765|962|669|

四份结果全部通过相同schema、题型/出处/难度/评分校验。输入：出题6601→6776字符（增加精简说明），评阅3164→2553字符。不能把一轮差异当成固定性能保证，正在反序复测控制冷启动和服务波动。
