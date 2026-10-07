# iOS 旅行页面开发完成记录

- task_id: ios-travel-pages-20261007
- status: VERIFIED（仅 iOS 客户端真机安装与旅行页面验收，不代表完整云端工作流或服务器发布）
- branch: codex/ios-travel-pages-20261007
- worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/ios-travel-pages-20261007
- head/local_commit: 功能源码提交 3c62aa01594b8ff624ac2cc29704d9c005a6deb7；最终证据提交仅含文档/图片，见 Git HEAD。
- remote_sha: 功能源码 3c62aa01594b8ff624ac2cc29704d9c005a6deb7，git ls-remote origin refs/heads/codex/ios-travel-pages-20261007 独立确认一致；最终证据提交补推三次被 GitHub Internal Server Error 拒绝，远端仍为已部署功能提交 3c62aa01；证据提交仅本地。
- server_before: 不适用（客户端任务）；device_before=1.0.3(75.1)。
- server_after: 不适用（无后端变更）；device_after=1.0.3(76)，安装后及测试后两次回读一致。
- health_check: 客户端签名核验通过、真机安装成功、测试后正常启动成功；服务器健康不适用。
- functional_check: 模拟器 7 项通过；iPhone 17 Pro/iOS 26.6 真机 4 项单元 + 1 项页面操作通过，实际截图已检查。
- rollback_point: Git 基线 fc1b2f88c4a4e0c1d0a393e2e58eb62b92626114；已有签名有效且注册此设备的 1.0.3(75) 归档可重装，完整路径与二进制 SHA 在下方回执。它不是原手机 75.1 的逐字节备份。
- manifest: ops/change-manifests/ios-travel-pages-20261007-completion.md

## 目标、复用与架构命中

把已确认的全屏旅行小世界原型接入实际 iOS 产品。旅行创建、攻略生成、笔记保存、旅行中的修订和进度记录已经有主路径；本次扩展其共享成果展示，不建立第二套工作流或笔记状态。

复用 `TravelPlanResultView`（工作流成果与保存后的笔记共用）、`TravelPlanDocument`、`TravelRouteStop` 和 `orderedStops`；保留现有动作、版本、修订、来源及个人记录处理。新 `TravelJourneyView` 仅负责全屏 UI、WKWebView 生命周期和原生 MKDirections 桥接。既有离线 SceneKit 球体移动到同一文件供错误降级复用。

既有抽象没有网页 3D 地球的承载容器，因此增加一个 WKWebView 展示组件，保持数据来自既有文档，不增加服务层、持久化层或后端接口。

## 开工盘点与规则

完整核验记录见 `ios-travel-pages-20261007-inventory.md`。修改前 task worktree 无修改，分支为 codex/ios-travel-pages-20261007，HEAD 为上述基线。

origin: https://github.com/Johnie198946/Quantum.git；source: https://github.com/Johnie198946/ai-lab-platform.git。

原主工作区 `/Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0` 是 main，HEAD 21250c7b8a5290abcf649b9279bbd91b9af1db88，落后 origin/main 29 个提交，并存在其他任务修改。仅只读核对，未混入、覆盖、暂存、清理或提交其修改。

仓库规则要求 main-only，与用户本次明确给出的“一任务一分支、一 Worktree”冲突，按用户明确指令使用隔离工作区。执行了读取最新 origin/main 的 fetch，未修改原 main。当前聊天的托管 Worktree 工具绑定 AI Lab 仓库，不支持指定 Quantum 仓库，因此以 git worktree 为目标产品创建隔离目录。

未使用 git add .、共享 stash 或 reset --hard。本地开发阶段未提交、推送或部署；下方继续阶段在用户明确授权后执行。

## 变更文件

- ios/AIPlatformApp/Views/Knowledge/KnowledgeView.swift：统一现有笔记翻页入口；增加旅行小世界入口和 fullScreenCover；封面使用现有主题色；离线球体移出。
- ios/AIPlatformApp/Views/Knowledge/TravelJourneyView.swift：注入真实文档地点与路段、校验坐标、全屏容器、原生汽车/步行规划、关闭/后台暂停、加载错误/重试/离线降级。
- ios/AIPlatformApp/Resources/TravelJourney/journey.html、journey.js：原型视觉接入，安全区、按需弹层、国家/城市/区域/地点相机尺度、四种玩具交通模型、路线回放。
- ios/AIPlatformApp/AIPlatformApp.swift：DEBUG 专用独立验收入口，真实用户页面不注入样例行程。
- ios/AIPlatformApp.xcodeproj/project.pbxproj：XcodeGen 注册新资源、源码与测试。
- ios/AIPlatformAppTests/TravelJourneyTests.swift、ios/AIPlatformAppUITests/TravelJourneyUITests.swift：数据边界与实际模拟器操作验收。
- ops/acceptance/ios-travel-pages-20261007/：实际模拟器地图及交通弹层截图。
- 本 completion manifest 与 inventory。

