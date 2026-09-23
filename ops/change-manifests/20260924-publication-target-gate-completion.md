# Publication target gate — completion receipt

- task_id: `20260924-publication-target-gate`
- scope: 将单篇目标发布验收与全局每日连载完整性告警分离；不关闭全局缺刊告警，不绕过目标回读。
- branch: `main`
- status: `TESTED`

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

- local_commit: pending
- remote_sha: pending
- server_before: pending
- server_after: pending
- health_check: pending
- functional_check: pending
- rollback_point: pending
- remaining_risks: production deployment and exact target-mode readback pending.
