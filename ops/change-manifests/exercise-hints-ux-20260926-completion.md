# 练习提示交互

task_id: exercise-hints-ux-20260926
status: TESTED
branch: codex/exercise-hints-ux-20260926
worktree: /Users/dengzhaoyu/Documents/AI Lab/.worktrees/exercise-hints-ux-20260926
head/local_commit: cbdea267b06ef086be7e49bfd3313e78e92f70fc（基线；本任务未提交）
remote_sha: 未推送；本轮fetch main基线cbdea267b06ef086be7e49bfd3313e78e92f70fc
server_before: 本轮未读取；前轮记录cbdea267b06ef086be7e49bfd3313e78e92f70fc
server_after: 未部署
health_check: 不适用，未部署
functional_check: 后端234项通过，Ruff与diff通过，iOS编译/两项定向测试通过；真机待安装验证
rollback_point: 不适用，未部署
remaining_risks: 真机镜像提示iPhone使用中，已请求锁屏；尚未安装/部署；模型耗时波动，新提示仅一组真实抽查。

## 变更与复用

backend/api/learning.py：复用Question/GeneratedSet/public及既有请求、JSON存储；新题hint要求1–240字符，提示词要求30–80字具体思路，不给答案；旧记录公开空hint并可正常提交。不增加模型调用、服务、迁移或依赖。
tests/test_learning_exercises.py：新提示字段及旧记录兼容回归。
docs/design/exercise-hints-ios.patch：以原iOS工作区为只读参考，最小独立补丁，尚未集成；复用HomePalette、Markdown、草稿assisted和保存路径，展开标记已查看，收起不撤销，跨题组重置展开状态。
docs/design/exercise-hints-preview.html：可点击设计预览，人工提示示例，非实际App。
本manifest。

设计沿用白卡、浅蓝强调、系统字体、既有圆角；44pt触控目标、无障碍展开状态、无需额外等待。旧无提示题不显示入口。
未复制、覆盖、暂存、提交另一任务未提交改动；用户明确要求隔离分支优先于仓库旧main-only规则。

## 验证

18 passed，4条既有弃用警告；Ruff通过；swiftc -frontend -parse 两份临时Swift文件通过（仅语法，不代表完整编译）；git apply --check原iOS工作区通过；git diff --check通过。
新测试覆盖空白/长度校验、旧无提示题读取和评阅；原测试继续验证答案字段不泄漏。

## Git盘点

新worktree由干净cbdea26创建；以下为修改后盘点。
```text
$ git status --short --branch
## codex/exercise-hints-ux-20260926
 M backend/api/learning.py
 M tests/test_learning_exercises.py
?? docs/design/exercise-hints-ios.patch
?? docs/design/exercise-hints-preview.html


$ git branch --show-current
codex/exercise-hints-ux-20260926


$ git rev-parse HEAD
cbdea267b06ef086be7e49bfd3313e78e92f70fc


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

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/exercise-hints-ux-20260926
HEAD cbdea267b06ef086be7e49bfd3313e78e92f70fc
branch refs/heads/codex/exercise-hints-ux-20260926

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/learning-endpoints-20260925
HEAD 9214ada52566e191485a1329c24e86e0a44f1dc9
branch refs/heads/codex/learning-endpoints-20260925

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/learning-latency-feedback-20260926
HEAD cbdea267b06ef086be7e49bfd3313e78e92f70fc
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

## 用户确认后接入（2026-09-27）

用户“OK 很好 帮我按照这样实现”确认前述必要前端接入范围。主线iOS比已安装Build63旧，因此以reading-selection-build54-20260925的现有iOS为兼容基线导入本隔离worktree；没有导入其后端代码，也没有修改原worktree。大部分Git差异属于Build63兼容基线，非本轮新增设计。未重新设计其他页面。
旧独立patch已被实际代码替代并移除。实际提示逻辑相对手机基线的改动文件为：
- ios/AIPlatformApp.xcodeproj/project.pbxproj
- ios/AIPlatformApp/AIPlatformApp.swift
- ios/AIPlatformApp/Networking/APIClient.swift
- ios/AIPlatformApp/Views/Chat/Components/ChatMessageStreamView.swift
- ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift
- ios/AIPlatformAppUITests/ProductionBookshelfUITests.swift
- ios/project.yml

- 提示读取直接使用题目hint，不发第二个模型请求。
- 展开标记assisted并本地保存，收起不撤销；已评分题查看提示不改成绩记录。
- 自动滚动展开内容至提交栏上方，减少动态效果设置生效；可访问性标记和44pt点击目标。
- 旧题无hint仍可打开作答，新提示从新生成题组开始。

## 完整验证

后端10个文件234 passed，6条既有弃用警告，63.84s；全仓库Ruff通过。
iOS题型解码/富文本渲染测试与提示UI自动化测试均通过（2/2）；UI测试验证提示默认隐藏、点击可见、答案选中不变、收起后辅助标记保留、可重新展开。
结果包/private/tmp/exercise-hints-tests-final.xcresult；截图docs/design/exercise-hints-simulator.png已人工检查，提示完整显示在固定提交栏上方。
真实模型用候选代码独立进程及既有模型通道生成，未改生产题组：40.433秒，四种题型、出处、难度、时间预算、schema全部通过；人工检查四条提示均给思路/第一步而非最终答案。单次数据不能证明出题速度稳定，点击提示不增加网络等待。
Debug iPhone最终构建通过（Build64，含自动滚动）；未上传TestFlight。

## 服务器部署前盘点

server_before=cbdea267b06ef086be7e49bfd3313e78e92f70fc
release_before=/opt/releases/ai-lab-platform-cbdea267b06e.TGFugz
image_before=sha256:7ac2fe446f336f1b94081f2e12ad173fbe057934a280cdf2f97fa9ccc2da6ce3
API ready；磁盘可用1.8GiB。将使用薄层镜像、标准发布锁和SHA前置条件。

## 发布门禁（2026-09-27）

自动审批在执行前拒绝git commit / git push origin HEAD:main组合操作：认为162文件/约2.4万行的前端基线导入超出明确授权。没有执行commit或push，没有绕过拒绝；已请求用户明确授权完整Build63基线纳入main及发布/安装。
status仍为TESTED。暂存区包含本任务已明确枚举的文件；未改动原iOS工作区。
真机镜像最后提示“iPhone使用中”，已请求锁屏连接，安装尚未执行。

安装包: /private/tmp/exercise-hints-device/Build/Products/Debug-iphoneos/AIPlatformApp.app
版本: 1.0.3 (64)
二进制SHA256: 1ec35e38de85745da0da6978b7080cb79f5e265e3b4134c375c868217c9fa436
