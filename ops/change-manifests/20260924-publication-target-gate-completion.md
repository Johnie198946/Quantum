# Publication target gate — completion receipt

- task_id: `20260924-publication-target-gate`
- scope: 将单篇目标发布验收与全局每日连载完整性告警分离；不关闭全局缺刊告警，不绕过目标回读。
- branch: `main`
- status: `VERIFIED`

## Root cause

`publication_release_remote.py` 原先只有全局退出语义：当天任一每日系列缺刊、重复出版或当日阻塞都会触发 exit `3`。因此指定文章已成功发布时，其他系列缺刊仍会让该次目标交付显示为失败。

## Change

- 增加 `--target-publication-id`。
- 目标模式要求该精确 publication ID 在发布后状态中唯一回读为 `published`，否则仍返回非零。
- 其他系列缺刊继续通过 `global_attention=true`、`issues.missing` 和全局模式 exit `3` 报警。
- 不指定目标时保持原全局门禁语义。

## Verification

- `PYTHONPATH=. python3 -m pytest -q tests/test_publication_remote_release.py tests/test_daily_publication.py tests/test_publication_editorial_workflow.py`
- result: `77 passed, 4 warnings`
- `git diff --check`: passed
- tests cover: target published with unrelated global gaps; exact target blocked; invalid target rejected before SSH.

## Delivery

- local_commit / remote_sha: `59795da073ec16fcae53ff676f48ea392127adab`，GitHub `main` 已回读一致。
- operational_install: 仓库脚本与 `/Users/dengzhaoyu/.hermes/scripts/publication_release_remote.py` SHA-256 均为 `217cca7f508e8d8b290485edc2ef48ca6481f7f0ef8b977ffbd72aefbe21e2e7`。
- server_before / server_after: `5ab35ef8f959aabd5c5c6a324624860662f6e64d`；本修复只改变 Mac 侧远程发行客户端，不需改动生产 API。
- health_check: 生产 API `running healthy`。
- functional_check: 对 `publication-9b5b298fb96bd44dfccb04c36fad8134` 执行目标状态回读，exit `0`；目标为 `published`，`edition-ae6c48dcf93ebbd99b8ad3482627154d`。汇总已正确显示 `expected=4`，同时保留 `global_attention=true` 与四条当日缺刊告警。
- rollback_point: GitHub `69010a2b723a91f2d49fa2bf0992c9d8356c80a8` 的上一版客户端。
- remaining_risks: `2026-09-24` 四条每日连载确实尚未出版；它们继续作为全局运营告警，不再误判本期目标发布失败。
