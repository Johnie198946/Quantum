# 阅读页视觉重构

task_id: reading-refresh-20260927
status: COMMITTED
branch: codex/knowledge-ui-refresh-20260927
worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/knowledge-ui-refresh-20260927
head/local_commit: d38170ce6a0c25f325245c03f66f7563f0bee21a（UI实现提交）
remote_sha: 已授权联合发布；本任务尚未推送，统一发版任务负责主线合并与远端核验
server_before: 不适用，本地iOS展示层
server_after: 未部署
health_check: 不适用
functional_check: 3项ReadingDesign UI测试通过；2项既有书架UI测试通过；KnowledgeNoteStoreTests通过
rollback_point: 独立任务分支基线f8c7d064，原main及用户未提交文件未编辑
manifest: ops/change-manifests/reading-refresh-20260927-completion.md
remaining_risks: 离线预览使用通用封面，未进行登录账号真实封面验收；未声称像素级1:1；已本地提交，联合推送/TestFlight待执行

目标：按批准的四屏设计重构SwiftUI展示层，拆分组件/图标/装饰，保留原功能，系统刊物默认折叠。

开工盘点见 `ops/acceptance/reading-refresh-20260927/inventory.json`（status/branch/HEAD/remote/worktree）。
规范源目录 `/Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0` 存在其他任务未提交改动，未覆盖/暂存/提交。
会话用户明确要求一任务一分支/Worktree，优先于仓库文件的main-only规则；本任务采用规范源仓库的最新origin/main作为基线。桌面managed worktree工具只能作用于当前AI Lab仓库，无法指定Quantum源仓库，因此对目标仓库使用git worktree add，未创建历史副本。

组件、素材、图标和保真边界：`docs/design/reading-refresh/COMPONENTS.md`。

新增：纯展示组件ReadingComponents.swift、三张透明插画、DEBUG预览与UI测试、文档。
复用：KnowledgeNoteStore、APIClient、SubscriptionCenterView原订阅/书单/阅读器状态、SF Symbols、原生Toggle与DisclosureGroup。
无新增包依赖、无后端改动。

## 本次书架纠偏

- 页头身份行44→28pt，书架段落间距20→12pt，在读标题到卡片间距12→4pt。
- 在读卡片326pt宽、封面100pt宽；主题封面104×156pt，标题最多两行；大字号允许扩展。
- 系统刊物默认折叠，复用DisclosureGroup状态，向下/向上箭头符合批准图。
- 保留真实书籍封面加载和数据，不将设计稿内容硬编码成生产书目。

## 校验

- xcodegen生成成功，Debug模拟器构建通过；git diff --check通过。
- 独立iPhone 17 Pro / iOS 26.1模拟器：C284B362-5DB0-498E-A26C-BF0A128D566C。
- ReadingDesignUITests：3/3通过，覆盖笔记两列/搜索/置顶/删除确认、书架折叠/选书/阅读返回/草稿保留、最大辅助字号与横屏。
- 既有ProductionBookshelfUITests中的testBookshelfEmptyScopesAndRealListEditor、testBookListReadingPreservesUnsavedDraft通过。
- KnowledgeNoteStoreTests：全部通过。具体用例及数量见ops/acceptance/reading-refresh-20260927/validation.txt。
- 真实截图01–06在同目录，已人工查看笔记、书架首页、书架下滑、书单编辑及大字号/横屏截图。
- 原始结果：/private/tmp/reading-refresh-tests-4.xcresult、/private/tmp/reading-refresh-unit.xcresult；此前两项既有回归在/private/tmp/reading-refresh-tests-3.xcresult。

## 变更文件

