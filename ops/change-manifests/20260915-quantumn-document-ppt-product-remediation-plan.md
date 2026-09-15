---
title: Quantumn iOS 文档与 PPT 产品化修复实施方案
aliases:
  - Quantumn PPT Remediation Implementation Plan
created: 2026-09-15
status: approved-for-execution
priority: P0
tags:
  - quantumn
  - ios
  - ppt
  - pcm
  - remediation
---

# Quantumn iOS 文档与 PPT 产品化修复实施方案

> [!danger] 当前门禁
> 当前结论是 **NO-GO**。`58d212f18ed1edd71d0a95d18b12fc0b820eb277` 仅作为技术链路基线和回滚点；不得继续宣称内容、视觉、统一编辑组件、串扰和文档类 PCM 已完整交付。

## 一、目标与不变原则

### 产品目标

1. PPT 内容逐项忠于用户材料，视觉达到正式对外演示标准。
2. PPT 主路径压缩为“需求确认 → 可编辑全稿预览 → 下载”。
3. 所有确认节点使用统一 Schema 驱动组件，支持预览、字段编辑、保存、冲突处理和回执。
4. 冷启动、账号切换、会话切换、并发任务和迟到响应均不得串扰。
5. Word、研究报告、学术论文形成真实可验收能力，不只停留在契约和单页冒烟。
6. 保持 Hermes 为唯一 AI Runtime，PCM Registry 为唯一能力真源，不新增第二套 Runtime。

### 不变原则

- 用户原文优先于模型扩写；无来源内容必须明确标记并获得批准。
- 优品 PPT 仅用于研究信息架构与视觉语言，不复制其受版权保护素材。
- 所有图片、地图和图标记录来源、许可、哈希、MIME 与缓存状态。
- 后端与旧版 iOS 保持兼容；重构不得与业务行为修改同时混做。
- 自动化测试是前置门禁，用户人工确认才是 PPT 内容与视觉的最终门禁。

## 二、实施批次

## Batch 0：冻结基线与补失败测试

### 文件落点

- `ops/acceptance/quantumn-document-ppt-baseline.yaml`
- `tests/fixtures/presentation/istanbul-source.md`
- `tests/fixtures/presentation/istanbul-trace.expected.yaml`
- `tests/test_document_presentation.py`
- `ios/AIPlatformAppUITests/ProductionBookshelfUITests.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`

### 工作

1. 固化当前失败事实：11 页、105 个对象、0 个媒体对象、没有真实地图、内容叙事偏离。
2. 将用户原始文案存为不可修改测试夹具；生成输入事实清单与逐页 trace matrix。
3. 先补以下失败测试，再改实现：
   - 原文事实丢失、无来源扩写和跨会话材料混入；
   - 旅游主题没有摄影、地图或 SVG；
   - 确认卡不能字段级保存；
   - 迟到请求覆盖当前会话；
   - Agent 描述使用通用占位句；
   - Word/研究报告/论文只生成单页或无有效引用。

### 退出门禁

- 每个已知缺口都有可稳定复现的失败测试或验收脚本。
- 基线报告明确区分 `implemented / partial / absent / unverified`。

## Batch 1（P0）：内容保真与 PPT 视觉能力重建

### 1.1 内容保真

#### 新增/修改文件

- `backend/services/presentation_source_trace.py`：事实切分、来源定位、段落哈希、逐页映射。
- `backend/contracts/presentation/source-trace.schema.json`：`source_id / span / claim / slide_id / transform / approval_state`。
- `backend/services/presentation_scenario.py`：主题、受众、用途、语气和视觉目标选择。
- `scripts/hermes_bridge.py`：Prompt 仅消费批准材料和批准的补充来源。
- `backend/services/presentation_renderer.py`：把 provenance 写入 artifact manifest，不在页面正文泄露内部字段。
- `tests/test_presentation_source_trace.py`。

#### 规则

- 先生成“用户原文事实清单”，再生成大纲，不允许直接从聊天历史自由创作。
- 每页必须回溯到一个或多个 `source_id`；无来源声明默认拒绝进入成品。
- 外部补充内容与用户原文分层保存，并在全稿预览中明确显示来源。
- `source_client_session_id` 与材料集合绑定，禁止跨 session 取材。

