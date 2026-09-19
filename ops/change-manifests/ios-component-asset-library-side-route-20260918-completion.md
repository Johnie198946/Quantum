# Completion Manifest

- task_id: `ios-component-asset-library-side-route-20260918`
- 目标: 体检 V3–V5 组件素材需求，生成并接入书籍/日记/头像/内容图标/旅行图片，使用现有 DTO 与 API 建立可验收旁路，并将路线替换为 MapKit。
- 当前状态: `TESTED`

## 变更文件

- `docs/ios-component-asset-audit-20260918.md`
- `docs/ios-component-assets/**`
- `ios/AIPlatformApp/Assets.xcassets/{book_cover_*,journal_cover_*,avatar_youth_*,content_icon_*}.imageset/**`
- `ios/AIPlatformApp/Assets.xcassets/travel_kyoto_{camera,street,bridge}.imageset/**`
- `ios/AIPlatformApp/AIPlatformApp.swift`
- `ios/AIPlatformApp/DesignSystem/Theme.swift`
- `ios/AIPlatformApp/Views/Chat/Components/ChatMessageStreamView.swift`
- `ios/AIPlatformApp/Views/Knowledge/KnowledgeView.swift`
- `ios/AIPlatformApp/Views/Settings/ProfileEditSheet.swift`
- `ios/AIPlatformApp/Views/Settings/SettingsView.swift`
- `ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`

说明：当前 worktree 在本任务开始前已包含同一 V3–V5 前端升级任务的未提交改动；本任务未清理、覆盖或提交其他改动。

## 开工前 Git 盘点

- status: 分支已存在多项同一前端升级任务的 tracked/untracked 改动；本任务在其上增量开发。
- branch: `codex/ios-v3-v5-style-sandbox-20260917`
- HEAD: `58d212f18ed1edd71d0a95d18b12fc0b820eb277`
- remote: `origin` 为本地 Quantum-2.0；`source` 为 `https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/Users/dengzhaoyu/Documents/AI Lab/.worktrees/quantum-ios-style-sandbox-20260917`

## 复用与新增边界

- 复用: `KnowledgeBookDTO.coverTheme/coverVariant/coverVersion`、`KnowledgeNote.tags/title`、`UserProfile.avatarUrl`、`WorkflowArtifactDTO.metadata.renderType`、`WorkflowArtifactContentDTO.content`、现有 `APIClient` 与 endpoint。
- 新增: 本地内容素材映射、统一书封/头像组件、`travel_plan_v1` 解码与 MapKit 地点序列路线。
- 未新增: service、repository、网络层、endpoint、后端数据模型或生产迁移脚本。
- 旁路保护: `-assetLibraryPreview` 下资料编辑不会 PATCH `/api/v1/me`。

## 测试与校验

- `git diff --check`: 通过。
- 18 个新增 asset family 的 `Contents.json` 经 `plutil -lint`: 通过。
- 关键派生尺寸经 `sips`: 书封 378×537、日记 360×264、头像 222×222、内容图标 204×204、Hero 1200×900、地点图 720×372。
- Xcode Debug simulator build: 通过。
- `testComponentAssetLibraryUsesExistingBookAndNoteMetadata`: 通过。
- `testTravelPlanDocumentDecodesSideRouteArtifactContent`: 通过。
- 模拟器功能检查: `Quantum-Style-Sandbox-20260917` 安装成功；聊天入口内容图标、知识页日记/书封/头像、个人页头像、旅行 Hero 与 MapKit 路线均完成截图检查。
- 当前模拟器启动参数: `-autoLogin -knowledgeHomePreview -assetLibraryPreview`，已停留在知识页。

## 交付状态

- status: `TESTED`
- commit SHA: 未授权/未执行；本地 HEAD 仍为 `58d212f18ed1edd71d0a95d18b12fc0b820eb277`
- GitHub remote/ref/SHA: 未授权/未执行；未运行 push，`remote_sha` 不适用
- server_before: 不适用；未授权部署
- server_after: 不适用；未授权部署
- health_check: 不适用；未部署
- functional_check: 本地隔离模拟器通过，正式后端迁移未执行
- rollback_point: Git HEAD `58d212f18ed1edd71d0a95d18b12fc0b820eb277`；本任务未提交，二进制旧旅行图保存在 `docs/ios-component-assets/legacy/`

## 风险与未完成项

- MapKit 当前连接真实坐标形成地点顺序线，不是逐路段道路导航；确认需要导航级线路后再接 `MKDirections`。
- 正式后端尚未允许 `avatar_url` 写入素材 key，也未要求旅行工作流输出 `travel_plan_v1`；需用户验收后迁移。
- 源母版约 43 MB，适合设计归档；正式合并前可按仓库资产策略决定是否改放对象存储，App 派生资产约 8.9 MB。
