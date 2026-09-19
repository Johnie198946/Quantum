# Quantum iOS 组件素材库

本目录保存本次由 ImageGen 原创生成的母版；App 内派生文件位于 `ios/AIPlatformApp/Assets.xcassets`。素材仅承担内容表达，返回、搜索、编辑、状态等交互图标继续使用 SF Symbols。

## 组件与派生规格

| 组件 | Asset 名称 | App 派生格式 | 显示尺寸 |
| --- | --- | --- | --- |
| 书籍封面 | `book_cover_{literature,history,growth,science,travel}` | PNG 1x/2x/3x | 126 × 179 pt |
| 日记封面 | `journal_cover_{reading,ideas,travel}` | PNG 1x/2x/3x | 120 × 88 pt |
| 用户头像 | `avatar_youth_{01...04}` | PNG 1x/2x/3x | 最大 74 × 74 pt |
| 内容图标 | `content_icon_{learning,reading,inspiration,life,research,travel}` | 透明 PNG 1x/2x/3x | 最大 68 × 68 pt |
| 旅行主图 | `travel_kyoto_camera` | JPEG，1200 × 900 | 393 × 300 pt |
| 旅行地点图 | `travel_kyoto_{street,bridge}` | JPEG，720 × 372 | 240 × 124 pt |
| 路线 | `TravelRouteMap` | MapKit 矢量路线 | 自适应 |

## 使用入口

- `ContentAssetLibrary`：按现有 `cover_theme`、标题、标签与意图选择素材。
- `IllustratedBookCover`：书籍封面统一组件。
- `UserAvatarView`：兼容素材 key、现有 SF Symbol 值和未来 HTTP(S) 头像 URL。
- `TravelPlanDocument`：复用现有 workflow artifact `content`，以 `metadata.render_type = travel_plan_v1` 标识结构化旅行结果。

## 旁路约束

- `-assetLibraryPreview` 下编辑头像只更新本地 `AppState`，不会 PATCH `/api/v1/me`。
- 后端无需新增接口；确认后只需允许 `avatar_url` 保存素材 key，并让旅行工作流按 `travel_plan_v1` 输出既定 JSON。
- `legacy/` 保存被替换的低清旅行素材，方便对照与回滚。

## 生成方向

配色取自附件中的浅天蓝、鼠尾草绿、蜜桃橙与淡紫；书籍/日记/内容图标采用清新纸张拼贴和轻水粉质感，头像采用自然光编辑摄影，旅行图采用真实清透的京都纪实摄影。所有生成提示均要求无文字、无 Logo、无水印和无 UI 外框。
