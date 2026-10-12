# Quantum TravelSpace

这是 iOS 工作流入口使用的生产 renderer，基于已批准的 ios-travel-v4 revision68 源码、照片、CSS 与动效。原型出处与 SHA 记录位于 `design/reference/ios-travel-revision68`；功能与后端偏离表见同目录的 `backend-alignment.md`。

## 构建

在仓库根目录安装一次依赖，再正常构建 iOS：

```sh
npm ci --prefix clients/travel-space
cd ios
xcodegen generate
```

Xcode 的 `Bundle approved TravelSpace renderer` 阶段运行 `ios/scripts/bundle-travel-space.sh`，将构建结果直接写到当前应用的 `TravelSpace` 资源目录。源码目录中的 1000 张风景照片是唯一杂志图片输入。Git 不收录 node_modules、开发构建输出或旧资源同步副本。缺少 Node.js 或依赖时构建明确失败，避免把过期 renderer 打包进应用。

```sh
node clients/travel-space/build.mjs
```

默认输出到 `clients/travel-space/.build/TravelSpace`。可以通过 `QUANTUM_TRAVEL_OUT` 指定独立输出位置。本地浏览器预览必须使用测试桥；业务请求仅由 WKWebView 内的原生客户端执行。

## 对接边界

- JS 不读取 token，不调用 HTTP 业务 API；CSP 禁止 `connect-src`。
- 原生 bridge 检查文件主框架、登录凭据代次、账号、租户、对话、任务与执行归属；销毁页面时取消任务、媒体下载、语音和定位。
- 当前成果按 artifact ID/hash 绑定；实际进度来自后端动作及成功回执。
- 个人手记、账本、批注、清单等作为 `client_state` 保存；不得覆盖后端的 actual_start/actual_end 或进度事实。
- 修改经串行 CAS 队列提交。修改先写入按账号和对话隔离的原生保护文件；冲突或离线时保留草稿，提供 JSON 导出。
- 账号隔离的现有读取缓存用于离线查看。401/403/404 不以缓存绕过权限；联网后再次读取版本并按当前 hash 同步。
- 地图使用 MapKit 实际底图；未知坐标保留文字。路线虚线表达游览顺序。GPS 仅由明确点击启动，保留实际定位点。
- 商户资料查询复用现有 authenticated Chat 能力，要求结构化来源、查询日期和币种。它不是库存或出票接口；预订仅记录用户已完成的真实订单。
- 用户可明确关联已有订单到 canonical action；后端 `confirmed_bookings` 确认后，后续改排必须保留该订单。

## 本地验收

```sh
npm --prefix clients/travel-space run test:model
python3 -m http.server 4274 --bind 127.0.0.1 --directory clients/travel-space/.build/TravelSpace
npm --prefix clients/travel-space run test:ui
npm --prefix clients/travel-space run test:journey
npm --prefix clients/travel-space run test:creation
npm --prefix clients/travel-space run test:booking
node clients/travel-space/tests/production-task-pages.mjs
```

UI 校验使用安装的 Chrome 与 Playwright WebKit。测试桥只位于 `tests/`，不被生产 entry 引用。测试数据的地点、资料来源和回执不代表真实商户或线上验收。

原生 UI 测试通过 DEBUG 的 `-travelSpacePreview` 启动实际入口和导航；该模式拒绝任务执行、个人数据保存、上传、定位和语音操作。最终生产联网、真机权限、公开检索、实际订单以及服务器部署不包含在这套隔离测试中。

`TravelSpaceUITests.testAomoriLiveWorkflow` 是单独的真实联网验收，普通运行默认跳过。只有显式配置 test runner 的 `QUANTUM_TRAVEL_LIVE_ACCEPTANCE=1` 才执行正常认证、澄清、计划确认、生成和采用；`QUANTUM_TRAVEL_CREATE_NEW=1` 明确创建新任务，`QUANTUM_TRAVEL_WORKFLOW_ID` 指定既有任务（原生仍检查当前账号和对话归属）。这两项与LIVE开关需同时写入xctestrun的EnvironmentVariables和TestRunnerEnvironmentVariables。它会写入当前账号的新旅行任务，不能混同为只读预览。DEBUG 的 `-travelLiveEvidence` 仅保存经过账号/任务与内容哈希校验的实际成果及状态，不保存凭据或确认令牌。验收使用用户正常登录的本任务模拟器，不以开发者自动登录或预览替代真实会话。

## 用户确认的十步主干

入口 → 右上角+直接悬浮对话 → 需求收敛后景点卡片 → 景点文件夹 → 完善计划 → 确认旅行计划/交通预订 → 行程制作 → 采用成稿 → 攻略与保存 → 旅行手记 → 手记按钮进入这趟旅行。create在计划确认阶段，start只在交通页确认之后。阶段审阅与最终采用按不同回执处理。

旧Dashboard/Create/Detail/PlanReview/Execution/Canvas和拓扑页面已移除；后台历史记录保留只读。照片处理是保留的唯一旧工作流，编辑器和原生处理回执沿用既有能力，表面统一当前风格。

最新结果见ops/acceptance/quantum-frontend-rebuild-20261012/ten-step-final：模型28项、浏览器110项/98axe均通过；真实青森五天成稿已确认，最终手记因服务器48k上游限制失败，不能用fixture通过代替真实成稿。后端client_state扩展未部署，仍需实际保存回执。
