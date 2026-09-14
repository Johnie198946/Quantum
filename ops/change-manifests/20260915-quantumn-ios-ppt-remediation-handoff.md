---
title: Quantumn iOS 交互、串扰与 PPT 全链路返工交接
aliases:
  - Quantumn iOS PPT 返工交接
  - 20260915 iOS PPT Remediation Handoff
date: 2026-09-15
status: handoff-no-go
branch: main
tags:
  - quantumn
  - ios
  - workflow
  - ppt
  - pcm
  - handoff
---

# Quantumn iOS 交互、串扰与 PPT 全链路返工交接

> [!danger] 当前结论
> **NO-GO。需求没有全部实现，也没有发布。**
>
> 本地已完成键盘、自动跳转、Agent 描述、工作流状态防回退、产物卡点击区域及生成上下文上限等修复；模拟器已真实走通伊斯坦布尔请求至“大纲预览确认 → 版式预览确认”。最终 PPT 生成仍被生产端旧的 12,000 字符限制阻断，因此全稿预览、PPTX 下载、视觉质量和完整无串扰均未验收。

## 1. 当前真源与状态

```text
task_id: 20260915-quantumn-ios-ppt-remediation
status: LOCAL_ONLY / NO-GO
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-ios-document-ppt-final-20260912
local_head: fec23ad9205f1ba4cfa9e96507e1cc01151e0c99
origin_main: fec23ad9205f1ba4cfa9e96507e1cc01151e0c99
production_sha: fec23ad9205f1ba4cfa9e96507e1cc01151e0c99
production_release: /opt/releases/ai-lab-platform-fec23ad9205f.hYCwvD
production_domain: https://t-react.com
rollback_point: fec23ad9205f1ba4cfa9e96507e1cc01151e0c99
```

生产健康状态复核：API、Frontend、Postgres、Redis、Planning Worker、Workflow Worker、Agent Evaluation Worker、Taskboard 均为 `running/healthy`。

> [!warning] 代码状态
> 当前 HEAD、`origin/main` 和生产 SHA 一致，但工作树存在 **9 个已修改代码文件**及多份未跟踪交接文档。当前返工代码未提交、未推送、未部署。禁止把生产健康解释为“本次修复已上线”。

## 2. 用户需求逐项状态

| # | 需求 | 当前状态 | 验收边界 |
|---|---|---|---|
| 1 | 键盘弹出后不得遮挡输入框 | **本地已实现，未发布** | 使用既有 `safeAreaInset` 与系统键盘安全区；模拟器中输入框和发送按钮可点击，定向 UI 测试通过 |
| 2 | 确认卡片后自动进入任务详情 | **本地已实现并有真实正向实测，未发布** | 全新伊斯坦布尔请求曾自动进入任务详情；首次挂载消费 pending、失败后保留 pending 的契约测试通过 |
| 3 | 执行中确认节点可预览、编辑 | **部分实现** | 大纲和版式已真实预览与确认；产物卡已改为整行可点击。当前仅有反馈、退回、重新生成；没有字段级直接编辑/保存契约 |
| 4 | Agent 描述回答功能、适合、边界，≤100字并支持折叠 | **本地已实现，未发布** | 描述生成和折叠边界测试通过；仍需逐 Agent 验证文案准确性 |
| 6 | 根除跨 Session 串扰 | **未闭环** | 服务端 mapping 锁、原子读改写和刷新已在生产基线；但客户端重启后仍曾显示无关旧任务活动条，需继续核查客户端恢复与全局活动投影 |
| 7 | 用伊斯坦布尔材料完成优质 PPT 全链路测试 | **未完成** | 已走通需求、方案、Agent、大纲、版式；最终 deck 生成失败，尚无新全稿/PPTX 下载结果 |
| 7a | 模板达到优品 PPT 风格 | **不达标** | 返工前本地产物严格评分约 4/10；缺旅行照片、地图、图标、布局变化和视觉叙事 |
| 7b | 小白体验、少步骤、低学习成本、动效 | **不达标** | 确认层级仍多，失败恢复和下一步引导不足；当前 Renderer 没有 PPT 动画能力 |
| 7c | PCM 支持 PPT、Word、研究报告、论文及扩展 | **部分实现** | PPT 和通用文档工作流存在；Word、研究报告、论文尚不是带独立格式、引用、审查契约的一等能力 |
| 7d | 统一组件库覆盖 iOS 功能 | **部分实现** | 已复用现有 Workflow、Artifact Preview、RendererRegistry、QCP 主链；不能声称覆盖全部 iOS 功能 |
| 7e | 后端瘦身、简化、去冲突 | **只完成体检，未完成重构** | 已发现巨型文件、状态回退和输入上限复用冲突；尚未拆分状态机、执行器、路由和事件投影 |

