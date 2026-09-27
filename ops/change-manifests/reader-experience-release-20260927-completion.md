# 阅读体验与按需配图交付

task_id: reader-experience-release-20260927
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
head/local_commit: 基线 c030b9cbba7a2d16e7d94bbb6541a069ae7442e8；本任务待提交
remote_sha: origin/main 基线 c030b9cbba7a2d16e7d94bbb6541a069ae7442e8；本任务未推送
server_before: c030b9cbba7a2d16e7d94bbb6541a069ae7442e8；/opt/releases/ai-lab-platform-c030b9cbba7a.8k10j1；8 容器 healthy
server_after: 未执行
health_check: 待部署
functional_check: 本地回归见下；线上待部署
rollback_point: 待部署前建立；当前线上基线只读核验完成
manifest: ops/change-manifests/reader-experience-release-20260927-completion.md
remaining_risks: TestFlight 未上传；生产待验证；出版 cron 现处于暂停状态，保持外部任务设置，未宣称自动出刊成功。

## 授权与架构命中

用户“接受你的建议完成开发以及上线”授权开发、提交、推送与部署。实际产品根目录 AGENTS 要求仅 main/规范目录，按产品规则交付；不混入已有 AGENTS §8 和其他任务 manifest。复用现有阅读器、Markdown 缓存、租户图片缓存、publication store/receipt、独立审核签名和 release/watchdog；未增加新服务、状态库或依赖。

选词问题优先回答真实用户请求，已有联网授权时允许有来源的知识延伸，保留仅本文/禁止联网边界；年龄问题明确事件时点和未知出生年。阅读滚动改为每个 ScrollView 一个观察器并合并回调；逐段字体保留 Markdown 样式与 Dynamic Type；封面 9:16、正文图 16:9，后台降采样并使用账户隔离缓存。

插图计划与正文 SHA、唯一段落锚点及 source receipt 绑定，走既有独立审核；新稿按需要 0..12 张（12 是资源上限而非目标），正文逐段显示；旧稿无计划保留五媒体合同及旧阅读器兼容。唐史敦煌壁画风格与时代考据要求写入既有素材/审核 prompt。历史已刊正文未被静默重写。

## 本地验证

- 签名 iOS 单元：285 passed；阅读器 UI：4 passed（长文、连续三次问题、键盘、来源入口）。
- 滚动同一隔离复现：100 段、60 次 contentOffset 修改，观察回调 6000→60，同步耗时约406ms→4.912ms；该指标不是整页 FPS。
- 新合同/投影/Chat/PCM：75 passed；问答联网边界：9 passed；计划及 watchdog：116 passed（需要沙箱外 ps）。
- 最新段落精确投影及 0/1/3/5 图实际媒体路由：7 passed；快进3ad0ec08后的计划/handoff回归：65 passed。
- 全出版相关回归：314 passed；先前沙箱测试因 ps 被拒失败，授权重跑通过。
- iOS 1.0.3(68) Release archive succeeded；上传待执行。
- PCM generator --check、git diff --check 通过。agent_config.py 存在基线重复 import 的3个 F811（已用 git show HEAD 核实）；不归因本任务，不擅改无关代码，其余 touched Python ruff 通过。

详细日志、复现及发布工具：/private/tmp/reader-experience-release-20260927/。

## Git 开工盘点

### status --short --branch

```text
## main...origin/main
 M AGENTS.md
 M ops/change-manifests/chat-cleanup-client-compat-20260927-completion.md
 M ops/change-manifests/chat-cleanup-pcm-20260927-completion.md
 M ops/change-manifests/cleanup-exercise-testflight-20260927-completion.md
 M ops/change-manifests/note-organization-v2-20260927-completion.md
 M ops/change-manifests/quantum-note-save-consent-20260927-completion.md
 M ops/change-manifests/quantum-notes-release-20260927-completion.md
?? ops/acceptance/receipts/
?? ops/change-manifests/cleanup-diff-20260927-completion.md
?? ops/change-manifests/quantum-2.0-hermes-gate-i0-20260909-completion.md
```

### branch --show-current

```text
main
```

### rev-parse HEAD

```text
c030b9cbba7a2d16e7d94bbb6541a069ae7442e8
```

### remote -v

```text
origin	https://github.com/Johnie198946/Quantum.git (fetch)
origin	https://github.com/Johnie198946/Quantum.git (push)
source	https://github.com/Johnie198946/ai-lab-platform.git (fetch)
source	https://github.com/Johnie198946/ai-lab-platform.git (push)
```

### worktree list --porcelain

```text
worktree /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
HEAD c030b9cbba7a2d16e7d94bbb6541a069ae7442e8
branch refs/heads/main

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-notes-20260927
HEAD c1c5788c7a94a25f8f4cb6ed81c50614b4feeba1
branch refs/heads/codex/travel-notes-20260927

```

## 变更文件

- AGENTS.md（仅§7按需配图一行）
- backend/api/chat.py
- backend/api/knowledge_publication.py
- backend/api/subscriptions.py
- backend/contracts/product-capabilities/bookshelf.yaml
- backend/contracts/product-capabilities/consumptions.yaml
- backend/services/knowledge_publication_store.py
- docs/product-capability-coverage.json
- docs/product-capability-manual.md
- docs/prompts/quantumn-ai-toolkit-workflow-assets.md
- docs/prompts/quantumn-ai-toolkit-workflow-author.md
- docs/prompts/quantumn-editorial-v2.md
- docs/runbooks/publication-standard-workflow.md
- ios/AIPlatformApp.xcodeproj/project.pbxproj
- ios/AIPlatformApp/DesignSystem/Theme.swift
- ios/AIPlatformApp/Networking/APIClient.swift
- ios/AIPlatformApp/Services/MarkdownBlockParser.swift
- ios/AIPlatformApp/Views/Chat/Cards/ImageCard.swift
- ios/AIPlatformApp/Views/Settings/SettingsView.swift
- ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift
- scripts/hermes_bridge_runtime/agent_config.py
- scripts/publication_daily_completion.py
- scripts/publication_editorial_remote.py
- scripts/publication_operator.py
- scripts/publication_release_remote.py
- scripts/publication_scheduler_watchdog.py
- tests/test_wiki_retrieval_governance.py
- tests/test_publication_illustration_plan.py
- ops/change-manifests/reader-experience-release-20260927-completion.md

## 主线同步

发布前检测到另一任务上线3ad0ec084fbefc8f439617da73bde67c3846fae9（收据kind 40→64）。两个重叠文件逐字保存，并经无冲突三方文件合并恢复本任务修改；main仅fast-forward，无stash/历史改写。新基线3ad0ec08，复验65项通过。该任务仍在服务器收尾与定时恢复，部署窗口待协调；本任务尚未改动服务器或本机出版runtime。
