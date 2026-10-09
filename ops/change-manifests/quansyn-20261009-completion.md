# QuanSyn 20261009 — 交付记录

task_id: quansyn-20261009
status: DEPLOYED
branch: codex/quansyn-20261009
worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/quansyn-20261009
head/local_commit: 产品部署 996fb84ac3714301ca142437a7fd727e27cc8204；发布后的验收记录另提交，具体提交见 Git HEAD
remote_sha: 部署 SHA 996fb84ac3714301ca142437a7fd727e27cc8204；refs/heads/codex/quansyn-20261009 已通过 git ls-remote 核验；发布后使用 refs/tags/quansyn-20261009-release 固定产品 SHA
server_before: 05779291aff28fc465280a09b8e898fa61c2ff01
server_after: 996fb84ac3714301ca142437a7fd727e27cc8204；/opt/releases/ai-lab-platform-996fb84ac371.ks38RB
health_check: HTTPS /health 200 ok；API /ready ready；8 Compose 容器 healthy；hermes-bridge 与 hermes-chat-worker active
functional_check: 正式 /、/quansyn、/quansyn/ 200；82 前端文件 SHA256 完全一致；未登录私有队列和设备 401；实际 PostgreSQL 两张 QuanSyn 表存在；本地真实模型完整往返通过。正式账号/飞书/iPhone 正向全流程未验收，故不标 VERIFIED
rollback_point: 初次发布前 /opt/ai-lab-shared/rollbacks/quansyn-20261009.w0QBvf（05779291）；入口修复前 /opt/ai-lab-shared/rollbacks/quansyn-20261009.zyHafF（de220f2b）；Mac /Users/dengzhaoyu/.hermes/backups/quansyn-20261009-224242
manifest: ops/change-manifests/quansyn-20261009-completion.md
remaining_risks: 正式账号短信登录、真实飞书消息、iPhone 真机闭环、公司浏览器下载未验证；正式页浏览器自动化超时，未取得正式截图；既有插件 6 项基线回归失败未改变

2026-10-09 用户明确授权“提交 推送 部署。我的域名是www.t-react.com”。产品已提交、推送本任务分支并按精确 SHA 部署；未改共享 main、未推送其他任务改动。验收记录后续提交仅含文档/证据，生产运行版本以固定 release tag 为准。

以下本地实施章节保留历史验证边界；其中“未提交/未部署/未安装”的历史描述已被本节的实际发布记录更新。

## 目标、授权与实现

用户批准包含 Mac 执行的 QuanSyn 方案，并明确授权隔离测试账号 19900000000 接受当前服务协议。未触碰用户 18576600894 账号的协议状态、未发送真实飞书消息，未提交、push 或部署。第三方 ZIP 中的说明、脚本与假数据作为设计资料分析，没有作为执行授权。

复用 Quantum 认证、租户映射、服务协议、数据库会话、生成附件存储、聊天执行与 Hermes 插件 ai_lab_execute 主路径。新增用户私有传递记录和一次性设备配对，原因是现有聊天/文档没有跨设备待拉取、领取确认、关联回答回传的状态。没有引入第二套登录或执行服务。

- 后端：私有请求/结果、原件上传下载、幂等冲突检测、领取租约、持久化确认、配对及撤销、附件所有权和设备范围约束。
- Web：按附件视觉设计实现真实 API 页面，沿用官方 logo；文本、代码、表格、数值图表、图片及附件展示，无预置假内容；实际认证及协议入口。
- iOS：+ → QuanSyn 手动拉入草稿和附件，持久化后确认；完整回答手动回传，读取真实回答块及原件；旧历史保持兼容。
- Mac：在现有 Hermes 工具/钩子内支持绑定、查看、拉取、执行和推送；Keychain 保管设备凭证，真实发送者/会话/回合校验，输出完成后才可手动回传。