## 3. 已完成的本地代码修改

### 3.1 键盘与底部布局

- 继续复用 `ChatView.safeAreaInset` 和系统键盘安全区。
- 移除基于焦点状态追加固定像素底部 padding 的假修复。
- 验收口径：键盘弹出后输入区域可见，发送按钮可点击。

涉及文件：

- `ios/AIPlatformApp/Views/Chat/Components/ChatInputBar.swift`：首轮临时修改已撤销，最终不保留固定像素方案。
- `ios/AIPlatformAppUITests/ProductionBookshelfUITests.swift`：增加键盘可点击回归。

### 3.2 确认后自动跳转

统一复用 `AppState` 与 `NavigationStack`，未新建第二套路由：

1. Workflow 创建/恢复事件调用 `AppState.openWorkflow`；
2. 切换到底部任务 Tab；
3. `WorkflowDashboardView` 首次挂载时消费 pending workflow；
4. fetch 失败时不清空 pending，允许后续重试；
5. 只有任务详情成功打开后才消费该请求。

涉及文件：

- `ios/AIPlatformApp/Models/UIModels.swift`
- `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
- `ios/AIPlatformApp/Views/MainTabView.swift`
- `ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`

### 3.3 工作流状态防回退

真实 E2E 暴露：Agent 已进入 `agent_ready` 后，迟到的 `building_agent` 回读会覆盖本地新状态，导致“启动任务”入口消失并落入“正在恢复工作流状态……”死区。

本地修复：

- `building_agent` 继续显示生命周期页面，不进入空白恢复页；
- 已确认 `agent_ready` 时，拒绝迟到的 `building_agent` 回退；
- 保留真实 execution 状态优先级，不伪造完成态。

涉及文件：

- `ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`

### 3.4 产物预览与真实反馈边界

首轮新增的 `HermesReviewComponent` 没有接入真实 Artifact/version 主链，“保存修改”只是发送自然语言消息，属于伪保存，已删除。

最终方案：

- 复用 `WorkflowExecutionView`；
- 复用 `WorkflowArtifactPreview`；
- 复用 `RendererRegistry` 与 QCP Artifact 契约；
- 产物卡整行统一为一个不低于 44pt 的按钮；
- 为预览入口提供稳定 accessibility identifier；
- 支持现有反馈、修改大纲/版式、按页退回和重新生成；
- 在后端没有字段级版本保存、CAS 和保存回执前，不提供“直接保存修改”。

> [!important] “编辑”的准确口径
> 当前完成的是**预览 + 反馈 + 退回/重新生成**，不是 PowerPoint 式字段级直接编辑。若产品必须支持直接编辑，需先补后端 Artifact revision、字段 Schema、并发控制、保存回执和冲突处理，再由 iOS 接入；不能靠自然语言消息伪装保存。

涉及文件：

- `ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
- `ios/AIPlatformAppUITests/ProductionBookshelfUITests.swift`

### 3.5 Agent 描述规范

- 输出固定覆盖：`功能`、`适合`、`边界`；
- 总长度不超过 100 字；
- 只有实际存在折叠内容才显示展开/收起；
- 不用统一空泛营销句替代每个 Agent 的真实能力边界。

涉及文件：

- `ios/AIPlatformApp/Views/Settings/SettingsView.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`

### 3.6 最终 PPT 生成上下文上限

生产失败事实：

```text
workflow_id: wf_e7ca455ea0e55dc18f9e03ec2c9de487
execution_id: wfr_703ac45fb93a470c9f34cacbe6f62b0d
title: 穷游伊斯坦布尔：横跨欧亚，避坑又出片
final_status: failed
progress: 75
failed_node: presentation_deck
prompt_length: 13007
production_limit: 12000
```

问题是最终 PPT 节点错误沿用了聊天输入上限，不是用户材料非法。

本地修复：

```text
MAX_INPUT = 12000                       # 普通聊天/通用节点
MAX_GENERATIVE_WORKFLOW_INPUT = 32000  # PPT/Word 等生成节点
MAX_DOCUMENT_WORKFLOW_INPUT = 96000    # 私有源文档首节点
```

约束保持：

- 不静默截断；
- 生成节点超过 32,000 字符仍显式失败；
- 私有源文档继续保留独立上限；
- 已批准大纲、顺序、标题和设计绑定不丢失。

涉及文件：

- `scripts/hermes_bridge.py`
- `tests/test_document_presentation.py`

## 4. 生产期间发现并处理的运行故障

