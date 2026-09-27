# 清理真机验收：旧客户端笔记工具兼容

task_id: chat-cleanup-client-compat-20260927
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
head/local_commit: 基线5cd60e418d7b462568469d49782bb90f9d78e381；修复待提交
remote_sha: origin/main 5cd60e418d7b462568469d49782bb90f9d78e381，git ls-remote已核验
server_before: 5cd60e418d7b462568469d49782bb90f9d78e381，SSH读取.deployed-sha
server_after: 本补丁尚未部署
health_check: 现有生产API /ready=ready，8容器healthy；不是本补丁部署后验收
functional_check: 109项相关测试通过；ruff与git diff --check通过；本补丁真机待部署后验证
rollback_point: 尚未建立本补丁部署回滚点；部署前沿用现有update.sh/镜像/数据库快照流程
remaining_risks: Mac锁屏及XCTest系统认证阻断真机；共享服务器窗口协调中；TestFlight未上传

## 目标与证据

用户已授权完成、推送和配套后端部署，以及真机验证后上传包含答题能力的TestFlight。
Build66真机已通过：清理列表真实9条、无待办tab、单击差异页、Chat自然语言检索和比较入口、共享比较页正确显示差异。
基础笔记创建首次返回knowledge_action_missing，后续返回note_client_upgrade_required；显式省略layout与illustration字段后生成确认卡，QA note A（Budget 300）和QA note B（Budget 500 / Reminder reserve early）均经确认创建且显示完成回执。
因此不移除服务端门禁；复用请求级工具schema装配，按签名note_illustration_v1裁剪旧端新字段及配图专属工具，并将能力位纳入Agent缓存签名。新端保留全部schema。未新增架构、服务或依赖。
尚未完成测试笔记合并/恢复闭环。用户手动操作期间曾出现真实笔记合并完成卡，该操作不归因为本任务自动验收，不据此宣称完整验收通过。

## 盘点与变更

开始HEAD05a0efabf6ccca5238d1389205a665cc866fd318，main；fetch后仅fast-forward至5cd60e4，无merge/rebase。
origin=https://github.com/Johnie198946/Quantum.git；source=https://github.com/Johnie198946/ai-lab-platform.git；唯一worktree为上述规范目录。
status已有AGENTS、清理/笔记manifest及未跟踪回执；均保留。笔记任务确认拟改文件无在途修改。
本补丁文件：scripts/hermes_bridge_runtime/{agent_execution,receipts}.py、tests/{test_client_session_notes,test_product_capabilities}.py及本manifest。
顺带删除agent_execution已有8项重复模块导入，使触及文件ruff通过；实际模块导入仍由同文件集中导入保留。

## 验证

PYTHONPATH=/private/tmp/cleanup-test-asgi python3 -m pytest tests/test_client_session_notes.py tests/test_note_illustration_capabilities.py tests/test_cleanup_capabilities.py tests/test_product_capabilities.py tests/test_pcm_semantic_capabilities.py -q：109 passed，6既有弃用warning。日志/private/tmp/cleanup-compat-related.log。
覆盖旧端create/update工具字段裁剪、新端字段保留、全局注册表不被污染、新旧能力切换schema和缓存签名不同；既有服务端旧端门禁测试仍通过。
扩展运行含test_bridge_usage_delta时：120 passed / 1 failed，失败为workflow入口测试未提供新要求的trusted agent_config。在未修改的5cd60e4归档/private/tmp/cleanup-compat-baseline独立重跑同用例亦失败；不将此既有失败冒充本补丁通过。基线日志/private/tmp/cleanup-compat-baseline.log。
本机归档/private/tmp/Quantumn-1.0.3-66-chat-cleanup.xcarchive签名在可访问系统证书服务时复核通过；未上传。
生产日志正文读取被自动审批拒绝（可能含用户内容）；未规避拒绝，仅使用真机反馈、代码、测试及状态级健康检查定位。

## 交付待办

提交、推送并核对SHA；协调共享部署窗口并建立回滚点后部署；旧端自然语言重新验收；完成合并/恢复与TestFlight上传。