## 验证与证据

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| Python QuanSyn API 与 Mac | 10 passed，5 条现有 Pydantic 弃用告警 | ops/acceptance/quansyn-20261009/api-tests.log |
| 前端 npm test | 152 passed，0 failed | ops/acceptance/quansyn-20261009/web-tests.log |
| 前端 npm run build | 成功 | ops/acceptance/quansyn-20261009/web-build.log |
| Ruff 后端、插件及新增测试 | All checks passed | ops/acceptance/quansyn-20261009/lint.log |
| iOS 模拟器测试（排除必须签名的 Keychain 测试） | 326 tests，2 skipped，0 failures | ops/acceptance/quansyn-20261009/ios-tests.log |
| 单独 ad-hoc 签名 Keychain 测试 | 1 test，0 failures，TEST SUCCEEDED | ops/acceptance/quansyn-20261009/ios-signed-keychain.log |
| 扩展插件回归 | 108 passed，6 failed；原基线同 6 项失败，未计为新增故障 | plugin-regression.log 与 baseline-regression.log |
| git diff --check | 通过 | 本次命令无输出、exit 0 |
| 本地服务健康 | HTTP 200，ok | ops/acceptance/quansyn-20261009/local-health.json |
| 真实 Mac 模型闭环 | 完成，附件字节/哈希核对一致 | ops/acceptance/quansyn-20261009/real-flow.json |
| 网页实际展示、复制 | 已显示真实 PNG/代码/表格/图表；剪贴板 518 字符含 60、20.00 和实际表格 | ops/acceptance/quansyn-20261009/web-result.jpg |

测试命令、Mac 配置和使用步骤见 docs/plans/quansyn-20261009.md。Python 使用隔离 Python 3.12 环境，测试数据库和附件目录都位于 /private/tmp/quansyn-acceptance；没有生产数据。前端 320×760 与 1024×900 检查了布局、横向溢出和输入框可见性，浏览器尺寸已恢复默认。

真实闭环使用本机现有 Hermes AIAgent、实际模型 gpt-5.6-sol、当前已有登录及代理配置，未替换成 mock 模型。通过可信 Feishu 形状的本地运行上下文测试了生产插件入口，但没有经过真实飞书消息网络。

请求 qs_cb6084ec85e1f9c16713e48aa26d5a59；结果 qs_207dc2f0cc5fda526b51289dde48f80f。实际数据 12、18、30，总和 60、均值 20.00。CSV 70 字节，SHA256 e91ec77780c2fdca189cd98a28cde2f26a3f092a42af1a79715212acfe948235；PNG 21317 字节，SHA256 c000661ae4b575e3a6b9f8234c80d3318d03e8bb85f09334f224d4fdb0877b30。

本地 API 下载及图片解码通过；内置浏览器点击下载后未收到落盘事件，外部 Chrome 自动化连接超时，因此不声称公司浏览器下载已验收。网页文本复制已实际核对剪贴板。最终租户映射/响应缓存安全调整另通过 API 测试，未再次消耗模型重跑。

验收后已撤销 1 个本地测试设备并删除其 Keychain 项（exit 0）。保留本地测试记录及预览服务供审阅；未安装或替换正式 Mac 插件。测试凭证不在源码或验收资料内。

## 变更文件

- agency/hermes-plugins/ai-lab-capabilities/__init__.py
- agency/hermes-plugins/ai-lab-capabilities/capability_router.py
- agency/hermes-plugins/ai-lab-capabilities/quansyn.py
- backend/api/quansyn.py
- backend/contracts/quansyn.py
- backend/db.py
- backend/main.py
- backend/models/quansyn.py
- docs/plans/quansyn-20261009.md
- frontend/public/quansyn/logo.png
- frontend/src/app/App.jsx
- frontend/src/auth/AuthContext.jsx
- frontend/src/features/quansyn/QuanSynPage.jsx
- frontend/src/features/quansyn/content.js
- frontend/src/features/quansyn/design.css
- frontend/src/features/quansyn/quansyn.css
- frontend/src/services/platformApi.js
- frontend/tests/quansyn.test.mjs
- ios/AIPlatformApp/Models/UIModels.swift
- ios/AIPlatformApp/Networking/APIClient.swift
- ios/AIPlatformApp/Views/Chat/Cards/AttachmentCard.swift
- ios/AIPlatformApp/Views/Chat/ChatView.swift
- ios/AIPlatformApp/Views/Chat/Components/BubbleActionBar.swift
- ios/AIPlatformApp/Views/Chat/Components/ChatMessageStreamView.swift
- ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift
- ios/AIPlatformApp/Views/Chat/MessageBubbleView.swift
- ios/AIPlatformApp/Views/Chat/PlusMenuSheet.swift
- ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift
- ops/acceptance/quansyn-20261009/local-health.json
- ops/acceptance/quansyn-20261009/real-flow.json
- ops/acceptance/quansyn-20261009/web-result.jpg
- ops/change-manifests/quansyn-20261009-completion.md
- tests/test_quansyn.py
- tests/test_quansyn_mac.py