### 4.1 Workflow Worker 写权限

伊斯坦布尔执行曾在分析阶段长期停留 `0%`。生产日志确认 `workflow-worker` 无法写入：

```text
/app/data/vault/workflows
```

已执行的即时恢复：

- 修复共享 Vault 的 workflows 目录 ACL；
- API、Workflow Worker、Planning Worker 当前均以 UID/GID `10001` 运行；
- workflows 目录现有 `10001:rwx` 和默认 ACL；
- 重启 Workflow Worker；
- 容器内真实写入探针通过；
- 原执行从 `0% running` 恢复到 `50% awaiting_approval`，随后继续至 `75%`。

> [!warning] 遗留风险
> 这是生产运行态修复，不等于部署脚本已证明能在下一次 release 后稳定重建同样权限。`scripts/update.sh` 已有共享数据 ACL 逻辑，但仍需补一个针对 `vault/workflows` 的部署后写入探针，并在下一次部署回读 ACL，防止复发。

### 4.2 生产当前状态

截至交接时：

- 生产 SHA 仍为 `fec23ad9205f1ba4cfa9e96507e1cc01151e0c99`；
- 所有主要 Compose 服务健康；
- 伊斯坦布尔 execution `wfr_703ac...` 最终为 `failed/75%`；
- 失败原因是生产仍未包含 32,000 字符生成上限修复。

## 5. 模拟器 E2E 实际进展

使用 iOS Simulator 和用户提供的伊斯坦布尔材料执行。测试入口在：

```text
ios/AIPlatformAppUITests/ProductionBookshelfUITests.swift
IstanbulPresentationLiveE2ETests
```

### 已真实通过的链路

```text
全新对话
→ 输入伊斯坦布尔原文
→ 发送“基于以上信息，帮我做一个PPT”
→ 能力确认
→ 自动创建 Workflow
→ 自动进入任务详情
→ 确认需求
→ 审阅方案
→ 构建专属 Agent
→ 启动任务
→ 大纲产物预览
→ 确认大纲
→ 版式样稿预览
→ 确认并生成全稿
```

### 当前阻断

```text
presentation_deck
→ 输入 13007 字符
→ 生产旧上限 12000
→ run_failed
→ 未生成最终全稿 Artifact
→ 无法验证最终预览与 PPTX 下载
```

### E2E 证据

```text
/tmp/quantumn-live-e2e-4.xcresult
/tmp/quantumn-live-e2e-5.xcresult
/tmp/quantumn-live-continuation-2.xcresult
/tmp/quantumn-live-continuation-3.xcresult
/tmp/quantumn-live-continuation-4.xcresult
```

这些结果包记录了自动跳转、Agent 状态回退、Worker 权限故障、产物点击区域和最终输入上限等逐层暴露的问题。最后一轮不是测试脚本误报：生产 execution 已回读为 `failed/75%`。

## 6. 测试与校验状态

### 已通过

- `git diff --check`：通过；
- iOS Simulator Debug build：`BUILD SUCCEEDED`；
- iOS `build-for-testing`：`TEST BUILD SUCCEEDED`；
- 定向 iOS 单元/UI 测试：首次跳转、失败保留、描述边界、QCP 预览契约、键盘可点击均通过；
- 生成工作流上限定向测试：`3 passed`；
- Ruff：本次 Bridge 与测试文件检查通过。

最新 App 构建：

```text
/tmp/quantumn-final-review-derived/Build/Products/Debug-iphonesimulator/AIPlatformApp.app
```

### 未通过或未完成

Bridge 组合测试：

```text
69 passed
3 failed
```

三个失败位于旧 Session 测试：

- `TestSessionExistsAssertion.test_invalid_session_triggers_new`
- `TestContextCoherence.test_resume_preserves_context`
- `TestConcurrencyIsolation.test_concurrent_users_isolated`

失败表现：测试依赖进程级默认 `/opt/ai-lab-platform/data`，且直接修改内存 mapping，与当前“每次解析前刷新持久化 mapping”的实现冲突。它们与本次生成上限逻辑没有因果关系，但属于发布门禁遗留，必须改成每例独立临时 mapping/state-db 后再跑全套，不能标记为通过或忽略。

仍未通过：

- 全新伊斯坦布尔 clean-room E2E 全链路；
- 最终全稿 Artifact 预览；
- PPTX 下载与文件 hash 一致性；
- PPT 视觉质量验收；
- 完整跨 Session 隔离验收；
- 当前修复的生产部署与回读。

## 7. PPT 视觉与用户体验结论

返工前 8 页伊斯坦布尔本地产物位于：

