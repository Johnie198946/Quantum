# Completion Manifest

- `task_id`: `ios-user-profile-isolation-20260913`
- `goal`: 补齐 iOS 多租户后端中工作流与预热入口的用户级 Hermes Profile 隔离；保留 Main 作为无状态基线角色，不为每个用户复制业务 Agent。
- `status`: `COMMITTED`

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
- `python3 -m ruff check scripts/hermes_bridge.py tests/test_bridge_usage_delta.py tests/test_client_session_notes.py`: 通过。
- `python3 -m py_compile scripts/hermes_bridge.py`: 通过。
- `git diff --check`: 通过。
- 首次直接调用全局 `pytest` 因仓库根未进入模块路径而在收集阶段失败；改用仓库约定的 `python3 -m pytest` 后全部通过。

## 交付与部署

- `implementation_commit_sha`: `c90affe16370ef736b77cd07e2611685719d02a3`
- `github_remote/ref/sha`: 用户未授权 push，未执行。
- `server_before`: 不适用；未授权部署，未读取服务器。
- `server_after`: 不适用；未执行部署。
- `health_check`: 不适用；未执行部署。
- `functional_check`: 本地 63 项相关回归通过。
- `rollback_point`: 开工基线 `bc791e55c543473f139bc2778744c144bf5347bf`；可回退本任务本地提交，未触及远端或服务器。

## 风险与未完成项

- 本次只治理实际承载租户状态的 Agent 入口；没有为用户创建可见的命名业务 Agent，这是刻意避免重复模型和运维膨胀。
- 未执行真机/模拟器测试：本次没有修改 iOS 客户端，隔离发生在服务端原生 Agent 生命周期。
- 未 push、未部署；线上行为不会因本地提交自动变化。