## 远端只读证据

命令 git ls-remote origin refs/heads/main，结果：
```text
de3c2ad00a4fb33029d7138f52622689be3267e7 refs/heads/main
```
origin: https://github.com/Johnie198946/Quantum.git
source: https://github.com/Johnie198946/ai-lab-platform.git

这仅核验开发基线，不是本任务 PUSHED 状态证据。

## 原目录 Git 盘点
### git status --short --branch
```text
## main...origin/main [behind 64]
 M AGENTS.md
 M backend/api/chat.py
 M backend/api/documents.py
 M backend/api/workflows.py
 M backend/capability_handlers.py
 M backend/contracts/product-capabilities/bindings.yaml
 M backend/contracts/product-capabilities/capabilities.yaml
 M backend/contracts/product-capabilities/generated_artifacts.yaml
 M backend/contracts/product-capabilities/ios-scope.yaml
 M backend/services/capability_catalog.py
 M backend/services/capability_gateway.py
 M backend/services/client_actions.py
 M backend/services/workflow_artifacts.py
 M backend/services/workflow_executor.py
 M backend/services/workflow_planner.py
 M backend/services/workflow_planning.py
 M docs/product-capability-coverage.json
 M docs/product-capability-manual.md
 M ios/AIPlatformApp.xcodeproj/project.pbxproj
 M ios/AIPlatformApp/AIPlatformApp.swift
 M ios/AIPlatformApp/Models/UIModels.swift
 M ios/AIPlatformApp/Networking/APIClient.swift
 M ios/AIPlatformApp/Views/Chat/Cards/ImageCard.swift
 M ios/AIPlatformApp/Views/Chat/ChatView.swift
 M ios/AIPlatformApp/Views/Chat/Components/ChatStatusCards.swift
 M ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift
 M ios/AIPlatformApp/Views/Chat/MessageBubbleView.swift
 M ios/AIPlatformApp/Views/Chat/NativeClientActionHost.swift
 M ios/AIPlatformApp/Views/Chat/PlusMenuSheet.swift
 M ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift
 M ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift
 M ios/AIPlatformAppUITests/ProductionBookshelfUITests.swift
 M ios/project.yml
 M ops/acceptance/ios-capability-matrix.json
 M ops/change-manifests/bookshelf-functionality-20260927-completion.md
 M ops/change-manifests/chat-cleanup-client-compat-20260927-completion.md
 M ops/change-manifests/chat-cleanup-pcm-20260927-completion.md
 M ops/change-manifests/cleanup-exercise-testflight-20260927-completion.md
 M ops/change-manifests/note-audit-recovery-20260927-completion.md
 M ops/change-manifests/note-organization-v2-20260927-completion.md
 M ops/change-manifests/note-quality-acceptance-20260927-completion.md
 M ops/change-manifests/quantum-note-save-consent-20260927-completion.md
 M ops/change-manifests/quantum-notes-release-20260927-completion.md
 M ops/change-manifests/reader-experience-release-20260927-completion.md
 M scripts/hermes_bridge_runtime/agent_execution.py
 M scripts/hermes_bridge_runtime/knowledge.py
 M scripts/hermes_bridge_runtime/workflow_artifacts.py
 M scripts/hermes_bridge_runtime/workflow_runtime.py
 M tests/test_cleanup_capabilities.py
?? :memory:.ses
?? backend/services/image_processing.py
?? ios/AIPlatformApp.xcodeproj/project.xcworkspace/xcshareddata/
?? ios/AIPlatformApp/Mantis-LICENSE.txt
?? ops/acceptance/image-workflow-20260927/
?? ops/acceptance/receipts/
?? ops/change-manifests/cleanup-diff-20260927-completion.md
?? ops/change-manifests/image-workflow-20260927-completion.md
?? ops/change-manifests/quantum-2.0-hermes-gate-i0-20260909-completion.md
?? tests/test_image_processing.py
```

### git branch --show-current
```text
main
```

### git rev-parse HEAD
```text
21250c7b8a5290abcf649b9279bbd91b9af1db88
```

