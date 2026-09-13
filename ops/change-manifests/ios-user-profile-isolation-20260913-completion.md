# Completion Manifest

- `task_id`: `ios-user-profile-isolation-20260913`
- `goal`: 补齐 iOS 多租户后端中工作流与预热入口的用户级 Hermes Profile 隔离；保留 Main 作为无状态基线角色，不为每个用户复制业务 Agent。
- `status`: `VERIFIED`

## 变更文件

- `scripts/hermes_bridge.py`: 工作流节点和会话预热构造原生 `AIAgent` 时，使用 Hermes 官方 ContextVar override 绑定用户沙箱 `HERMES_HOME`，并在 `finally` 中恢复。
- `tests/test_bridge_usage_delta.py`: 验证工作流在用户 Profile 内构造 Agent，结束后恢复宿主上下文。
- `tests/test_client_session_notes.py`: 验证预热在用户 Profile 内构造 Agent，结束后恢复宿主上下文。

## 开工前 Git 盘点

- `status`: `main...source/main`；已有两份被修改和一份未跟踪的其他任务 manifest，均未覆盖、暂存或纳入本任务。
- `branch`: `main`
- `HEAD`: `bc791e55c543473f139bc2778744c144bf5347bf`
- `remote`: `origin=https://github.com/Johnie198946/Quantum.git`; `source=https://github.com/Johnie198946/ai-lab-platform.git`
- `worktree`: 当前 `/Users/dengzhaoyu/Documents/AI Lab/Quantum-2.0`；其余历史/独立 worktree 未改动。

## 架构判定

- 用户沙箱、`profile.json`、独立 `state.db` 和普通聊天的请求级 `HERMES_HOME` 绑定已经存在，属于“部分实现”。
- 本任务复用 `TenantHermesSandbox`、`_sandbox_hermes_home` 及 Hermes 官方 `set_hermes_home_override/reset_hermes_home_override`，未新增 Profile 表、每用户 Agent 行、进程或配置层。
- 无工具、无技能、无记忆、无会话的澄清模型保持无状态；启动预热模型不承载租户身份。

## 测试与校验

- `python3 -m pytest -q tests/test_bridge_usage_delta.py tests/test_client_session_notes.py tests/test_agent_os_runtime_acceptance.py`: `63 passed`。
- 合并最新 `source/main` 后，连同知识治理和部署契约回归执行 `201 passed`。
- `python3 -m ruff check scripts/hermes_bridge.py tests/test_bridge_usage_delta.py tests/test_client_session_notes.py`: 通过。
- `python3 -m py_compile scripts/hermes_bridge.py`: 通过。
- `git diff --check`: 通过。
- 首次直接调用全局 `pytest` 因仓库根未进入模块路径而在收集阶段失败；改用仓库约定的 `python3 -m pytest` 后全部通过。

## 交付与部署

- `implementation_commit_sha`: `c90affe16370ef736b77cd07e2611685719d02a3`
- `deployed_commit_sha`: `a9725bbc9e5ac7277982cf6ddd6a6291161dcf71`，包含本任务、并发 Build 37 提交及合并时 `source/main` 的已测试提交。
- `github_remote/ref/sha`: `source/main` 与 `origin/main` 均经 `git ls-remote` 核验为 `a9725bbc9e5ac7277982cf6ddd6a6291161dcf71` 后才部署。
- `server_before`: `/opt/releases/ai-lab-platform-0ec9b84a5242.PIKs1Y`，`.deployed-sha=0ec9b84a524288d076aac0e6831f671e14e8d883`；API、Bridge、Chat Worker 均健康，无部署进程占锁。
- `server_after`: `/opt/releases/ai-lab-platform-a9725bbc9e5a.x3WRsy`，`.deployed-sha=a9725bbc9e5ac7277982cf6ddd6a6291161dcf71`；四个后端服务镜像均为 `sha256:af205cf774eae2b9d16bd3bb10e4c4525d9ac2ca723d92768bc695a428489f5f`，OCI revision 与部署 SHA 一致。
- `health_check`: API `/ready=ready/0.8.0`、`/health=ok/0.8.0`；Bridge `/health=ok/v6.0`；`hermes-bridge`、`hermes-chat-worker` active；8 个 Compose 服务均为 running/healthy。
- `functional_check`: 本地合并后相关回归 `201 passed`；已部署 release 上工作流、预热和普通聊天 Profile 隔离回归 `4 passed`。
- `rollback_point`: release `/opt/releases/ai-lab-platform-0ec9b84a5242.PIKs1Y`；旧镜像标签 `ai-lab-platform-api:rollback-before-a9725bbc9e5a`；旧 attestation `/opt/ai-lab-shared/deploy-backups/ios-user-profile-isolation-before-a9725bbc9e5a/offline-images.attested`。

## 部署过程说明

- 首次 exact-SHA 部署因后端离线镜像仍标记旧 revision 而在切换 release 前安全退出。
- 完整镜像重建因服务器无法访问 Docker Hub 的固定基础镜像而超时。经 Git diff 核验，生产 SHA 到目标 SHA 的镜像输入只有 `scripts/hermes_bridge.py` 修改，`backend/`、`config/` 无变化且三者均无删除；因此复用已证明的生产镜像父层，覆盖目标 SHA 的三个源码目录并更新 revision。
- 候选镜像通过 linux/amd64、非 root、healthcheck、revision、离线 `pip check` 和 `import backend.main` 校验后，才原子更新四个服务标签和 attestation；随后标准 exact-SHA 部署成功。

## 风险与未完成项

- 本次只治理实际承载租户状态的 Agent 入口；没有为用户创建可见的命名业务 Agent，这是刻意避免重复模型和运维膨胀。
- 未执行真实双账号生产对话；服务端生命周期隔离由本地和已部署 release 回归覆盖。
- 本次 Profile 修复没有修改 iOS 客户端；同一合并 SHA 中的 Build 37 源码已推送，但未上传 TestFlight/App Store。