## 验证

工具：Xcode 26.1.1；独立 iPhone 17 Pro / iOS 26.1 模拟器 QuantumTravel-20261007，UDID 45CEABA3-E4E9-47E5-9C93-2BC5B9858735。

编译：`xcodebuild -project ios/AIPlatformApp.xcodeproj -scheme AIPlatformApp -configuration Debug -destination 'generic/platform=iOS Simulator' -derivedDataPath /tmp/QuantumTravelDerived build CODE_SIGNING_ALLOWED=NO`，BUILD SUCCEEDED，日志 `/tmp/quantum-travel-build.log`。

最终验收：同工程 scheme，destination 为上述模拟器，运行 `TravelJourneyTests`、`TravelJourneyUITests`，以及已有 `WorkflowLifecycleDTOTests/testTravelPlanDocumentDecodesSideRouteArtifactContent`、`testTravelRoutesIncludeTransportEndpointsAndReturnLegs`。TEST SUCCEEDED，共 7 个测试无失败；日志 `/tmp/quantum-travel-tests-verified.log`，结果 `/tmp/QuantumTravelTests-Verified-20261007.xcresult`。

测试覆盖真实文档坐标、缺坐标断开路段、非法坐标剔除、往返顺序、脚本注入文本按数据处理、资源打包、原生全屏宽高、打开弹层、选择汽车后收起、播放暂停、关闭返回原笔记。

截图：`ops/acceptance/ios-travel-pages-20261007/fullscreen.png`、`transport-sheet.png`，为模拟器实拍。人工检查确认底图、完整路段、沿途汽车模型、主题色、按需展开面板及安全区显示。截图中的 Kyoto 行程只用于 DEBUG 测试入口。

验收中发现并修正：WebKit 弹层入口/切换控件无障碍类型不同于普通 Button；相机切换期间 isStyleLoaded 导致完整路线取景失效；瓦片恢复后仍显示误报提示。最终运行已包含这些修正。

`git diff --check` 通过。

## 外部来源与运行边界

沿用已调研的原型方案：MapLibre GL JS 6.11.2（BSD-3-Clause）、Three.js 0.169.0（MIT）、OpenFreeMap/OSM。固定 CDN 版本，保留运行时底图署名。前序选型证据来自已读取的本机 `designs/ios-travel/research.md`，不是本次新增猜测。

- https://github.com/maplibre/maplibre-gl-js/blob/v6.11.2/LICENSE.txt
- https://github.com/mrdoob/three.js/blob/r169/LICENSE
- https://maplibre.org/maplibre-gl-js/docs/examples/add-a-3d-model-to-globe-using-threejs/
- https://openfreemap.org/quick_start/

网络底图和 CDN 需要联网，原生网页使用非持久存储，不共享 App 登录凭据。MKDirections 只接受既有文档校验后的坐标和汽车/步行类型。个人笔记正文不会作为可执行脚本，地图不会加载笔记中的任意链接。

## remaining_risks / 未完成项

- 已推送隔离分支并完成真机安装，未合并 main、未部署服务器、未上传 TestFlight。
- 汽车/步行尝试 Apple Maps 规划，可用时替换路线；这次截图仍为示意连线，不能声称已经验证该地点的真实道路规划成功。飞机/列车始终为示意，并非真实航线或铁路。
- 使用当前文档经纬度；没有新增 Google Maps 坐标提取器，也没有使用 Google 卫星或摄影测量模型。
- 国家/城市/区域/地点是连续相机尺度展示，不是行政区识别与自动边界检索。
- 旅行控制中的交通模式是展示方式，不会擅自改写真实行程交通安排。
- 缺坐标显示待定位；零坐标使用原生空态，不补造地点。离线球体只有位置示意，不含道路/地形。
- 已在物理 iPhone 17 Pro/iOS 26.6 验收，iOS 17 未验收；真机 UI 使用 DEBUG 行程 fixture 进入实际共享成果视图，未重新执行真实云端研究/生成/修订全过程，相关后台主路径本次未修改。
- CDN/底图服务可用性与低端设备 WebGL 性能仍受环境影响；加载失败提供重试和既有离线视图。

