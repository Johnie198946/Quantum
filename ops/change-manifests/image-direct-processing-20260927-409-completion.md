# 图片端侧取消后重试409增量

task_id: image-direct-processing-20260927-409
status: TESTED
branch: codex/image-direct-processing-20260927
worktree: /Users/dengzhaoyu/Documents/AI Lab/.worktrees/image-direct-processing-20260927
head/local_commit: b9e4d128dd5839bae89cff39790fb8240297e23e；未提交
remote_sha: 本增量未推送
server_before: 协调任务报告b9；本轮只读诊断
server_after: 未部署、未写生产数据
health_check: 未做发布健康检查
functional_check: 58 passed；Ruff和git diff --check通过
rollback_point: 本地冻结图片补丁921cfcd25d920632b20358b21bb3b9cb1d6847c370f3ea4f3ad2f4a7aef463e7；无新增服务器回滚点

## 盘点与所有权
本轮为原图片任务发布前阻断修复，经既有协调明确分工在原隔离worktree继续，不创建平行修复；根任务不编辑workflows.py、统一发布。开工status为上一轮13 tracked修改+completion manifest，git diff --binary与冻结/tmp/image-direct-own.patch字节完全一致。branch/HEAD如上。origin=https://github.com/Johnie198946/Quantum.git；source=https://github.com/Johnie198946/ai-lab-platform.git。worktree列表与原completion记录一致，canonical main仍21250c7，仅只读。未覆盖原冻结patch。

## 根因与最小改动
生产最近窗口3次retry接口409对应同一图片执行，后缀d8012254。只读SQL事务验证cancelled、output_kind=image、唯一OUTPUT_FORMAT节点succeeded/attempt1。默认重试只选择failed或未成功节点，抛“没有可重试的节点”。截图附件缺失，不能声称已直接核对截图。

- backend/api/workflows.py：仅图片设备取消/失败且参数节点已成功时，显式复用image_edit节点重试；远端重试不可用返回503并回滚本地状态，避免假排队。
- backend/services/image_processing.py：选参数artifact时校验当前节点attempt，避免同秒新旧artifact时间相同而选中旧终态action。
- tests/test_image_processing.py：完整已有JPEG链路内覆盖CANCELLED与FAILED恢复、新attempt/new instruction/new action、同created_at、旧终态回执拒绝/幂等不污染新执行、普通workflow仍409、远端不可用状态不变，以及恢复后真实JPEG字节下载。

## 验证
`pytest tests/test_image_processing.py tests/test_workflows_api.py tests/test_client_action_capabilities.py tests/test_workflow_event_projection.py -q`：58 passed，日志/tmp/image-409-tests.log。Ruff三文件与git diff --check通过。测试模拟远端retry及Bridge事件投影，不冒充真实设备或模型执行。
增量仅相对原冻结图片补丁，不含原差异：/tmp/image-409-increment.patch
SHA256: 92b6292f3af1a622afab3fc98a7ab999b24bfbbdf41baf600cb6010a2e732ed0
原/tmp/image-direct-own.patch及921cfcd摘要保持不变。根任务仅应用本增量并做联合验证。

remaining_risks: 新版组合真机完整验收尚未执行；本增量未部署，生产409尚未实际恢复。后续由统一发布任务建立服务器回滚点并验证部署。
