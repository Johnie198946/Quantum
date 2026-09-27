# 图片处理工作流交付记录

task_id: image-workflow-20260927
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
head/local_commit: shared checkout 21250c7b；release parent d228c06d6865bdbca9329f264acfe4cf0e8fc5f7；提交SHA见后续发布证据
remote_sha: 图片功能未推送；共享 origin/main 已被其他任务推进，发布前必须协调同步并核验
server_before: 本任务尚未建立部署前快照
server_after: 本任务未部署
health_check: 未执行生产验收
functional_check: 干净整合版后端172/旅行35/Swift195通过；模拟器完整UI1通过；物理iPhone PNG/JPG集成各1通过；真机全UI点击未完成
rollback_point: 尚未部署，部署前必须建立
remaining_risks: 真机全UI点击和图库选择器未完成；生产验收待部署；TestFlight由协调任务唯一上传

## 最终架构与复用

用户已确认手机执行像素操作。复用 Chat、PCM、WorkflowDashboard、ClientActionInvocation 与回执、generated_artifacts 私有存储及下载。
- iOS 原生 Vision 提取主体，原生编码 PNG/JPG、按像素裁切；Mantis 3.1.0 提供交互裁切，MIT，固定 revision 0960be1feed2e62f62a5fddbb8d72b26008db881，许可证随 App 打包。
- 后端生成并冻结参数，派发现有设备任务，校验结果所有权、源哈希、格式、尺寸及透明度，原子确认回执和工作流结果。
- 后端新增 image_processing.py 集中图片边界校验和设备结果协调；不新增模型服务或状态库。原图不传桥接模型，服务器不执行分割/裁切/转码。
- 已移除本任务先前试验的 SAM/rembg/ONNX 依赖。早期服务器像素处理证据不计入最终端侧方案验收。
- 输出仅 PNG/JPG，输入静态 PNG/JPEG/WebP，HEIC 在 iOS 转 PNG；限制12MB/2400万像素。透明抠图不能输出 JPG。主体通过位置选择，默认中心；任意语义定位尚不保证。

## 开工盘点与改动边界

初始 main，HEAD b696d13bdcef18cc23b1707dc00501ca012ee224。origin=https://github.com/Johnie198946/Quantum.git，source=https://github.com/Johnie198946/ai-lab-platform.git。
原始 status/branch/HEAD/remote/worktree 证据：../acceptance/image-workflow-20260927/initial-*.txt。
用户允许后按实际仓库 main 规则执行；共享工作区含其他任务改动，不能整树暂存或覆盖。
2026-09-27 续验盘点：main，HEAD21250c7b，behind origin/main4，图片及其他任务未提交变更并存；另有 knowledge-ui-refresh/travel-notes worktree。
变更范围：backend 图片上传、PCM合同及gateway、client_actions、workflow规划/执行/产物；bridge 参数产物；iOS 图片工作台、附件、设备操作宿主、工作流页面、DTO及测试；生成文档/能力矩阵、验收记录。

## 已完成验证

- 后端图片/设备回执/PCM/workflow/产物等回归129 passed；bridge/事件投影/contract63 passed；状态补充5 passed。
- 最新 proposal/client_actions/图片回归41 passed；Swift ImageProposalContractTests 1 passed：图片参数保存恢复不丢失、旧缺参卡片不能确认。
- Ruff、生成合同检查曾通过；交付前需在最终差异再次检查。设备及模拟器 build-for-testing 通过。
- 真机 iPhone17Pro/iOS26.6：Vision 提取完整中央人物可见，证据 ../acceptance/image-workflow-20260927/native-vision-device.png；Mantis16:9选项可见，native-mantis-device.png。尚未证明完整流程导出字节。
- 真机真实上传→Chat生成16:9/JPG参数成功；旧UI持久化字段缺失导致显示PNG，自动审批拒绝点击。未绕过；已修复DTO并以单测验证，等待重新真机验收。
- 真机 XCUITest runner 初始化失败，非功能通过。已按约恢复 Build70，设备归笔记任务，等待新窗口。
- 模拟器前几次脚本因旧选择器、误触和误匹配原图导出失败；当前改为精确处理结果导出按钮，正在重跑。

## 授权与剩余工作

用户已授权：真机全链路验收完成后提交推送和部署；已授权与笔记/书架任务协调。未完成真机链路前不推送部署。
剩余：模拟器和真机完整 Chat→确认→参数→本机处理→保存→下载，核验结果尺寸/格式/哈希；共享diff审查、最终回归；协调部署窗口，建立回滚，push及ls-remote，部署相同SHA并健康/功能复验。
回滚：只撤回本任务明确差异，不覆盖其他任务改动；禁止 reset --hard。

## 最新验收进展

- 模拟器完整 Chat 上传→16:9/JPG提案确认→需求/方案确认→本机处理→上传回执→确认下载→导出分享面板通过，1 test/0 failures/84.663秒。证据 /tmp/quantum-image-simulator-live7.xcresult。
- 下载接口实际字节独立回读200，JPEG656×369，source_kind=ios_native，SHA256=aeb2a498666aae31434df04b9b43907bdf614fb78e44738eef4825eb0da21ec5；见 ../acceptance/image-workflow-20260927/native-simulator-jpeg.json。
- 最新核心回归41 passed/10测试配置警告，两个生成合同检查通过，git diff --check通过，最终Build71真机 build-for-testing成功。
- 真机完整链路仍待协调窗口，尚未推送部署；当前保持LOCAL_ONLY。
- 模拟器抠图链路到达本机执行，但 Vision 报 Could not create inference context；未计为通过，停止该轮测试。
- 真机窗口已交接，最新 Build71 安装成功；两次开发工具启动被 iOS Locked 拒绝，已请求用户物理解锁。等待期间不绕过锁屏、不改变生产账号或配额。
- 用户尚未解锁，已恢复1.0.3 Build70并以devicectl apps核验bundleVersion=70，证据/tmp/quantum-image-restored-apps-second.json；未改变账号或生产配额。镜像/真机窗口已交还笔记任务。继续验收前需重新协调窗口及用户解锁。