#### 验收

交付以下四级映射：

`原文段落 → 批准大纲 → 页面/元素 → PPTX/PDF 成品`

硬门禁：

- 用户原文关键事实覆盖率 100%。
- 页面主张来源覆盖率 100%。
- 未批准的外部扩写为 0。
- 跨会话来源命中为 0。
- 关键词覆盖率作为诊断指标，不替代语义保真和用户确认。

### 1.2 旅游主题模板与素材系统

#### 新增/修改文件

- `backend/contracts/presentation/slide.schema.json`：新增 `hero_photo`、`photo_collage`、`geo_route_map`、`timeline`、`icon_facts`、`quote_photo`、`data_story` 等一等布局。
- `backend/contracts/presentation/themes/travel-editorial.yaml`：旅游杂志风主题。
- `backend/contracts/presentation/themes/travel-cinematic.yaml`：摄影叙事主题。
- `backend/services/presentation_materials.py`：素材搜索、许可、缓存、哈希、MIME 与真实格式校验。
- `backend/services/presentation_map.py`：地点解析、坐标、可编辑 SVG/PowerPoint shape 路线图。
- `backend/services/presentation_svg.py`：SVG 解析、颜色适配、可编辑矢量转换。
- `backend/services/presentation_renderer.py`：新布局渲染。
- `backend/contracts/presentation/material-manifest.schema.json`。
- `tests/test_presentation_materials.py`、`tests/test_presentation_map.py`、`tests/test_presentation_visual_gates.py`。

#### 素材策略

- 摄影：只使用允许商业使用或用户提供的素材；保存来源 URL、作者、许可、下载时间和 SHA-256。
- 地图：由地点/坐标生成真实地理表达；普通文本框、装饰线或虚构比例不得标记为地图。
- SVG：图标必须是独立矢量资产，不得以 `SEE/MAP/WALK` 文字徽章冒充。
- 缓存：下载后校验响应 MIME、文件签名、尺寸、解码能力和许可记录；失败时 fail closed。

#### 伊斯坦布尔样稿视觉门禁

- 1 张封面主视觉，至少 4 张场景摄影。
- 至少 1 页可编辑地理路线图，包含欧亚两岸、博斯普鲁斯海峡和景点节点。
- 至少 6 个真实 SVG/矢量图标。
- 至少 5 种布局家族，连续页面不得机械重复。
- 正文字号默认不低于 18pt；来源脚注可更小但必须可读。
- 无裁切、溢出、重叠、空白页和失真图片。
- PPTX 中图片/矢量对象和来源清单必须真实存在，不能只在 Prompt 中声明。
- 机器门禁通过后，必须把新 PPTX/PDF 发给用户人工确认；未确认不得标记视觉完成。

## Batch 2（P0）：统一可编辑确认组件

### 架构

新增通用 renderer：`structured_review`，不为 PPT 私建页面。Hermes/QCP 只提交受注册 Schema 约束的 review document；iOS 根据 Schema 渲染。

### 新增/修改文件

- `backend/contracts/product-capabilities/renderers.yaml`
- `backend/contracts/product-capabilities/events.yaml`
- `backend/contracts/product-capabilities/bindings.yaml`
- `backend/contracts/review/structured-review.schema.json`
- `backend/services/review_state.py`：版本、CAS、审计与撤销。
- `backend/api/workflows.py`：review 读取/保存薄路由。
- `ios/AIPlatformApp/Views/Components/StructuredReview/StructuredReviewView.swift`
- `ios/AIPlatformApp/Views/Components/StructuredReview/ReviewFieldView.swift`
- `ios/AIPlatformApp/Views/Components/StructuredReview/ReviewConflictView.swift`
- `ios/AIPlatformApp/Views/Chat/Cards/ClarifyCard.swift`：改为统一 renderer 接入。
- `ios/AIPlatformAppTests/StructuredReviewTests.swift`
- `ios/AIPlatformAppUITests/StructuredReviewUITests.swift`