## 2026-10-07 用户授权的推送与真机部署

用户明确要求“推送 部署 使用真机测试”，授权本任务 commit、GitHub 推送和 iPhone 安装验收。继续使用本任务隔离分支，不把规范 main 的其他修改带入。重新盘点 branch/HEAD/remote/worktrees，与前段记录一致；fetch 后 origin/main 仍为 fc1b2f88c4a4e0c1d0a393e2e58eb62b92626114。

部署范围为 iOS 客户端，后端无本次代码变更，因此不重启或部署服务器。已连接设备 iPhone 17 Pro（00008150-000C50980244401C / CoreDevice CFE79F35-1270-527D-8BD7-9AB60449B6DF），iOS 26.6。部署前 installed version=1.0.3(75.1)，证据 /tmp/travel-device-apps-before.json。当前准备 1.0.3(76) 签名包，尚未执行安装或声称真机测试通过。TestFlight 是否需要额外发布已向用户提出可选澄清。

### 已执行的最终真机部署回执

功能提交 3c62aa01594b8ff624ac2cc29704d9c005a6deb7 已 push 到 origin/codex/ios-travel-pages-20261007，ls-remote 完整 SHA 一致。未移动 main；仓库记录的其他任务脏工作区保持不动。

真机 build-for-testing 成功，/tmp/QuantumTravelDeviceDerived/Build/Products/Debug-iphoneos/AIPlatformApp.app；codesign --verify --deep --strict 通过。二进制 SHA256=4241546130c5c2a13a443d6cbb0b058b66f66db71d680d251a015ac77abd89fa，旅程 HTML/JS 打包资源与已推送源码哈希一致。

安装前已核验旧版 75 归档的签名与 development profile（包含该 UDID），二进制 SHA256=663ba14577fa62d4823a3e5405a385a21e37f29bd497a498760a5b1fe4254f67。归档位于 /Users/dengzhaoyu/Library/Developer/Xcode/Archives/2026-09-28/Quantumn-1.0.3-75-image-studio.xcarchive/Products/Applications/AIPlatformApp.app。此回滚包是 75，非手机原 75.1 的逐字节备份。无卸载、无清空 App 数据。

2026-10-07 23:06 安装成功，devicectl apps 回读 1.0.3(76)。真机测试 23:07 完成：TEST EXECUTE SUCCEEDED，4 单元 + 1 UI，共 5 项零失败；UI 包含全屏、交通弹层、汽车模式选择、播放/暂停、关闭并返回原笔记。结果 /tmp/QuantumTravelPhysical-20261007.xcresult，日志 /tmp/quantum-travel-physical-tests.log。

真机截图 ops/acceptance/ios-travel-pages-20261007/physical-fullscreen.png、physical-transport-sheet.png 已人工检查：整段路线与汽车模型可见，底图加载正常，弹层与主题显示一致。当前截图仍为点间示意，不能把汽车真实道路规划成功当作已验收。

23:07:56 测试后以无 DEBUG 参数正常启动 com.ailab.AIPlatformApp 成功，最终安装版本再次回读 76，证据 /tmp/travel-device-normal-launch.json、/tmp/travel-device-final-apps.json。脱敏综合回执 physical-device-verification.json 随本任务提交。

本轮按 iOS 真机安装交付；未额外上传 TestFlight。客户端改动无需重启后端，因此 server_before/server_after 均不适用。健康/功能核验仅指本次客户端页面，不宣称全流程云端验收或生产服务器已上线。

### GitHub 验收记录补推失败（23:10—23:12）

功能提交 3c62aa01594b8ff624ac2cc29704d9c005a6deb7 已成功推送并部署真机。证据提交 2164be6f891aeda4cd0c2ee328df2ea2919b7291 不含 iOS 源码变更；普通推送两次、HTTP/1.1 推送一次均返回 GitHub `remote rejected / Internal Server Error`。对应 request IDs：0E5F:11D892:14E070:1CA60B:6AC660DE、61D1:103791:148DFD:1C50D9:6AC6610F、0505:B130:147952:1C4B58:6AC6616B。每次 ls-remote 均确认远端仍是 3c62aa01594b8ff624ac2cc29704d9c005a6deb7。不是自动审批拒绝，未使用 force push 或更改其他分支。

remaining_risks 更新：真机功能版本核验完成；真机截图及验收文档的后置提交尚未同步 GitHub，保留本地待补推。不能声称本地最新 HEAD 已推送。main 未合并，TestFlight 未上传，后台真实生成/修订全流程未复验。