### git remote -v
```text
origin	https://github.com/Johnie198946/Quantum.git (fetch)
origin	https://github.com/Johnie198946/Quantum.git (push)
source	https://github.com/Johnie198946/ai-lab-platform.git (fetch)
source	https://github.com/Johnie198946/ai-lab-platform.git (push)
```

### git worktree list --porcelain
```text
worktree /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
HEAD 21250c7b8a5290abcf649b9279bbd91b9af1db88
branch refs/heads/main

worktree /private/tmp/quantum-ryg-audit-fc1b2f8
HEAD fc1b2f88c4a4e0c1d0a393e2e58eb62b92626114
detached
prunable gitdir file points to non-existent location

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/bookshelf-review-compat-20260928
HEAD 9e393b76b0bb01cb69827567a94ee5c403233afa
branch refs/heads/codex/bookshelf-review-compat-20260928

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/chat-media-refresh-20260928
HEAD 9e393b76b0bb01cb69827567a94ee5c403233afa
branch refs/heads/codex/chat-media-refresh-20260928

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/gemini-review-gate-20261008
HEAD bf3a3cc49619fab39eea449ca8c5bd337ce4bf17
branch refs/heads/codex/gemini-review-gate-20261008

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/image-studio-refresh-20260928
HEAD 9e393b76b0bb01cb69827567a94ee5c403233afa
branch refs/heads/codex/image-studio-refresh-20260928

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/image-studio-v4-20260927
HEAD 43fabf515e990a2b6aa1b0e8baa0891a0eaa021d
branch refs/heads/codex/image-studio-v4-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/ios-travel-pages-20261007
HEAD 0ab83f67bc89501f91d989444414d21796ca95a3
branch refs/heads/codex/ios-travel-pages-20261007

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/jev-pcm-routing-20260927
HEAD ecf5fd4881a157c6943ce7915db641f6d4dd58cc
branch refs/heads/codex/jev-pcm-routing-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/keyboard-dismiss-20260928
HEAD 9e393b76b0bb01cb69827567a94ee5c403233afa
branch refs/heads/codex/keyboard-dismiss-20260928

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/knowledge-ui-refresh-20260927
HEAD ae11b9bd8e30c89269ea8c59da7cf239fac86920
branch refs/heads/codex/knowledge-ui-refresh-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/opencv-packaging-fix-20261009
HEAD 6808f3230aa3859b0e50cb88f166543a1a84b906
branch refs/heads/codex/opencv-packaging-fix-20261009

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/quansyn-20261009
HEAD de3c2ad00a4fb33029d7138f52622689be3267e7
branch refs/heads/codex/quansyn-20261009

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/quantum-confirmation-fix-20260927
HEAD b9e4d128dd5839bae89cff39790fb8240297e23e
branch refs/heads/codex/quantum-confirmation-fix-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/server-no-response-20261009
HEAD eef7bea607301dc8841d8f3e41d9ea6c012be32a
branch refs/heads/codex/server-no-response-20261009

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-actions-20261008
HEAD 669fba1c612c8d35611d962ad5efb67bf785c3f3
branch refs/heads/codex/travel-actions-20261008

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-context-fix-20260928
HEAD fc1b2f88c4a4e0c1d0a393e2e58eb62b92626114
branch refs/heads/codex/travel-context-fix-20260928

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-creation-original-20261009
HEAD de3c2ad00a4fb33029d7138f52622689be3267e7
branch refs/heads/codex/travel-creation-original-20261009

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-input-cleanup-20261008
HEAD 40d6e3905362d8cac2f139a648f1764398a0f5f9
branch refs/heads/codex/travel-input-cleanup-20261008

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-notes-20260927
HEAD 370bd4c479e0f71fd7fed1c7743dc4291d73a7b5
branch refs/heads/codex/travel-notes-20260927

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/image-direct-processing-20260927
HEAD b9e4d128dd5839bae89cff39790fb8240297e23e
branch refs/heads/codex/image-direct-processing-20260927

worktree /Users/dengzhaoyu/Projects/publication-quality-20260928
HEAD 457abcd4284f5ab0910df1d138475894b963a782
branch refs/heads/feat/serial-narrative-quality-20260928

```