### 功能

- 全稿预览和字段级编辑：文本、长文本、列表、选项、页面结构、素材替换。
- 每次读取返回 `version + ETag`；保存必须发送 `If-Match`。
- 服务端使用 CAS；冲突时展示本地版本、远端版本和差异，不静默覆盖。
- 保存后返回持久化回执；支持撤销和重新生成。
- 小屏、键盘弹出、底栏存在时，当前字段和主操作按钮始终可见可点。

### 验收

- 同一份全稿在两端并发编辑，第二次旧版本保存必须收到冲突，而不是覆盖。
- 保存后退出页面、杀进程、重新登录，编辑内容仍存在。
- PPT 默认仅保留“需求确认 → 可编辑全稿预览 → 下载”三步；风险门禁由策略显式开启。

## Batch 3（P0）：串扰彻底闭环

### 新增/修改文件

- `backend/api/workflows.py`：继续保留并强制验证 `source_client_session_id`。
- `backend/services/workflow_scope.py`：统一 tenant/user/client-session scope。
- `backend/services/workflow_projection.py`：权威 activity projection。
- `ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift`：additive cache 改为权威响应替换。
- `ios/AIPlatformApp/Models/UIModels.swift`：owner/session generation fence。
- `ios/AIPlatformApp/Views/MainTabView.swift`：切换 session 时递增 generation。
- `tests/test_workflow_scope.py`。
- `ios/AIPlatformAppTests/WorkflowSessionIsolationTests.swift`。
- `ios/AIPlatformAppUITests/ProductionSessionIsolationUITests.swift`。

### 机制

- workflow、execution、artifact 和 activity 均绑定 tenant、user、chat session。
- 请求发出时携带 owner/session/generation；响应回填前再次比对，迟到响应直接丢弃并记审计事件。
- 列表刷新采用服务端权威快照替换，不再永久累加本地旧 activity。
- legacy workflow 没有来源 session 时进入“历史任务”隔离区，不自动投影到当前聊天。

### 生产验收矩阵

- 双账号；每账号双会话。
- 四个任务并发。
- A/B 会话快速切换。
- 退出登录、重新登录。
- 杀进程、冷启动恢复。
- 制造网络延迟，让旧请求晚于新请求返回。
- 混入升级前 legacy workflow。

退出门禁：任何当前会话页面、activity、深链、产物列表中出现其他 owner/session 数据即失败；不能用“重启后暂未复现”代替通过。

## Batch 4（P1）：小白化体验与 Agent 描述

### 修改文件

- `ios/AIPlatformApp/Views/Settings/SettingsView.swift`
- `ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift`
- `ios/AIPlatformApp/Views/Chat/Cards/ClarifyCard.swift`
- `backend/contracts/product-capabilities/capabilities.yaml`
- `docs/product-capability-manual.md`

### 工作

- 确认后自动切入任务详情；失败显示原因和重试按钮。
- 统一主按钮位置、动效、进度反馈和撤销反馈；不制造伪执行链。
- 首次使用只显示当前一步及一句解释，高级选项折叠。
- Agent 描述从能力 Registry 的结构化字段生成，不再截断原描述拼通用句：
  - 功能：实际能完成什么；
  - 适合：具体任务类型；
  - 边界：数据、权限、质量或人工确认限制。
- 完整描述不超过 100 个中文字符，默认两行折叠，点击展开。

### 验收

- 每个 Agent 三段语义均不同且与 handler/policy 一致。
- 键盘、小屏和底栏场景下无控件遮挡。
- 新用户不看文档也能完成 PPT 主链；观察测试中不需要人工解释下一步。

## Batch 5（P1）：PCM 文档类能力真实 E2E 与覆盖矩阵

### 文件落点

- `ops/acceptance/pcm-ios-coverage.yaml`
- `tests/e2e/test_word_workflow.py`
- `tests/e2e/test_research_report_workflow.py`
- `tests/e2e/test_academic_paper_workflow.py`
- `docs/product-capability-coverage.json`
- `docs/product-capability-manual.md`

### 三条真实 E2E