```text
/Users/dengzhaoyu/quantumn-acceptance-20260915/artifacts
/Users/dengzhaoyu/quantumn-acceptance-20260915/artifacts/previews/montage.png
```

严格视觉评分约 `4/10`。主要问题：

- 页面以标题和正文为主；
- 留白过量但没有形成高级版式；
- 缺少伊斯坦布尔旅行照片；
- 缺少欧亚跨洲地图和路线视觉；
- 缺少地标、交通、支付、安全等图标系统；
- 模板重复，视觉节奏单一；
- 没有图片型、地图型或时间线型一等布局；
- 没有 PPT 动画/转场能力。

不能因为 PPTX 可生成就声称达到“优品 PPT”风格。下一轮必须对最终生产产物重新评分，至少检查：主题匹配、模板一致性、图文比例、地图/图标、颜色、字体层级、页面变化、信息密度、视觉叙事和导出稳定性。

小白体验的当前问题：

- 需求、方案、Agent、启动、大纲、版式、全稿存在多级确认；
- 页面可理解，但路径仍长；
- 失败后缺少明确的“发生了什么 / 是否保留进度 / 下一步怎么做”；
- 预览、反馈、退回、重新生成的边界需用用户语言呈现；
- 不能展示后端不支持的“保存修改”。

## 8. PCM、组件库与架构体检

### PCM

当前 PCM/Registry 能覆盖 PPT、知识、工作流和通用文档等部分能力，但不能声称覆盖全部 iOS 功能。

建议建立独立一等契约：

```text
document.word
report.research
paper.academic
```

每个契约至少明确：

- 输入 Schema；
- 输出 Artifact 类型；
- 引用与来源要求；
- 模板/格式规范；
- 审核点；
- 反馈与重生成语义；
- 版本、下载和回执；
- 能力边界与失败模式。

“随机扩展”不应解释为运行时任意生成一套未知协议。正确方向是：通过 YAML/Registry 注册新能力，由 Hermes 编译为原生工具，QCP 负责鉴权、确认、幂等与 handler binding。

### 统一组件库

必须继续复用：

- `WorkflowExecutionView`
- `WorkflowArtifactPreview`
- `RendererRegistry`
- QCP Artifact/review 契约

不要恢复 `ClarifyCard.swift` 中的平行 `HermesReviewComponent`，也不要让 iOS 单边定义 `review_card_v1` 或字段保存协议。

后续可把 `WorkflowArtifactPreview` 和工作流确认卡从巨型页面文件中抽出为独立组件文件，但必须保持同一状态与契约真源，不能复制逻辑。

### 后端瘦身

当前主要热点：

- `backend/api/quantum_workspace.py`：约 9,860 行；
- `scripts/hermes_bridge.py`：约 9,073 行；
- `backend/api/showroom.py`：约 3,222 行；
- `backend/api/workflows.py`：约 3,038 行。

建议边界：

1. `hermes_bridge.py` 拆分 Session mapping、Workflow state machine、Prompt assembly、Artifact binding、event projection；
2. `quantum_workspace.py` 拆分路由、领域服务和 DTO；
3. Workflow 状态转换集中到一个确定性状态机，拒绝旧状态回退；
4. Prompt 限制按聊天、生成工作流、私有文档分层，不共用一个常量；
5. Artifact 预览、审批、版本与下载使用同一契约；
6. 先加回归测试再拆文件，不做大爆炸式重写。

已发现的实际冲突：

- 聊天输入上限错误复用于最终 PPT 生成；
- 持久化远端状态可覆盖本地更新状态；
- UI 曾出现伪保存语义；
- 预览卡视觉上是整行，实际只有文字区域可点击；
- mapping 层修复通过，但客户端全局活动投影仍可能显示无关旧任务。

## 9. 下一位开发者执行顺序

> [!todo] P0：先恢复发布门禁
> - [ ] 阅读 `AGENTS.md` 和本交接，不覆盖三份既有未跟踪文档。
> - [ ] 审查当前 9 个修改文件的完整 diff。
> - [ ] 修复 3 个 Session 测试的临时文件隔离，不改变生产 mapping 语义。
> - [ ] 重跑 Bridge、document/presentation、workflow API、session locking 全套回归。
> - [ ] 重跑 iOS 单元测试、UI 定向测试、`build-for-testing` 和 Debug build。

