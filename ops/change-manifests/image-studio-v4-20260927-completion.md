# image-studio-v4-20260927

- task_id: image-studio-v4-20260927
- 目标：实现确认的七屏手动图片工作台、共享原生渲染、真实保存与批量、PCM/Chat 同合同调用。
- 当前状态：TESTED（本地开发和约定验收通过；未提交、push 或部署）。
- 用户授权：明确允许从最新 main 建独立 Worktree；这是对仓库 main-only 规则的本任务例外。2026-09-28 用户已明确授权推送、部署、上传 TestFlight；交付结果以实际回执为准。

## 开工盘点

原规范目录 `/Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0`：main，HEAD `21250c7b8a5290abcf649b9279bbd91b9af1db88`，落后 origin/main 21 个提交；49 个 tracked 文件存在其他任务修改，另有 untracked。未覆盖、暂存或带入这些修改。

本任务从 fetch 后的 origin/main `ae11b9bd8e30c89269ea8c59da7cf239fac86920` 创建：

- branch: `codex/image-studio-v4-20260927`
- worktree: `/Users/dengzhaoyu/Desktop/TepVis/.worktrees/image-studio-v4-20260927`
- 初始 status: `## codex/image-studio-v4-20260927...origin/main`，无修改。
- head/local_commit: `ae11b9bd8e30c89269ea8c59da7cf239fac86920`（基线；本任务未提交）
- origin fetch/push: `https://github.com/Johnie198946/Quantum.git`
- source fetch/push: `https://github.com/Johnie198946/ai-lab-platform.git`
- worktree list 包含规范 main、本任务，以及其他独立任务：jev-pcm-routing、knowledge-ui-refresh、quantum-confirmation-fix、travel-notes、image-direct-processing；均未修改。

## 架构命中与改动

判定：旧版已实现 Mantis 裁剪、Vision 抠图、设备图片任务和私有上传；文字图层、调色修复、导出面板与批量仅部分/尚未实现。

复用 `WorkflowCreateSheet → ImageWorkbench → ImageEditSupport`；Chat `NativeImageProcessAction` 使用同一渲染函数与 `ImageEditDTO.studio`。复用 generated artifacts owner 存储和 PCM dispatcher；新增 `media.save_edit` 只负责验证/记录已在设备实际渲染的结果。

主要文件：

- `ios/AIPlatformApp/Views/ImageStudio/*.swift`：配方、同一渲染器、编辑状态、画布和七屏面板。
- `ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift`：处理图像直接进入手动编辑入口。
- `ios/AIPlatformApp/Views/Chat/Cards/ImageCard.swift`、`NativeClientActionHost.swift`、`Networking/APIClient.swift`：共享入口、私有图层素材下载、DTO。
- `ios/project.yml`、生成工程/锁文件/Info.plist、`OpenCV-SPM-LICENSE.txt`：固定 OpenCV 4.13.0、相册添加权限与许可。
- `backend/services/image_processing.py`：配方范围、素材归属、尺寸格式、来源哈希校验和保存。
- `backend/services/generated_artifacts.py`：在现有存储增加可选幂等身份与原子目录发布，不另建存储。
- `backend/capability_handlers.py`、`capability_catalog.py`、PCM 合同与生成文档：媒体合同扩展、保存注册、错误收据。
- `tests/test_image_studio.py`、既有图片测试、iOS 像素/界面测试、`tests/fixtures/image_studio_server.py` 隔离验收服务。
- `scripts/hermes_bridge_runtime/agent_execution.py`、`knowledge.py`、`workflow_artifacts.py`：Chat/既有工作流读取完整 PCM 图片合同。
- `ios/AIPlatformApp/Fonts/`：两款 OFL 中文字体、原始许可证和来源/hash记录；避免平台缺字体时预设无效果。
- `docs/design/image-studio-v4/`：确认图、每个图标和组件的拆解清单。

## 验证（2026-09-28）

