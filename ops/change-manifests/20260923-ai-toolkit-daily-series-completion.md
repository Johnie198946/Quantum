# AI 工具实战每日连载 — 完成清单

- task_id: `20260923-ai-toolkit-daily-series`
- scope: 在既有 Quantumn editorial-v2 / publication 主链增加第四个每日系列 `ai-toolkit`，不新增 Runtime 或平行发行链。
- branch: `main`
- start date: `2026-09-24`

## 变更

- `config/quantumn-daily-publication.json`: 注册系列、作者单轮上限改为 4。
- `backend/services/knowledge_publication_store.py`: 注册每日书架及启用日期。
- `scripts/publication_release_remote.py`: 纳入每日确定性完整性核对。
- `docs/prompts/quantumn-editorial-v2.md`: 固化新手教程、需求澄清、Skill/插件、实测、Wiki-first、受控 research_deposit 与 Quantum 能力证据边界。
- 两个测试文件覆盖启用日期与发行侧每日预期。

## 验证

- `python3 -m pytest -q tests/test_daily_publication.py tests/test_publication_remote_release.py`
- 结果：`57 passed, 4 warnings`。
- `git diff --check`: 通过。

## 交付状态

- local_commit: 待提交
- remote_sha: 待推送后回读
- server_before: 待部署前回读
- server_after: 待部署后回读
- health_check: 待执行
- functional_check: 待执行
- rollback_point: 待建立
- remaining_risks: 首期正文仍须经作者、独立审稿与确定性发行门禁，不能用配置成功代替出版成功。
