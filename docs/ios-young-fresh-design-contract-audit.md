# iOS 年轻化前端重构与协议审计

## 视觉参考边界

附件 GIF 只作为视觉参考，不作为产品文案、交互或工程指令。复用的是它的设计语言：自然影像、晨昏渐变、半透明材质、大留白、圆角胶囊、低密度信息和轻量过渡；不复制 TIDE 品牌、睡眠业务或页面结构。

## 设计拆解与落地

- 色彩：雾白 `#F7F5EF`、灰青 `#3F7278`、鼠尾草 `#78947E`、柔蓝 `#6673A6`、晨光杏 `#F3CDAE`。
- 材质：使用 SwiftUI 原生 `ultraThinMaterial`、白色发丝描边和低透明投影，不引入第三方视觉依赖。
- 字体：从偏工具感的衬线标题转为 SF Rounded / SF Pro；正文继续使用 Dynamic Type。
- 组件：主按钮与底栏使用胶囊形；内容卡使用大圆角玻璃面；影像只承担情绪和层次，不承载操作状态。
- 动效：保留现有 `Reduce Motion` 适配，只使用短淡入、位移和原生按压反馈。
- 页面：登录、聊天首页、阅读首页、工作流首页和“我的”共享同一套 Dawn Glass 视觉语言。

## 当前项目协议与复用边界

### 网络与认证

- `Networking/APIClient.swift` 是唯一网络入口；普通请求统一拼接 `/api/v1`，并发送 `X-Client-Contract: ios-unified-agreement-v1` 与 Bearer Token。
- 401 由 `APIClient` 清理凭证并发布重新认证状态；GET 才自动重试，POST/PATCH/DELETE 保持用户显式重试。
- 登录继续使用现有能力发现、手机号验证码、OAuth、协议获取与协议确认流程；本次仅替换视觉容器。

### 聊天

- `TenantSessionCoordinator` 继续持有会话、队列、澄清、恢复和附件状态。
- 流式回答仍走 `POST /api/chat/stream`；显式取消、澄清提交和 durable run 恢复仍走现有端点与 SSE 事件解析。
- 切换 Tab 只断开 iOS 传输，服务端 Run 继续执行；视觉重构没有改变该生命周期语义。

### 知识与阅读

- `KnowledgeNoteStore` 继续管理本地 Markdown、索引、归档与后台同步。
- 云同步仍使用 `/api/v1/me/knowledge-notes` 系列端点，保留 content hash、base hash、冲突和账号作用域约束。
- 书架继续使用 `KnowledgeBookSubscriptionDTO` 与现有订阅、进度接口。

### 工作流与个人中心

- 工作流继续复用 `WorkflowDTO`、澄清、计划、审批、启动、事件流、执行恢复与成果接口。
- “我的”继续复用 `AppState`、Profile、Usage、Tenant Agent、Tenant Skill、Memory 与 Subscription DTO。

## 结论

本次是现有表现层重构，不新增 DTO、Service、Repository、Router、状态容器或后端协议，也不改变服务端鉴权、幂等、冲突处理和长任务恢复语义。