- 后端命令：`python3 -m pytest tests/test_generated_artifact_capabilities.py tests/test_image_studio.py tests/test_image_processing.py tests/test_ios_capability_matrix.py tests/test_capability_gateway.py tests/test_pcm_semantic_capabilities.py -q`：**54 passed**，6 个既有弃用警告。
- `python3 scripts/generate_product_capability_manual.py --check`、`python3 scripts/generate_ios_capability_matrix.py --check`、`git diff --check` 均通过。
- Xcode `build-for-testing`：**TEST BUILD SUCCEEDED**。Mantis 3.1.0 / OpenCV 4.13.0 锁定依赖解析成功；OpenCV 二进制 SHA256 已验证为 `41fc3bf0f2af1660e24694a3e05d5c56e5869a133cea7084a7e262d54dd5b675`。
- iPhone 17 Pro / iOS 26.1 专用模拟器 `801B82BB-4B7F-449D-82C0-01DF69E93ED6`：6 项原生测试 + 1 项七屏 UI 流程，**0 failures，TEST EXECUTE SUCCEEDED**。
- 原生验收覆盖真实像素、裁剪映射、输出尺寸、透明 PNG、白底 JPEG、OpenCV 修复、实际中文字体、私有贴图参数、撤销重做和草稿编码。
- 完整按钮验收：文字/图层/滤镜/修复 → 保存副本 → 私有作品文件 → 相册成功 → 批量 5 张完成。使用隔离本地服务的真实 documents/capabilities 路由，不伪造保存成功回执。
- PCM/Chat：现有桥接路径的 `media.process` 高级配方与 `media.save_edit` 调用通过；新动作使用 `image_studio_v1`，不让旧客户端静默忽略配方。
- 首轮验收发现修复 alpha 合成、系统字体回退和画布无障碍标签覆盖问题，均已修正并重跑通过。截图检查后修正固定保存按钮、工具取消/完成和滤镜缩略条。
- 结果包：`/private/tmp/image-studio-v4-acceptance.xcresult`；编译日志：`/private/tmp/image-studio-build.log`。
- 持久化测试日志：`docs/design/image-studio-v4/backend-test.txt`、`native-test.txt`；七屏原始截图：`docs/design/image-studio-v4/screenshots/`。
- 可复现说明：`docs/design/image-studio-v4/acceptance.md`。

## 交付与回滚

- commit SHA: 未执行；保留本地修改。
- remote/ref/SHA、git ls-remote: 未授权 push，未执行交付核对；基线取自 fetch 的 origin/main，不作为本任务已推送证据。
- server_before: 不适用，未授权部署。
- server_after: 不适用，未部署。
- health_check: 生产不适用；本地 `curl http://127.0.0.1:8897/health` 返回 `{"status":"ok","fixture":"image-studio-local"}`。
- functional_check: 后端 54 项 + iOS 6 项原生/1 项 UI 流程通过，实际单图及批量保存/系统相册写入成功。
- rollback_point: 本任务独立 Worktree 基线 `ae11b9bd8e30c89269ea8c59da7cf239fac86920`；无远端变更需要回滚。
- 回滚方式：只撤回本任务文件的修改；不操作规范目录或其他 worktree。
- remaining_risks: 真机 Vision 识别效果、低内存设备性能与发布包体积未量测；尚无生产部署/验收。实际截图使用现有旅行素材而非原型校园人物，保留照片完整比例和系统控件，不声称像素级 1:1。上限为单图 12MB/24MP、批量20张/60MB，详见验收说明。

- 本地隔离验收服务在测试完成后停止；可用验收文档中的命令重新启动。

## 变更文件清单

```text
backend/capability_handlers.py
backend/contracts/product-capabilities/bindings.yaml
backend/contracts/product-capabilities/generated_artifacts.yaml
backend/contracts/product-capabilities/ios-scope.yaml
backend/services/capability_catalog.py
backend/services/client_actions.py
backend/services/generated_artifacts.py
backend/services/image_processing.py
docs/design/image-studio-v4/acceptance.md
docs/design/image-studio-v4/approved-editing.png
docs/design/image-studio-v4/approved-export-batch.png
docs/design/image-studio-v4/backend-test.txt
docs/design/image-studio-v4/component-inventory.md
docs/design/image-studio-v4/native-test.txt
docs/design/image-studio-v4/screenshots/01-editor.png
docs/design/image-studio-v4/screenshots/02-text.png
docs/design/image-studio-v4/screenshots/03-layers.png
docs/design/image-studio-v4/screenshots/04-color.png
docs/design/image-studio-v4/screenshots/05-repair.png
docs/design/image-studio-v4/screenshots/06-save.png
docs/design/image-studio-v4/screenshots/07-batch.png
docs/product-capability-coverage.json
docs/product-capability-manual.md
ios/AIPlatformApp.xcodeproj/project.pbxproj
ios/AIPlatformApp.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved
ios/AIPlatformApp/AIPlatformApp.swift
ios/AIPlatformApp/Fonts/MaShanZheng-Regular.ttf
ios/AIPlatformApp/Fonts/README.md
ios/AIPlatformApp/Fonts/ZCOOLXiaoWei-Regular.ttf
ios/AIPlatformApp/Fonts/mashanzheng-OFL.txt
ios/AIPlatformApp/Fonts/zcoolxiaowei-OFL.txt
ios/AIPlatformApp/Info.plist
ios/AIPlatformApp/Networking/APIClient.swift
ios/AIPlatformApp/OpenCV-SPM-LICENSE.txt
ios/AIPlatformApp/Views/Chat/Cards/ImageCard.swift
ios/AIPlatformApp/Views/Chat/NativeClientActionHost.swift
ios/AIPlatformApp/Views/ImageStudio/ImageStudioPanels.swift
ios/AIPlatformApp/Views/ImageStudio/ImageStudioRecipe.swift
ios/AIPlatformApp/Views/ImageStudio/ImageStudioRenderer.swift
ios/AIPlatformApp/Views/ImageStudio/ImageStudioSession.swift
ios/AIPlatformApp/Views/ImageStudio/ImageWorkbench.swift
ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift
ios/AIPlatformAppTests/ImageStudioTests.swift
ios/AIPlatformAppUITests/ImageStudioUITests.swift
ios/project.yml
ops/acceptance/ios-capability-matrix.json
ops/change-manifests/image-studio-v4-20260927-completion.md
scripts/hermes_bridge_runtime/agent_execution.py
scripts/hermes_bridge_runtime/knowledge.py
scripts/hermes_bridge_runtime/workflow_artifacts.py
tests/fixtures/image_studio_server.py
tests/test_image_processing.py
tests/test_image_studio.py
```