1. `document.word`：生成多页 Word，编辑两处内容，重新下载并验证结构和哈希。
2. `report.research`：使用至少三个可访问且互相独立的来源，逐条核对引用可追溯性，完成一次修改回路。
3. `paper.academic`：形成摘要、正文、参考文献和引用对应关系；未核实来源不得生成伪引用。

### 覆盖矩阵

逐项映射：

`iOS 用户功能 → capability → event → renderer → handler → consumer → policy → 测试 → 生产回执`

未覆盖项明确标注 `absent` 或 `unverified`，不得用能力总数代替覆盖结论。

### 扩展规则

- 新能力通过 Registry、Schema、Event、Renderer、Consumer、Policy 和测试受控注册。
- 不允许 Hermes 或客户端在运行时生成未经注册的未知协议。

## Batch 6（P2）：后端瘦身与职责拆分

仅在 Batch 1–5 行为验收通过后开始。

### 拆分目标

- `backend/api/quantum_workspace.py`：路由、状态机、session mapping 分离。
- `scripts/hermes_bridge.py`：presentation prompt、document prompt、结构验证和 transport 分离。
- `backend/api/workflows.py`：API DTO、review、scope、artifact projection 分离。

### 原则

- 先提取纯函数和稳定接口，再移动状态机。
- 不复制旧逻辑形成两套真源。
- 每次拆分保持 PCM Registry 与 Hermes Runtime 边界不变。
- 每个重构提交只改变结构，不同时改变产品输出。

### 验收

- 行为 golden tests 与拆分前一致。
- 无循环依赖、无双状态机、无重复 Prompt 真源。
- 目标回归、生产验收和 rollback 演练通过。

## 三、发布策略

### 发布批次

1. **R1：P0 后端兼容能力**
   - source trace、素材服务、统一 review API、generation fence 服务端支持。
   - 新字段保持向后兼容；旧客户端不崩溃。
2. **R2：iOS 新构建**
   - 统一编辑组件、自动跳转、权威 activity 投影、Agent 描述和三步主链。
   - 上传 TestFlight 后回读构建号；安装到真机，不能复用旧 Archive 或旧构建号。
3. **R3：模板与 PCM 正式启用**
   - 功能开关先对验收账号开放，通过后再扩大范围。
4. **R4：架构瘦身**
   - 独立发布，不与 R1–R3 混合。

### 每批固定流水线

1. 本地失败测试转绿。
2. Python 目标回归、iOS 单元测试、UI 测试和真实 artifact 检查。
3. clean-room staging/production E2E，不复用旧 workflow。
4. 提交并推送 `main`。
5. 核对本地 `HEAD == origin/main`。
6. 以精确 SHA 部署服务器并回读 API/workflow/planning/evaluation revision。
7. iOS 使用新构建号 Archive、上传 TestFlight、回读 ASC 状态、真机安装。
8. 回读 artifact 哈希、来源 manifest、session provenance 和版本号。
9. 删除临时凭据和测试环境注入文件。
10. 失败立即回滚到上一已验证 SHA；不得用局部通过覆盖失败项。

## 四、最终验收包

最终交付不是测试日志，而是以下完整验收包：

- 用户原文、事实清单、批准大纲、逐页 trace matrix。
- 新版 PPTX、PDF、全页 montage、素材来源与许可清单。
- PPTX 可编辑对象、媒体对象、地图和 SVG 结构检查报告。
- 统一编辑组件录屏/截图及 CAS 冲突回执。
- 双账号、双会话、并发、退出、冷启动、迟到响应生产矩阵。
- Word、研究报告、论文三个最终文件及来源/引用/修改回执。
- iOS capability 覆盖矩阵。
- 本地、GitHub、服务器 revision 和 TestFlight 构建号对照。
- 回滚 SHA 与回滚演练结果。

> [!success] 完成定义
> 只有上述门禁全部通过，并把基于用户原文生成的新 PPTX/PDF 发给用户人工确认后，才能宣布完成。自动化测试通过、生产 execution 完成或 PPTX 可打开，均不能单独代表产品完成。