## 2026-09-27 解锁后的真机验收

- 用户明确回复已解锁；真机71成功启动，真实上传示例照片并调用Chat生成中心主体/透明PNG参数。重开后参数保留正确；一次确认因安全凭证不持久化而失效，未绕过该失效凭证。
- Xcode UI runner仍认证失败；镜像滚动不响应，未完成真机全UI点击链路。模拟器全UI链路通过，不能与真机hosted集成测试混称。
- 复用正式API与真实手机上传原图/模型参数，隔离测试脚本重新提案、确认、规划；hosted XCTest在物理iPhone17Pro/iOS26.6执行原生处理→上传→回执→review→下载字节一致性。PNG1 passed/0.561秒；JPEG1 passed/0.654秒。测试仅LIVE_IMAGE_DEVICE_INTEGRATION=1启用，并要求隔离8878地址。
- PNG720×372，alpha0–255，主体包围盒(317,75,420,372)，hash8b668b6eddf00c76fe61f11cf07181547e4f8cac04af3c871c46b34508e98f3e；JPEG656×369，hash80b88ed9b4ba5971591240d2d7f059b5f21c27f60724d3196609ef48e11d3a3c。独立下载接口均200；native-device-cutout.json/native-device-jpeg.json记录关联ID。
- 真机测试后恢复1.0.3 Build70并核验bundleVersion70，证据/tmp/quantum-image-restored-apps-final.json；窗口已交还笔记任务。生产配额未改。
- 界面限制：本轮原图通过DEBUG示例上传按钮进入正式上传接口；照片图库选择器未完成真机操作验收。完整真机GUI链路未过，已保留上述限制。

## 最终整合验证

以远端d228c06d为父提交，在独立临时Git索引三方合并共享入口，保留旅行功能和图片功能；没有修改canonical其他任务的脏文件。测试归档/tmp/quantum-image-release/src仅用于候选测试，非第二代码真源。
- 后端172 passed、14 subtests；旅行35 passed；Swift工作流/旅行/图片合同195 passed。
- 两个合同生成器检查、Ruff、iOS模拟器build-for-testing通过。
- 整合版完整图片UI1 passed/60.628秒，/tmp/quantum-image-release/ios-live2.xcresult。前一轮脚本误触附件栏已修正可见范围判断后重跑，未修改产品行为掩盖失败。
- 真机hosted链路与模拟器全UI分别验收，不能宣称真机全UI已通过。物理设备已恢复70并交还。
- 用户已授权push/deploy；发布仅图片独立差异，不含其他任务manifest、knowledge.py或test_cleanup_capabilities.py。TestFlight由笔记协调任务统一发布，本任务不重复上传。

## 最终联合候选相册入库修复

# image-workflow-20260927 相册入库修复
status: TESTED（增量补丁尚未提交；原图片167f已PUSHED）
base: 1914bce542cc268476a63064ddb456cd98e785c4
source: /tmp/quantum-image-final-1914bce5（干净候选归档上的最小补丁）
patch: /tmp/quantum-image-photo-source-fix.patch
冻结工作树未改动，git apply --check通过。

复用 uploadDocument + document_original_path；相册原件只上传/保存一次，Chat同时保留同一doc图片引用和附件来源。已有OCR、私有笔记、编译状态跟踪及source_refs沿用。图片参数和读取同时支持ga/doc；结果回传仅允许ga，避免生成结果入库。无新服务或模型依赖。

验证：
- 137 passed, 1 skipped, 90 warnings，14.21秒；/tmp/quantum-image-photo-fix-regression.log。
- 新增参数化集成路径：HTTP上传doc→私有笔记/编译排队→PCM workflow→device action→处理结果回执→可下载结果；校验单原件、无重复ga、跨用户/跨租户拒绝、缺失原件拒绝。设备像素处理在此服务端集成测试使用测试JPEG；不能替代真机。
- Swift ImageProposalContractTests：2 passed/0 failed；包含doc图片与附件共享引用持久化、原图字节不落消息；xcresult /tmp/quantum-image-release-derived/Logs/Test/Test-AIPlatformApp-2026.09.27_19-21-18-+0800.xcresult。
- 两个合同生成器 --check通过。
- 冻结1914与初版修复真机build-for-testing通过；最终修改完整模拟器test编译通过。

server_before: 本增量未部署
server_after: 本增量未部署
health_check: 未执行生产检查
functional_check: 本地集成通过；最终真机全UI仍未通过
rollback_point: 未建立，未部署
remaining_risks: 最终候选须重建并补图库→Chat→确认→处理→导出真机全UI；解析失败保留原件和失败状态，沿用既有文档合同。

由联合发布任务在冻结1914bce5干净worktree审查整合。规范main脏树未动。最终真机UI未过，不推送、不部署、不上传。

联合整合后独立回归：133 passed/1 skipped/6 warnings，7.21秒；图片、文档、清理、PCM、旅行模块均覆盖。Ruff与git diff --check通过。日志/private/tmp/quantum-final-photo-regression.log。