## 独立任务 Worktree Git 盘点
### git status --short --branch
```text
## codex/quansyn-20261009...origin/main
?? docs/plans/quansyn-20261009.md
```

### git branch --show-current
```text
codex/quansyn-20261009
```

### git rev-parse HEAD
```text
de3c2ad00a4fb33029d7138f52622689be3267e7
```

### git remote -v
```text
origin	https://github.com/Johnie198946/Quantum.git (fetch)
origin	https://github.com/Johnie198946/Quantum.git (push)
source	https://github.com/Johnie198946/ai-lab-platform.git (fetch)
source	https://github.com/Johnie198946/ai-lab-platform.git (push)
```

### git worktree list --porcelain
```text
worktree /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
HEAD 21250c7b8a5290abcf649b9279bbd91b9af1db88
branch refs/heads/main

worktree /private/tmp/quantum-ryg-audit-fc1b2f8
HEAD fc1b2f88c4a4e0c1d0a393e2e58eb62b92626114
detached
prunable gitdir file points to non-existent location

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/bookshelf-review-compat-20260928
HEAD 9e393b76b0bb01cb69827567a94ee5c403233afa
branch refs/heads/codex/bookshelf-review-compat-20260928

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/chat-media-refresh-20260928
HEAD 9e393b76b0bb01cb69827567a94ee5c403233afa
branch refs/heads/codex/chat-media-refresh-20260928

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/gemini-review-gate-20261008
HEAD bf3a3cc49619fab39eea449ca8c5bd337ce4bf17
branch refs/heads/codex/gemini-review-gate-20261008

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/image-studio-refresh-20260928
HEAD 9e393b76b0bb01cb69827567a94ee5c403233afa
branch refs/heads/codex/image-studio-refresh-20260928

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/image-studio-v4-20260927
HEAD 43fabf515e990a2b6aa1b0e8baa0891a0eaa021d
branch refs/heads/codex/image-studio-v4-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/ios-travel-pages-20261007
HEAD 0ab83f67bc89501f91d989444414d21796ca95a3
branch refs/heads/codex/ios-travel-pages-20261007

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/jev-pcm-routing-20260927
HEAD ecf5fd4881a157c6943ce7915db641f6d4dd58cc
branch refs/heads/codex/jev-pcm-routing-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/keyboard-dismiss-20260928
HEAD 9e393b76b0bb01cb69827567a94ee5c403233afa
branch refs/heads/codex/keyboard-dismiss-20260928

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/knowledge-ui-refresh-20260927
HEAD ae11b9bd8e30c89269ea8c59da7cf239fac86920
branch refs/heads/codex/knowledge-ui-refresh-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/opencv-packaging-fix-20261009
HEAD 6808f3230aa3859b0e50cb88f166543a1a84b906
branch refs/heads/codex/opencv-packaging-fix-20261009

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/quansyn-20261009
HEAD de3c2ad00a4fb33029d7138f52622689be3267e7
branch refs/heads/codex/quansyn-20261009

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/quantum-confirmation-fix-20260927
HEAD b9e4d128dd5839bae89cff39790fb8240297e23e
branch refs/heads/codex/quantum-confirmation-fix-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/server-no-response-20261009
HEAD eef7bea607301dc8841d8f3e41d9ea6c012be32a
branch refs/heads/codex/server-no-response-20261009

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-actions-20261008
HEAD 669fba1c612c8d35611d962ad5efb67bf785c3f3
branch refs/heads/codex/travel-actions-20261008

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-context-fix-20260928
HEAD fc1b2f88c4a4e0c1d0a393e2e58eb62b92626114
branch refs/heads/codex/travel-context-fix-20260928

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-creation-original-20261009
HEAD de3c2ad00a4fb33029d7138f52622689be3267e7
branch refs/heads/codex/travel-creation-original-20261009

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-input-cleanup-20261008
HEAD 40d6e3905362d8cac2f139a648f1764398a0f5f9
branch refs/heads/codex/travel-input-cleanup-20261008

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-notes-20260927
HEAD 370bd4c479e0f71fd7fed1c7743dc4291d73a7b5
branch refs/heads/codex/travel-notes-20260927

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/image-direct-processing-20260927
HEAD b9e4d128dd5839bae89cff39790fb8240297e23e
branch refs/heads/codex/image-direct-processing-20260927

worktree /Users/dengzhaoyu/Projects/publication-quality-20260928
HEAD 457abcd4284f5ab0910df1d138475894b963a782
branch refs/heads/feat/serial-narrative-quality-20260928

```