> [!todo] P0：严格按 GitHub → 生产顺序交付
> - [ ] 仅显式暂存本任务代码与本交接；禁止 `git add .`。
> - [ ] 提交到本地 `main`。
> - [ ] 获得外部写入授权后推送 GitHub `main`。
> - [ ] 用 `git ls-remote` 验证远端 SHA 与本地一致。
> - [ ] 建立生产回滚点。
> - [ ] 部署同一个已核验 GitHub SHA，禁止直接复制未提交 Bridge 文件到服务器。
> - [ ] 回读 `.deployed-sha`、current release、Compose health、ACL 和 workflows 写入探针。

> [!todo] P0：重新跑完整伊斯坦布尔 E2E
> - [ ] 使用全新 Session 和全新 Workflow，不复用已失败 execution 作为最终 clean-room 证据。
> - [ ] 只输入用户提供的伊斯坦布尔材料，再发送“基于以上信息，帮我做一个PPT”。
> - [ ] 验证确认后自动进入任务详情。
> - [ ] 验证 Agent 状态不回退。
> - [ ] 逐级打开大纲、版式、全稿预览。
> - [ ] 验证反馈/退回语义真实，不出现伪保存。
> - [ ] 下载 PPTX，记录 workflow、execution、Artifact ID、version、bytes、SHA-256。
> - [ ] 验证 PDF preview 与 PPTX 版本绑定一致。
> - [ ] 检查所有页面只含伊斯坦布尔内容，不得出现 AI Lab、鹿儿岛、因特拉肯或其他 Session 主题。

> [!todo] P1：产品质量
> - [ ] 对新 PPT 做 montage 和逐页视觉评分。
> - [ ] 补图片、地图、图标、时间线等 Registry/Renderer 一等布局，而不是仅改 Prompt。
> - [ ] 重新评估确认步骤，合并无风险步骤；高风险/不可逆节点保留确认。
> - [ ] 建立 Word、研究报告、论文独立 PCM 契约及 E2E。
> - [ ] 对 Session 冷启动、切换、并发和全局活动条做串扰回归。

## 10. 验收完成定义

只有同时满足以下条件，才能把状态从 `NO-GO` 改为 `VERIFIED`：

1. 当前代码完成审查，所有约定测试无失败、无 skipped 冒充通过；
2. 当前修复已提交并推送 GitHub `main`；
3. 生产部署 SHA 与 GitHub SHA 完全一致；
4. 所有生产服务健康，workflows 目录真实写入探针通过；
5. 全新伊斯坦布尔请求完成自动跳转、大纲、版式、全稿和 PPTX 下载；
6. App 下载文件与生产 Artifact hash 一致；
7. 全链路没有其他 Session 内容；
8. 预览、反馈、退回、重生成和保存语义与后端能力一致；
9. PPT 视觉质量达到重新约定的门槛；
10. 留存 XCResult、截图、Artifact IDs、hash、server before/after 和 rollback receipt。

## 11. 当前工作树文件

已修改：

```text
ios/AIPlatformApp/Models/UIModels.swift
ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift
ios/AIPlatformApp/Views/MainTabView.swift
ios/AIPlatformApp/Views/Settings/SettingsView.swift
ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift
ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift
ios/AIPlatformAppUITests/ProductionBookshelfUITests.swift
scripts/hermes_bridge.py
tests/test_document_presentation.py
```

交接文档：

```text
ops/change-manifests/20260914-ios-build40-ppt-registry-routing-handoff.md
ops/change-manifests/20260914-ios-build40-ppt-registry-routing-handoff-final.md
ops/change-manifests/20260915-ios-uncommitted-rework-completion.md
ops/change-manifests/20260915-quantumn-ios-ppt-remediation-handoff.md
```

不得删除、覆盖或暂存不属于本任务的既有未跟踪文档。

## 12. 最终交接收据

```text
task_id: 20260915-quantumn-ios-ppt-remediation
status: LOCAL_ONLY / NO-GO
branch: main
head/local_commit: fec23ad9205f1ba4cfa9e96507e1cc01151e0c99
remote_sha: fec23ad9205f1ba4cfa9e96507e1cc01151e0c99
server_before: fec23ad9205f1ba4cfa9e96507e1cc01151e0c99
server_after: 未部署本次代码；仍为 fec23ad9205f1ba4cfa9e96507e1cc01151e0c99
health_check: 主要 Compose 服务 running/healthy
functional_check: 伊斯坦布尔链路通过大纲与版式确认，最终 deck 在 75% 失败
rollback_point: fec23ad9205f1ba4cfa9e96507e1cc01151e0c99
manifest: ops/change-manifests/20260915-quantumn-ios-ppt-remediation-handoff.md
remaining_risks: 最终 PPT 未生成/下载；串扰未闭环；视觉质量不达标；PCM/组件覆盖不完整；3 个 Session 测试未通过；当前代码未提交、未推送、未部署
```
