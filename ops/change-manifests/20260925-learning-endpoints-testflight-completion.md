# 学习接口 404 修复与 TestFlight 配套交付

- task_id: `20260925-learning-endpoints-testflight`
- 目标：恢复 Build 63 已调用但生产缺失的 `GET /api/v1/me/learning-resume` 与混合练习接口；复用已上传的前端二进制。
- 用户授权：本轮明确要求修复、直接部署和上传；后端可推送 GitHub 并部署生产。TestFlight `1.0.3 (63)` 已在前一轮上传，本轮无客户端源码更改，不上传内容相同的重复构建。

## 开工盘点

- 起点：独立干净 worktree `/Users/dengzhaoyu/Documents/AI Lab/.worktrees/learning-endpoints-20260925`，branch `codex/learning-endpoints-20260925`，HEAD `2f62cc4d0a1e7ec83ff0a1c535950d2b0a56eceb`。
- remote：`origin=https://github.com/Johnie198946/Quantum.git`；`git ls-remote origin refs/heads/main` 初始同为 `2f62cc4d0a1e7ec83ff0a1c535950d2b0a56eceb`。
- `git worktree list --porcelain` 已核对旧阅读、学习和图书热修 worktree 各自独立；其未提交改动没有被覆盖、暂存或混入。

## 根因、复用与变更

- 生产主线未注册学习恢复与练习路由。无认证只读请求均为 HTTP 404，主线代码搜索也未找到这两组路由；Build 63 客户端已调用这些路径。
- 复用此前学习工作区已实现的练习路由和测试，将其接入当前主线的 `require_auth`、统一协议门禁、现有书籍正文授权与 Hermes chat 调用；保留同一用户隔离及答案发布前隐藏的原有检查。
- 延伸既有书籍订阅与阅读进度主路径：保存章节/段落/字符位置、提供有证据锚点的学习恢复要点；增量迁移旧订阅表的三个可空字段，新练习表由既有 `init_db` 建表。内存编辑仅使当前用户的练习画像信号失效。
- 变更文件：`backend/api/learning.py`、`backend/api/subscriptions.py`、`backend/api/hot_memory.py`、`backend/models/tenant.py`、`backend/db.py`、`backend/main.py`、`tests/test_learning_exercises.py`、`tests/test_book_subscriptions.py`、`tests/test_book_progress_legacy.py`、本 manifest。无新依赖、无第二条 AI 调用链。

## 测试与交付记录

- `PYTHONPATH=. python3 -m pytest -q tests/test_learning_exercises.py tests/test_book_subscriptions.py tests/test_book_progress_legacy.py::test_additive_migration_preserves_unversioned_position_idempotently tests/test_daily_publication.py tests/test_publication_reader_projection.py tests/test_jev_selector.py tests/test_pcm_jev_routing_contract.py --tb=short` → `115 passed`、4 个既有 Pydantic 弃用警告。回环 HTTP 用例需要允许绑定 `127.0.0.1`；普通沙箱仅该用例报 `PermissionError`，受控权限重跑后全绿。
- `python3 -m ruff check` 变更文件、`python3 -m compileall -q`、`git diff --check`：通过。
- 旧 `tests/test_book_progress_legacy.py` 全组在当前系统 Starlette/httpx 组合下因 `TestClient(... app=)` 初始化失败；这是测试环境兼容性，非产品断言；其中直接覆盖幂等迁移的用例单独通过。
- status: `TESTED`；commit / remote_sha：待提交与远端核验。
- server_before：预计为已验证图书热修 `2f62cc4d0a1e7ec83ff0a1c535950d2b0a56eceb`，部署前须重新读回。
- server_after / health_check / functional_check：待部署后核验；不得预填成功。
- rollback_point：当前不可变 `2f62cc4` release 与旧离线镜像，部署前须验证和备份。
- remaining_risks：需构建并校验新的离线 API 镜像、完成标准发布门禁和生产路由检查；Apple TestFlight Build 63 已上传但处理/测试组可见性尚未核验，真实登录与模型输出仍需真机验收。