## iOS 打包与执行位置复核（2026-09-28）

用户强调全部图片编辑在 iOS 执行。本次只核查和补充打包验证，不变更处理架构。

- Mantis 3.1.0：Swift Package，声明 iOS 15 起；项目 iOS 17，兼容，随 App 编译链接。
- OpenCV 4.13.0：XCFramework 包含独立 `ios-arm64` 真机 slice 和模拟器 slice；通过 SPM 链接本地 Telea 修复，无 Python 或服务端修图进程。
- Vision / Core Image / UIKit / ImageIO：链接 iOS 系统框架，分别承担主体提取、调色滤镜、文字图层与输出编码。
- 站酷小薇 / 马善政：两款 TTF 及 OFL 许可证已核实进入 Release App，UIAppFonts 配置完整。
- 手动与 Chat 均调用 `ImageEditSupport.renderStudio`；Chat 经 `image_studio_v1` 下发到设备，设备输出完成后再上传。
- 后端仍会解码图片做格式、尺寸、透明度校验，并存储原始上传字节；不执行编辑配方、不生成编辑后的像素。当前保存与贴图登记依赖联网，不等于完整离线工作流。
- 新增验证命令：`xcodebuild build -project ios/AIPlatformApp.xcodeproj -scheme AIPlatformApp -configuration Release -destination 'generic/platform=iOS' -derivedDataPath /private/tmp/image-studio-v4-device-build -clonedSourcePackagesDirPath /private/tmp/image-studio-v4-packages -disableAutomaticPackageResolution CODE_SIGNING_ALLOWED=NO`。
- 结果：**BUILD SUCCEEDED**；App 可执行文件为 **Mach-O 64-bit executable arm64**，MinimumOSVersion **17.0**。原始日志 `/private/tmp/image-studio-device-build.log`。
- 产物：`/private/tmp/image-studio-v4-device-build/Build/Products/Release-iphoneos/AIPlatformApp.app`。
- 此为无签名真机目标构建，未执行签名 IPA 导出、真机安装或 App Store 提交。状态仍为 TESTED，branch/worktree/HEAD/remote/server/rollback 与上述记录相同。

## Build 75 发布执行（进行中）

- 本任务独立 worktree 开始 HEAD `ae11b9bd8e30c89269ea8c59da7cf239fac86920`；从当时最新 `origin/main` 快进至 `457abcd4284f5ab0910df1d138475894b963a782`，未碰规范 main 的其他任务改动。
- 版本由 1.0.3(74) 调整为 1.0.3(75)，仅改 `ios/project.yml` 与生成工程中的两个构建号。
- 同步后后端相关测试加新主线出版测试：102 passed，6 个既有弃用警告；PCM manual/matrix `--check`、`git diff --check` 通过。
- 同步后 `origin/main` 又增加 JEV/PCM 路由提交 `ecf5fd4881a157c6943ce7915db641f6d4dd58cc`；涉及 capability_catalog、Hermes/knowledge 和 PCM 合同，需要集成并复测，禁止覆盖推送。
- TestFlight 归档已完成并签名校验通过；此时尚未上传。
- 生产服务器：对 `root@120.79.216.160` 的一次只读查询使用 `ai_lab_deploy_ed25519_20260912b` 失败（publickey）；自动审批明确拒绝随后轮询多个本地密钥，理由是未经授权的凭据探测，不进行替代重试。部署所需的回滚点与服务器当前SHA尚未取得。
- 当前状态仍 TESTED；commit、remote_sha、server_after、TestFlight 回执均未产生。

## Build 75 候选复核（合并后）

- 本任务源码提交 `1d344f88`；合并最新 JEV/PCM 路由 `ecf5fd4881a157c6943ce7915db641f6d4dd58cc` 已自动合并，三个交叉文件检查保留了媒体 PCM 注册与请求范围内的路由投影。
- 联合后端/PCM/JEV/出版测试：168 passed、6 个既有弃用警告；`media.save_edit` 与 `media.process` 仍在 PCM 中。
- Build 75 归档：`/private/tmp/Quantumn-1.0.3-75-image-studio.xcarchive`，`ARCHIVE SUCCEEDED`；`codesign --verify --deep --strict` 通过；Info.plist 为 1.0.3(75)、最低 iOS 17。JEV 合并不改 iOS 源码，归档对应本任务 iOS Build75 文件。
- 当前尚未 push/deploy/upload；接下来只按经核验的远端 main 快进交付，不使用 force push。
