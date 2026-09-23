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

- status: `PUSHED`（未部署）
- local_commit / remote_sha: `944249a35724edf1996b76bcf6aaa17f2c29f0b5`，GitHub `main` 已回读一致。
- Cron: 作者与独立审稿任务已原位更新并回读；作者每日 `08:00/14:00/18:00`，审稿 `10:00/10:30/16:00/16:30/20:00/20:30`，均启用。
- server_before/server_after: 均为 `/opt/releases/ai-lab-platform-6d7619918701.hRYPgT`，`.deployed-sha=6d761991870150f65a7c1468388ccbb142eeba0e`。
- deployment: 标准 exact-SHA 部署在原子切换前 fail-closed：`backend image revision mismatch: api=6d761991... expected=944249a...`；未改动线上 release。
- health_check: 旧生产 API 容器 `running/healthy`。
- functional_check: 本地 `57 passed`；Cron 提示回读包含 `ai-toolkit` 与 `research_deposit`。
- rollback_point: 无需回滚，部署未越过镜像验证与原子切换。
- remaining_risks: 需先构建并验证目标 SHA 的离线后端镜像、更新 attestation，再重跑 exact-SHA 部署；其后首期正文还须经过作者、独立审稿与确定性发行门禁。配置、调度或生成启动均不能代替出版成功。