## 恢复与发布边界

所有修改保留在独立任务 worktree，没有暂存或提交；原 main 的其他任务改动未覆盖或混入。恢复时仅按本 manifest 所列文件审阅、恢复本任务差异，不使用共享 stash 或 reset --hard。

发布需要用户明确授权提交/push/部署；授权后仍需保存生产 server_before、建立 rollback_point、核验 git ls-remote 目标 SHA、部署 server_after、健康与功能检查，之后才能报告 VERIFIED。iOS 需要正式构建安装；Mac 需要更新实际插件配置并通过真人飞书消息完成验收。初期不做后台自动执行或自动回传，保持用户手动控制。

## 2026-10-09 用户纠正后的前端恢复

用户要求附件前端除品牌/logo外保持一致。上一版自行改写了布局及组件，未满足该要求；现已移除重设计覆盖，直接从 ZIP App.tsx 适配原 Icon、Brand、LoginPage、DeviceCard、CopyControl、CodeDetail、DetailDialog、DocumentSearch、ExitDialog 和 TransferPage（现名 TransferView）组件。

变更：frontend/src/features/quansyn/QuanSynDesign.jsx、QuanSynPage.jsx、design.css、quansyn.css。本次未改后端、iOS、Mac 或认证接口，继续复用既有数据流。原稿 CSS 的 2023 条声明值逐条匹配，见 ops/acceptance/quansyn-20261009/design-source-check.json；仅对选择器添加 QuanSyn 作用域，并补足原稿依赖的浏览器默认值隔离 Quantum 的全局样式。原稿 721–900px 区间的抽屉 display:none 遗留冲突修正为可打开，保留原缩放方式。

恢复了登录页背景/粒子/功能卡片，导航抽屉与页面缩放，搜索浮层、名称/内容筛选及空闲收起，文件卡片及详情缩放，图表/代码详情展开，消息回执布局，滚动进度/速度效果，以及 3 秒退出倒计时。完整回答、结构化表格/图表与原件使用真实后端数据，不保留初始演示消息或模拟发送/已读计时器。

必要业务差异明确保留：品牌改为 QuanSyn + 官方 Quantum logo；密码/Apple/免费注册入口改为当前 Quantum 手机验证码认证；虚构设备名称/在线状态、AES 端到端加密、2GB 限制与容量数字替换为真实名称、手动流程、账号权限和 25MiB 上限；未接通的演示稿生成按钮不冒充可用动作。

浏览器验收：隔离账号重新登录成功；原搜索浮层匹配真实 CSV/PNG；原退出确认显示 3 秒倒计时后退出；图表详情显示 12/18/30；代码详情显示完整实际代码；全文复制实际 518 字符含总和 60；通过原输入区提交新的真实需求，后端返回“已保存，待拉取”。320×760 时文档宽度 320，输入区域 bottom=725 在视口内；结束时已恢复浏览器默认尺寸，并关闭额外测试标签。

构建通过；前端 152 项测试全部通过；git diff --check 通过。记录于 design-build.log / design-tests.log。截图 restored-login.jpg 和 restored-web.jpg 为本次修正后的页面，先前 web-result.jpg 仅是上次验收历史，不代表最终视觉。当前仍为 TESTED，未 commit、push、部署；生产/真机/真实飞书/公司浏览器的未验收边界不变。

## 发布授权与生产基线（2026-10-09）

用户明确授权“提交 推送 部署。我的域名是www.t-react.com”。DNS www.t-react.com=120.24.248.58，现有严格 TLS HTTPS 入口响应 200。SSH 通过已配置部署身份及严格 known-host 校验，未打印或复制密钥。实际服务器基线 05779291aff28fc465280a09b8e898fa61c2ff01，release /opt/releases/ai-lab-platform-05779291aff2.uoUHch；8 容器 healthy，Bridge 和 chat worker active。

先提交本任务，再合入 GitHub 已核验且当前已部署的 server-health-fixes 分支，保留共享服务和工作流修复；不修改其他任务的 worktree/main。复用 exact-SHA update.sh 的部署锁、预期版本 CAS、镜像哈希证明及回滚。仅 www.t-react.com 的 SPA 首页跳转 QuanSyn，其他入口逻辑保留。尚未 push/deploy，此处只记录授权和预检。

