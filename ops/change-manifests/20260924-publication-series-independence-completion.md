# Publication series independence — completion receipt

- task_id: `20260924-publication-series-independence`
- scope: 删除跨连载原子齐套门禁；每个 edition 仅由自身审稿、权利、哈希、stage/readback 条件决定能否发布。
- branch: `main`
- status: `TESTED`

## Root cause

发行存储层原本已逐条检查并发布 due edition，但随后把任一系列缺刊/阻塞汇总成 `attention_required`，operator 和 Mac 客户端再将其升级为整个 sweep 的非零退出。客户端还维护一份硬编码的“每日系列全集”，使新增连载自动扩大所谓全局齐套集合。结果是：一条合格连载已经发布，仍会因无关连载缺刊被报告为发行失败。

## Correct model

- 每条 series/edition 是独立发布单元。
- 单篇 editorial approval、权利、内容哈希、stage/readback 和幂等性门禁保留。
- `missing`、`blocked`、`attention_required` 只用于告警和监控，不控制其他 edition 的发布或 sweep 退出状态。
- 新 series 由服务端配置/status 自动进入观测；客户端不维护“必须全部齐套”常量。
- 作者产能限制按 series 表达为 `per_series_max_issue_count=1`，不再使用随系列数增长的全局上限。
- `--target-publication-id` 仅是可选的精确回读断言，不是绕过全局门禁的特批路径。

## Verification

- `PYTHONPATH=. python3 -m pytest -q tests/test_publication_remote_release.py tests/test_publication_release_remote.py tests/test_daily_publication.py tests/test_publication_editorial_workflow.py`
- result: `87 passed, 4 warnings`
- `git diff --check`: passed
- 覆盖：单条成功而其他条缺失/阻塞；状态告警保留但默认退出成功；目标未发布仍失败；未来未知 series 无需修改客户端常量即可进入观测；真实 transport/readback 错误仍失败。

## Delivery

- local_commit / remote_sha: pending
- operational_install: pending
- server_before / server_after: pending
- health_check: pending
- functional_check: pending
- rollback_point: `65e2f603e5bd7924b67a22223aba13eafc05e412`
- remaining_risks: exact-SHA 部署和生产端部分缺刊回读待完成。