- ios/AIPlatformApp/Views/Knowledge/KnowledgeView.swift
- ios/AIPlatformApp/Views/Knowledge/ReadingComponents.swift
- ios/AIPlatformApp/Views/Settings/SettingsView.swift
- ios/AIPlatformApp/Views/MainTabView.swift
- ios/AIPlatformApp/DesignSystem/Theme.swift
- ios/AIPlatformApp/Assets.xcassets/reading_{notes,reading,growth}.imageset/*
- ios/AIPlatformAppUITests/ReadingDesignUITests.swift
- ios/AIPlatformAppUITests/ProductionBookshelfUITests.swift（更新Tab控件定位）
- ios/AIPlatformApp.xcodeproj/project.pbxproj（登记新增Swift文件）
- docs/design/reading-refresh/*、ops/acceptance/reading-refresh-20260927/*、本manifest。

## 未执行和回滚

未获push/部署授权，因此未执行git ls-remote交付核验、服务器版本/健康检查；不涉及服务端变更。
未生成commit；保留独立worktree便于审阅。回滚时只撤销本清单的任务差异，禁止覆盖源main中其他任务的改动。
尚未做登录真实书库、小屏iPhone、iPad和Release构建验收；当前测试范围不得解释为全设备像素级复刻完成。

## 在读卡片二次纠偏

沿用同一任务分支和worktree，HEAD仍为f8c7d064，现有任务差异保留，未操作其他worktree。origin/main跟踪状态已落后3个提交；本次未混入其他变更。
问题证据：IllustratedBookCover以width < 100区分标题字号；前次100pt封面触发15pt标题，明显重于原稿。
改为96×160pt封面，正文callout semibold、8pt段距、较小胶囊按钮、16pt装饰书签，并补充浅薄荷椭圆衬底。全部复用recentBookCard原有数据与点击行为。
复验：Debug构建与书架UI回归1/1通过，/private/tmp/reading-card-tests.xcresult；git diff --check通过。已查看实际截图ops/acceptance/reading-refresh-20260927/07-reading-card-refined.png，封面标题和右侧文案均可读，操作沿用原入口。

## 首页背景统一（用户追加范围）

沿用本任务worktree；盘点：分支codex/knowledge-ui-refresh-20260927，HEAD f8c7d064，origin/main跟踪落后3提交，任务未提交差异保留。remote和worktree与前述一致，未混入其他任务。
新增修改文件：ios/AIPlatformApp/Views/Chat/ChatView.swift。
已查看独立模拟器首页：原QuantumMistBackground整页照片与卡片照片重叠。只在空会话首页替换为纸白底、薄荷/浅紫边缘椭圆，不改共享背景、卡片内容和消息页。装饰不响应点击，对辅助功能隐藏；无新图片、无新依赖。
校验：Debug模拟器构建成功（/private/tmp/home-background-build.log），git diff --check通过。独立iPhone 17 Pro模拟器安装运行成功，人工查看08-home-before.png与09-home-background.png，背景无照片重叠，首页内容和按钮布局保持原样。纯背景变更未新增测试；未验证登录后真实进度，截图中的进度读取失败在修改前已存在。

## 联合TestFlight交付准备

用户最新要求“要推送、部署吗？testflight合并一起提交”，授权将本任务整合提交并纳入TestFlight。已发现清理任务统一协调旅行/图片联合发布；本任务仅iOS展示层，无独立服务器部署。先生成本任务独立提交，待联合主线整合后重验。当前origin/main跟踪167fba5c，包含图片处理，两个重叠文件为ChatView与工程/测试登记，必须保留两侧能力。
本次检查：git diff --check通过；既有Debug编译与阅读回归见上。当前提交不包含规范源目录的未提交图片/工作流文件。TestFlight尚未上传，不宣称已发布。

交接确认：联合发版线程01a0de14-6e79-7cc2-9765-5313560c4dcb已接收d38170ce并开始核对纳入，明确保留图片上传状态、Mantis依赖和统一版本号。本任务不重复上传，不直接改共享main。最终推送SHA、Apple回执与测试组可用性以联合发版记录为准，尚未完成时不得标记PUSHED或VERIFIED。
