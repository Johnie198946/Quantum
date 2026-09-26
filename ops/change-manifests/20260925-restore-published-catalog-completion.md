# 恢复历史已发布图书目录

- task_id: `20260925-restore-published-catalog`
- 目标：修复每日连载新媒体门禁误拦旧版已发布书籍，恢复完整图书目录；不放宽新版本的发布要求。
- 变更文件：`backend/services/knowledge_publication_store.py`、`tests/test_daily_publication.py`、本 manifest。

## 开工前盘点

- 既有阅读工作区 `codex/reading-selection-build54-20260925` / HEAD `ed85a752074008a743f360d44be6e205dafea9c0` 含 Build 62 未提交改动，保留原样。
- 本修复独立 worktree：`/Users/dengzhaoyu/Documents/AI Lab/.worktrees/restore-published-catalog-20260925`；`git status --short --branch` 初始干净，分支 `codex/restore-published-catalog-20260925`，HEAD `17c35d8eb60af1bff93078d895bd0f5e8358d8d8`，remote `origin https://github.com/Johnie198946/Quantum.git`，`git worktree list --porcelain` 已核对其他两个工作区分离。GitHub `main` 在修改前由 `git ls-remote` 核对为相同 SHA。

## 根因与修复

- 生产发布库仍有 10 条 `published` 记录（四系列：3/3/3/1）；全部只因 `required_publication_media_missing` 被 `PublicationStore.published()` 拒绝。历史记录发行时间均为 2026-09-19 至 09-24，新媒体门禁提交时间为 2026-09-25 10:17:28 CST；9 本旧版无媒体、1 本仅有双封面。生产只读验证显示：若仅豁免这一新规则，10/10 恢复，其他准入条件仍通过。旧 Wiki 入册候选为 0，不能用客户端缓存或个人藏书替代。
- 只在 `actual_release_at` 早于该门禁提交时间的**已发布**版本上跳过“五媒体必备”新条件；文件哈希、媒体有效性（如有）、编辑审核、权限、到期和 Wiki 引用校验照旧。新书的 stage / release 仍强制双封面和三插图；时间无效时保持拒绝。
- 不新增服务、数据库表、依赖或第二条书目接口。Build 62 的 UI 工作区没有混入本修复。

## 验证与交付

- 定向回归：`PYTHONPATH=. python3 -m pytest -q tests/test_daily_publication.py tests/test_publication_reader_projection.py tests/test_book_subscriptions.py --tb=short` → `67 passed, 4` 项既有 Pydantic 弃用警告。新增用例覆盖旧版无媒体仍可读、新版相同内容仍拒绝；既有用例覆盖四系列新书缺任一媒体即阻断。
- `git diff --check`：通过。
- server_before：`/opt/releases/ai-lab-platform-6b36b0786f2d.ILdQNA`，`.deployed-sha=6b36b0786f2d3b97f3e213b6dbfbc1da1736d64b`；只读生产抽样确认发布记录 10、当前可读 0。部署前 HTTPS `/health` 为 200 / `ok` / `0.8.0`。
- rollback_point：上述当前不可变 release；部署前需再次核对路径和 SHA，部署脚本必须做预期版本 CAS。
- status: `TESTED`；commit / remote_sha：待提交、推送和核验；server_after / health_check / functional_check：待部署后核验。
- remaining_risks：远端生产版落后于 GitHub 当前 `main`，部署最新 SHA 会同时包含两者之间已提交的改动；需完整部署门禁和回滚验证。恢复的最终书数与用户真机登录态须在部署后复查，不能仅凭本地测试宣称已修复。
