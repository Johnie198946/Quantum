# Quantum iOS V3–V5 逐页 1:1 复刻矩阵

验收口径：V3 52 个、V4 52 个、V5 9 个，共 113 个手机画面；每个画面都必须对应一个真实 SwiftUI 页面、Sheet 或可复现状态，不以“同风格”替代逐页复刻。V4/V5 对同一页面的修订以最新版覆盖旧版。真实用户数据、书籍内容和后端返回文案允许变化，但布局、层级、组件、颜色、间距、按钮和状态反馈必须一致。

## 2026-09-17 ImageToCode 实施记录

- 已从 29 张设计板逐手机框拆分出 113 张独立页面图：`docs/ios-v3-v5-pages/v3` 52 张、`v4` 52 张、`v5` 9 张；文件名保留版本、原板号、页序和页名，可直接逐页复验。
- 前端没有复制 113 套页面：这些画面是现有真实 SwiftUI 页面在空态、加载、成功、失败、Sheet、确认和阅读模式下的状态组合，继续复用下表所列入口及原有 API/DTO/store。
- 最新产品根导航按实施方案收敛为“首页 / 阅读 / 工作流 / 我的”；书架保留为阅读域内页面和可直达预览，不再作为第五根导航。
- 113 个原型状态均已由 `-prototypePreview <pageID>` 路由到真实 SwiftUI 组件或可复现状态，并逐页生成模拟器截图：V3 52、V4 52、V5 9。
- `docs/ios-v3-v5-validation/{v3,v4,v5}` 仅保存运行结果证据，不作为 App 页面或组件素材；前端中的交互图标使用 SF Symbols，位图只用于照片、插画和品牌资产。
- 原型页与验收页按文件名做集合比对，113/113 对应且差集为空。

## V3 · 完整功能板

| 原型板 | 页面 / 状态 | 既有实现入口 | 当前判定 |
|---|---|---|---|
| 01 | 启动、手机号、验证码、协议/错误 | `LoginView` / `AgreementSheet` | 已实现并留证（4/4） |
| 02 | Chat 空态、对话中、待发队列、会话管理 | `ChatView` / `SessionDrawerSheet` | 已实现并留证（4/4） |
| 03 | 智能创作、添加与导入、链接导入、语音 | `ChatInputBar` / `PlusMenuSheet` | 已实现并留证（4/4） |
| 04 | 澄清、确认、整理中、知识操作 | `ClarifyCard` / `ChatStatusCards` | 已实现并留证（4/4） |
| 05 | 富回答、沉浸阅读、来源预览、回答操作 | `MessageBubbleView` 及内容卡片 | 已实现并留证（4/4） |
| 06 | 知识首页、搜索、多选、智能整理、回收站 | `KnowledgeView` / `KnowledgeArchiveView` | 已实现并留证（4/4） |
| 07 | 笔记编辑、阅读、关联内容、恢复操作 | `KnowledgeNoteEditor` / `NoteReadingView` | 已实现并留证（4/4） |
| 08 | 工作流首页、新建、编辑计划、确认运行 | `WorkflowDashboardView` | 已实现并留证（4/4） |
| 09 | 执行、失败恢复、人工审核、成果 | `WorkflowExecutionView` / `WorkflowArtifactPreview` | 已实现并留证（4/4） |
| 10 | 拓扑、节点详情、评估设置、评估结果 | `TopologyCanvasView` | 已实现并留证（4/4） |
| 11 | 我的、创建智能体、记忆中心、记忆详情 | `SettingsView` / `AgentCreatorView` / `MemoryCenterView` | 已实现并留证（4/4） |
| 12 | 权益、方案、申请进度、管理员审核 | `SubscriptionCenterView` | 已实现并留证（4/4） |
| 13 | 书架、搜索、详情、沉浸阅读 | `SubscriptionCenterView` / `KnowledgeBookReaderView` | 已实现并留证（4/4） |

## V4 · 反馈细化板

| 原型板 | 页面 / 状态 | 既有实现入口 | 当前判定 |
|---|---|---|---|
| 01 | 登录字段级错误 | `LoginView` | 已实现并留证（4/4） |
| 02 | 轻思考、长按语音 | `ReasoningCard` / `ChatInputBar` | 已实现并留证（4/4） |
| 03 | 轻澄清、合并预览 | `ClarifyCard` / `NoteDraftCard` | 已实现并留证（4/4） |
| 04 | 极简工作流与计划 | `WorkflowDashboardView` | 已实现并留证（4/4） |
| 05 | 选择/预览/配置/试跑智能体 | `WorkflowPlanReviewView` | 已实现并留证（4/4） |
| 06 | Chat 转旅行任务 | `ChatView` → `WorkflowDashboardView` | 已实现并留证（4/4） |
| 07 | 图文旅行计划与导出 | `WorkflowArtifactPreview` | 已实现并留证（4/4） |
| 08 | 选词问答、问答批注、批注中心 | `KnowledgeBookReadingView` | 已实现并留证（4/4） |
| 09 | Chat 创建智能体 | `AgentCreatorView` | 已实现并留证（4/4） |
| 10 | 智能体知识/工具 CRUD | `SettingsView` + Tenant Agent API | 已实现并留证（4/4）；工具写入仍受后端契约限制 |
| 11 | ComfyUI 式工作流画布 | `WorkflowPlanReviewView` / `WorkflowCanvasEditor` | 已实现并留证（4/4） |
| 12 | 节点输入/输出与 A/B 对比 | `AgentNodeDetailSheet` / `AgentEvaluationView` | 已实现并留证（4/4） |
| 13 | 智能研究 / PPT | `WorkflowDashboardView` / `PresentationOutlinePreview` | 已实现并留证（4/4） |

## V5 · 启动页与旅行笔记

| 原型板 | 页面 / 状态 | 既有实现入口 | 当前判定 |
|---|---|---|---|
| 01 | 无副标题启动页 | `LoginView` | 已实现并留证（1/1） |
| 02 | 旅行计划转旅行笔记 | `WorkflowArtifactPreview` / `TravelNoteReadingView` | 已实现并留证（4/4） |
| 03 | 拍照、随写、AI 排版、确认 | `KnowledgeNoteEditor` / `TravelMomentComposer` | 已实现并留证（4/4） |

## 后端边界

- 可直接复用：Tenant Agent 创建/修改/删除、知识包订阅、工作流计划/执行/产物、记忆 CRUD、书架/阅读进度。
- `TenantAgentDTO` 可读取 `allowedTools`，但 `TenantAgentCreateDTO`/PATCH 当前没有工具写入字段；前端不得伪造“保存成功”。工具配置页面可以 1:1 呈现读取、测试与状态，但真正的增删改需等待既有后端契约提供写入字段。
- 视觉 1:1 不等于伪造业务数据：原型示例文案和图片使用真实返回内容替换，信息结构保持一致。

## 完成门禁

- 29 组、113 个手机页面/状态：已实现。
- 113 个页面/状态均有对应的真实模拟器截图：已完成，文件集合差集为空。
- iOS Simulator Debug 构建：通过；`WorkflowLifecycleDTOTests`：143/143 通过。
- 未提交、未推送、未部署；是否合并到主工作区仍由用户决定。
