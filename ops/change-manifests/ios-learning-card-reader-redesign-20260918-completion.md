# Completion Manifest

- task_id: `ios-learning-card-reader-redesign-20260918`
- 目标: 在现有 Quantum iOS 架构内重构工作流、确认、公式、代码、高亮、长文本阅读、图表、书架和书籍阅读体验，并保留现有数据模型、接口、阅读进度、提问和批注写入链路。
- 当前状态: `TESTED`

## 架构命中与变更范围

- 判定: 部分实现。服务端 DTO、`APIClient`、卡片分发、书籍正文/订阅/进度/批注链路已存在，缺少目标视觉和长文本分卡呈现。
- 复用入口: `BlockCardDispatcher`、`MessageBubbleView`、`LongAnswerSheet`、`WorkflowDashboardView`、`KnowledgeBookReadingView`、`KnowledgeNoteStore`。
- 未新增 service、repository、adapter、状态容器、数据模型或并行调用链。
- 本任务编辑文件:
  - `ios/AIPlatformApp/Views/Chat/Cards/MarkdownCards.swift`
  - `ios/AIPlatformApp/Views/Chat/MessageBubbleView.swift`
  - `ios/AIPlatformApp/Views/Chat/Cards/ChartCard.swift`
  - `ios/AIPlatformApp/Views/Chat/Cards/ClarifyCard.swift`
  - `ios/AIPlatformApp/Views/Chat/Components/ChatStatusCards.swift`
  - `ios/AIPlatformApp/Views/Chat/ChatView.swift`
  - `ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift`
  - `ios/AIPlatformApp/Views/Settings/SettingsView.swift`
  - `ios/AIPlatformApp/Views/Knowledge/KnowledgeView.swift`
  - `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`

## 开工前 Git 盘点

- status: 工作树在本任务前已有 V3–V5 前端、素材和文档的未提交改动；本任务未清理、还原、暂存或覆盖这些改动。
- branch: `codex/ios-v3-v5-style-sandbox-20260917`
- HEAD: `58d212f18ed1edd71d0a95d18b12fc0b820eb277`
- remote:
  - `origin`: 本地隔离仓库 remote
  - `source`: GitHub 源仓库
- worktree: `/Users/dengzhaoyu/Documents/AI Lab/.worktrees/quantum-ios-style-sandbox-20260917`
- worktree list: 本任务独占上述 worktree。

## 实现结果

- 工作流卡片使用真实 phase/status/output 数据展示四阶段进度，删除伪造数量和时间。
- 需求确认卡片使用可扫描的任务边界、选择和提交状态，原有 workflow 回调与 choice 文案协议不变。
- 公式、代码、高亮、图表卡片完成年轻化视觉重构，复制、文本选择和图表数据行为不变。
- 长文本由 `ReadingCardDeck` 按标题、分隔线和最大块数切成多张阅读卡；未改变服务端 Markdown 数据结构。
- 书架继续使用现有订阅与封面数据，加入轻量书卡层次；书籍阅读使用章节卡片。
- 选中文字后通过底部浮动操作坞执行“问 Quantum”或“写批注”；提问复用 Book scope，批注复用 `KnowledgeNoteStore` 和现有账户同步路径。
- DEBUG 原型验收页直接调用生产组件，不维护第二套展示实现。

## 测试与校验

- `git diff --check`: 通过。
- iOS Simulator build: 通过，`** BUILD SUCCEEDED **`。
- signed generic iOS device build: 通过，`** BUILD SUCCEEDED **`；签名身份 `Apple Development: Johnie Deng`，bundle id `com.ailab.AIPlatformApp`。
- 新增最小逻辑测试 `testReadingDeckStartsNewCardsAtHeadingsAndCapsDenseCards`: 通过。
- 现有阅读回归测试:
  - `testNativeReaderShowsWaitingPartialAndCompletedContentStates`: 通过。
  - `testReaderBodySurvivesSubscriptionFailure`: 通过。
- 模拟器视觉检查通过:
  - 长文本阅读与图表: `/private/tmp/quantum-card-p01.png`
  - 公式、代码与高亮: `/private/tmp/quantum-card-p02.png`
  - 书籍阅读: `/private/tmp/quantum-book-reader.png`
  - 书架: `/private/tmp/quantum-bookshelf.png`
  - 需求确认: `/private/tmp/quantum-confirmation-card.png`
  - 工作流: `/private/tmp/quantum-workflow-card.png`
- 真机安装与启动: 已完成。设备“囧尼部落”（iPhone 17 Pro）安装 bundle `com.ailab.AIPlatformApp` 成功；CoreDevice 详细启动日志确认 launch 成功，进程列表核验到 `AIPlatformApp`，PID `1137`。

## 交付与外部状态

- commit SHA: 未授权、未创建。
- GitHub remote/ref/SHA: 未授权 push，未执行 `git ls-remote`。
- server_before: 不适用，未授权且未执行服务器部署。
- server_after: 不适用，未授权且未执行服务器部署。
- health_check: 不适用，无服务器变更。
- functional_check: 模拟器六组视觉页面、相关测试、签名设备构建、真机安装与启动均通过；真机进程 PID `1137`。
- rollback_point: `58d212f18ed1edd71d0a95d18b12fc0b820eb277` 仅作为开工基线参考。工作树含其他未提交改动，禁止使用 reset；如需回滚，只能逐文件/逐 hunk 反向恢复本 manifest 所列变更。

## 风险与未完成项

- 选字菜单依赖 iOS 原生 `UITextView` 选择行为，编译和既有阅读回归测试已通过，仍建议由用户完成实际触控手势验收。
- 未提交、未推送、未部署。
