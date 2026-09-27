# Travel acceptance receipts

这些脚本只创建临时 SQLite、私有 AI_LAB_HOME 和合成测试用户，不连接生产数据库。模型验收会使用本机已有 Hermes 模型配置并产生调用费用。不要对生产服务运行故障注入脚本。

- 从任务 worktree 运行，设置 `PYTHONPATH=.`，使用满足仓库 `requirements-bridge-worker.lock` 的环境。本机已验证解释器为 `/tmp/travel-hermes-validation-env/bin/python`，OpenAI SDK 2.24.0；系统 Python 的 1.14.1 不兼容当前 Hermes，不能用于模型验收。Office 与 platform harness 的日志记录本次结果。
- `full-client-local-harness.py` 启动 8847 和真实 Hermes，配置写至 `/tmp/travel-full-client-config.json`。将其中 token 通过 `TEST_RUNNER_TRAVEL_FULL_E2E_TOKEN` 传给 xcodebuild；运行 `AIPlatformAppUITests/TravelFlowUITests/testFullClientJourneyWithStageWaits`。使用空临时库和本任务专用模拟器，测试在真实 UI 创建任务。
- `client-local-harness.py` 在 8846 启动隔离故障注入服务。先通过 `TRAVEL_CLIENT_SESSION_ID` 指定专用模拟器当前测试聊天会话 ID，使固定成果归属该客户端会话；不指定时仅用于 API 测试。将输出配置中的 token 和 artifact_id 分别以 `TEST_RUNNER_TRAVEL_E2E_TOKEN`、`TEST_RUNNER_TRAVEL_E2E_ARTIFACT` 传给 xcodebuild，运行十轮与离线测试。勿提交包含 JWT 的临时配置。
- 所有 iOS 测试的 DEBUG 启动参数仅省略身份登录界面，运行正式 View、网络层和本地存储。网络故障测试由隔离服务返回 503，不代表无线网络物理断开。
- 性能样本的场景、样本量、分段和限制见 JSON；本机结果不能解释为公网 SLO。Chrome 登录态验收尚无成功记录。

最终客户端通过记录：`client-full-final-results.txt`（两项测试 236.771 秒），包含创建至最终采用与独立保存重开；两项应按 FullClient → SavedRealNotebook 顺序运行于同一隔离环境。`full-client-local-harness.py` 已含配图地址、独立 durable store 和真实 worker；退出会停止其 worker。需要回读现有验收库时可将 `TRAVEL_ACCEPTANCE_ROOT` 指向本任务创建的临时 root，不可指向生产数据。

`image-api-harness.py` 依赖上述服务与配置，只验证公开测试图片的归档与隔离。`client-illustration-results.json` 记录真实生成的两张 Seedream 图片和截图失败项；completed 状态中仍须检查 failed_indices，不能只看任务终态。

Cloud Google Maps acceptance (2026-09-27): see `cloud-maps-result.txt` and
`cloud-maps-date-result.txt`. These use a temporary server Hermes runtime and
public browsing, not desktop Chrome or production App sessions. `cloud-reference.jpg`
is the actual https://www.hitou.or.jp/ screenshot archived through the task's
reference function. Byte capture passed; this minimal temporary Linux environment
lacks complete CJK fonts and some external page assets, so it is not final visual
quality acceptance. The production provisioning list includes `fonts-noto-cjk`.
`cloud-server-version.json` is the independently re-read server version; it changed
during this task through another operation, not a deployment by this task.