## 合并后发布前验证

产品提交 f0c121e5；合并当前服务器基线提交 8d44a9d76bc3c8b221ab85f5003e0d8b8dc9f69a，无冲突。111 项后端/Mac/工作流/聊天流/容器边界测试全部通过（显式启用 pytest_asyncio.plugin）；前端 152 项通过，构建通过。日志存本地 release-tests.log、release-web-tests.log、release-build.log。共享发布链、资源预算和已部署工作流修复均保留。预检记录 release-preflight.json。

发布时必须使用推送后核验的精确源码 SHA、服务器部署锁及 expected-current=05779291aff28fc465280a09b8e898fa61c2ff01；源码和静态构建哈希对应，API/前端候选镜像验证通过后才切换。此提交时仍未部署；最终运行收据在操作完成后回填本地 manifest。

## 独立 Mac 安装校验

安装包按字节复制 canonical backend/contracts/quansyn.py 为 _quansyn_contract.py；独立包测试禁止 backend 导入，真实块校验及非法图表拒绝通过。相关后端/聊天/工作流/容器检查最终 112 passed；前端 152 passed，构建通过。

## 正式入口修复

首次正式 HTTPS 检查发现静态品牌目录与 /quansyn SPA 路由冲突。frontend/Dockerfile 为 /quansyn 和 /quansyn/ 添加精确 index.html 路由，保持 logo 路径及页面组件不变。生产页面需重新检查。首次部署 de220f2b，回滚备份 /opt/ai-lab-shared/rollbacks/quansyn-20261009.w0QBvf；8 容器及 API/Bridge 健康。

## 正式发布与回滚

证据：`ops/acceptance/quansyn-20261009/production-release.json`、`production-http.json`、`mac-install.json`、`deployment-wrapper.sh`。未下载数据库或输出密钥；源码离线档由 git archive 精确 SHA 生成，源包 SHA256 `04723d2ba56ad5bb2f6fcf1b7c3e9cfc1b5bfe2a3e5c93ee190c7c8038ec7edf`；前端 82 个字节哈希经候选镜像和正式 HTTPS 两次核对。发布前继承部署锁及 expected-current-SHA 检查，无覆盖并行发布。

首次前端候选包权限检查在生产切换前阻断，修正 nginx 可读权限后通过；首次正式入口检查识别静态目录与 SPA 冲突，已通过 996fb84a 修复并重新验证两个入口均为 200。当前镜像 revision 与实际源码 SHA 一致。最后修改的容器合同检查 16 passed；此前完整相关检查 112 passed，前端 152 passed。

回滚使用现有 scripts/update.sh 精确版本流程：取得部署锁并核验当前 SHA，按初次备份 images-before.txt 恢复 05779291 对应标签及 offline-images.attested.before，再以对应 root-owned 离线源包执行 update.sh，核对 API、Bridge、容器及域名。新增 QuanSyn 表为 additive，不应为了应用回滚删除表或恢复数据库覆盖后来数据；数据库 dump 与 SQLite 原件仅供必要的数据恢复。回滚操作尚未执行。

Mac 仅替换 __init__.py、capability_router.py、quansyn.py 和由 canonical 后端生成的 _quansyn_contract.py；其他模块不动，YAML 更新前后比较其余数据完全一致。Hermes 原生重启通过；launchd PID 从 1520 变为 14559；独立 PluginManager 加载、正式 API 地址、canonical contract 均通过。设备尚需用户在正式网页手动配对，未代替用户接受生产协议。Mac 回滚需先核对当前文件与 mac-install.json 哈希，恢复备份中的既有模块/配置并通过原生网关重启；未存在的新增模块仅在确认属于本任务后移除。

使用入口：https://www.t-react.com/quansyn。真实账号登录后，Web 选择 Mac 并生成配对码，在现有机器人发“绑定 QuanSyn <配对码>”；发送需求后发“拉取并执行 QuanSyn qs_实际编号”，完成后发“推送 QuanSyn qs_实际编号 附件 1,2”（附件按真实清单选择）。首版仍为人工触发。


## 2026-10-09 23:25 继续验收与登录按钮调整（尚未发布）

