# Publication series independence — completion receipt

- task_id: `20260924-publication-series-independence`
- scope: 删除跨连载原子齐套门禁；每个 edition 仅由自身审稿、权利、哈希、stage/readback 条件决定能否发布。
- branch: `main`
- status: `VERIFIED`

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
- deployment egress contract: `12 passed, 106 deselected`；允许任意合法且 HTTP/HTTPS 一致的 `127.0.0.1` 端口，仍拒绝外部地址、凭据、额外变量、端口不一致及越界端口。

## Delivery

- release implementation commit: `e6227efcace63cb87f2137feb5567d03cf067e14`。
- deployed commit / remote SHA: `965abf1f2d4c5acc6f76c838f87fa6e4a3991afd`；包含发行解耦及 loopback egress 契约漂移修复，部署前 GitHub `main` 已回读一致。
- operational install: 仓库与 `~/.hermes/scripts/publication_release_remote.py` SHA-256 均为 `14e53d97edf2f1566eca6043d43e9e3c2e9631daab58c76cd3e73248c60453f4`。
- server_before: `/opt/releases/ai-lab-platform-5ab35ef8f959.sLeSOm`，revision `5ab35ef8f959aabd5c5c6a324624860662f6e64d`。
- server_after: `/opt/releases/ai-lab-platform-965abf1f2d4c.InR7lb`，`.deployed-sha`、API OCI revision 均为 `965abf1f2d4c5acc6f76c838f87fa6e4a3991afd`。
- health_check: API `running healthy`、`/ready=ready/0.8.0`；Hermes Bridge `ok/v6.0`。
- functional_check: 生产 `publication_operator.py release-due` 在四条当日 series 全部 missing 时返回 exit `0`、`ok=true`、`status=ok`，同时完整保留四条 `missing`；Mac 发行 sweep 同样 exit `0`、`global_attention=true`、`issues.missing` 四条、无重复发布。
- cron topology: 原任务 `5a3f2a2eb988` 只处理原三条连载；新增独立 `ai-toolkit` 作者任务 `171a125ddb63`（`5 8,14,18 * * *`）。二者都禁止全局齐套停止条件；独立 reviewer 与确定性 release sweep 保持职责隔离。
- rollback_point: `/opt/releases/ai-lab-platform-5ab35ef8f959.sLeSOm`。
- deployment incident: 首次 `e6227ef…` 部署因脚本硬编码 `7890`、生产已使用受控 loopback `17897` 而安全回滚；API 回读恢复为旧 SHA。修复并测试契约后以新 SHA 部署成功。
- remaining_risks: 当日四条缺刊是真实运营状态，继续告警；共享 release sweep 只是定时基础设施，不是原子发布集合。