本段与上方已部署产品记录分开：新增按钮改动及模拟器验收暂为 LOCAL_ONLY，未提交/未推送/未部署。

- 开工盘点：分支 codex/quansyn-20261009，HEAD 7bdc23b791097b6395fad3ae84672fa3d6f03167，origin https://github.com/Johnie198946/Quantum.git；工作区只包含本任务 QuanSynDesign.jsx、quansyn.css、ProductionBookshelfUITests.swift 改动。独立 worktree 路径沿用本任务。其他 worktree/main 未改动。
- 修改范围：上述三文件、frontend/tests/quansyn.test.mjs、本 manifest。继续复用手机验证码认证，不新增跨端认证边界；跨端一次性 App 授权方案等待用户按 AGENTS.md 确认。
- 按钮：图标主导、文字辅助；300ms ease-in-out 缩成圆形，旋转加载至少 1.2 秒；真实短信发送成功才绿色描画对勾；失败显示错误；1 秒后恢复，避免与提交动作重叠。
- 验证：前端 154 项测试全部通过，包含实际动效处理函数时序、慢请求、错误、卸载取消与忙碌保护；前端构建通过（最终提交按钮禁用条件调整也已重新构建通过）。浏览器/原生界面检查被 Mac 锁屏阻止，未获得动效实测截图。
- 最新已完成的模拟器产品：/private/tmp/quansyn-derived-data/Build/Products/Debug-iphonesimulator/AIPlatformApp.app，1.0.3（84），此前完成时间 21:13。今晚旅行任务之后完成的是 iphoneos 构建，不能直接装到模拟器。新建独立 QuanSyn-20261009，UDID 24B48A56-1C35-4F01-9E95-DD91E1C60333，安装启动成功（PID 21005）。正常认证用例运行中，不注入令牌、不复制真机 Keychain。
- USB XCTest 首次构建失败：XCUIElement.lastMatch 不存在，已改正；没有真机通过证据。用户随后要求模拟器，未继续 USB。
- 生产只读核验：服务器 .deployed-sha=a9c1bfe97ebb17a7c21ecfe47e43812b4e9cb07b（服务器修复任务已包含996fb84产品发布）；直接 API /api/v1/auth/capabilities 返回 phone enabled=true；Authen 六个 authen@*.service active，8001 /health 200。未发生产验证码、未变更生产认证配置。
- 当前续作 remote_sha/server_after/rollback_point：未执行新发布；先前发布证据仍在上方，新发布前必须保留 a9c1bfe 的服务器修复并建立回滚点。
- 未完成：Mac 解锁后的动效界面检查；模拟器正常账号登录后真实 Web→App→Web 流程；经确认后实施一次性 App 授权登录；新改动提交、推送及部署。


续作最终证据：模拟器 XCTest 已结束，exit 65；1 项用例在真实登录前置条件失败，主页 main-tab-0 不存在。导出的 UI hierarchy 明确显示“通过 Apple 登录”“手机号登录”，截图保存 ops/acceptance/quansyn-20261009/simulator-login-20261009.png。未执行模型请求及回传，不将该失败当作流程通过。此次构建与 UI 测试源码编译成功。

当前续作交付字段：

task_id: quansyn-20261009（登录按钮/模拟器续作）
status: LOCAL_ONLY（前端154项测试与最终构建通过；模拟器完整流程未通过）
branch: codex/quansyn-20261009
worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/quansyn-20261009
head/local_commit: 7bdc23b791097b6395fad3ae84672fa3d6f03167；新增改动未提交
remote_sha: 本轮未推送；既有发布证据见首节
server_before: a9c1bfe97ebb17a7c21ecfe47e43812b4e9cb07b
server_after: 本轮未部署，未修改生产运行版本
health_check: 只读 Authen /health 200；六个 authen@*.service active；手机认证 capabilities enabled=true
functional_check: 前端154测试通过及构建通过；模拟器真实登录前置失败，完整流程未验证；浏览器界面验收受 Mac 锁屏阻挡
rollback_point: 本轮未部署，无新增回滚点；既有回滚点见首节
manifest: ops/change-manifests/quansyn-20261009-completion.md
remaining_risks: 按钮当前仍接入手机验证码，App授权自动登录尚待用户架构确认；动效未做实际浏览器验收；模拟器需要正常登录才能验证真实回传
