# 清理差异与 Chat / PCM 完整接入

task_id: chat-cleanup-pcm-20260927
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
head/local_commit: 基线 ed673c0cbceb239693db3864fe3db2f3bc276866；本任务提交前
remote_sha: origin/main ed673c0cbceb239693db3864fe3db2f3bc276866；本任务尚未推送
server_before: 出版任务报告 ed673c0cbceb239693db3864fe3db2f3bc276866，待切换前独立核验
server_after: 本任务未部署
health_check: 本任务待部署后执行
functional_check: 干净构建输入后端111项、iOS单元254项及UI2项全部通过；真机线上闭环待配套后端发布
rollback_point: 本任务部署前建立；现生产发布目录由出版任务报告为 /opt/releases/ai-lab-platform-ed673c0cbceb.3umr96
remaining_risks: 本任务尚未推送/部署；真机新后端操作及TestFlight上传尚未完成

## 授权与架构命中

用户“帮我完成。完后后推送和部署”明确授权提交、推送及配套后端部署；此前明确授权与答题能力一起上传TestFlight，仍须先完成真机验证。
已存在笔记merge/archive/restore、conversation.lifecycle、task.update、PCM本地提案签名、KnowledgeActionExecutor、CAS与回执；扩展这些主路径。仅新增只读比较投影knowledge.note.compare和已有knowledge-actions路由下merge-preview。未新增服务、存储、依赖或JEV。
首页待办不可用或无候选时隐藏标签。查看差异一次进入；折叠共同段落、突出不同字词、逐项选择和全文预览，原文不截断。Chat复用同一差异页，选择变更后生成新签名提案；自然语言确认只绑定当前会话唯一待确认操作，多方案及不匹配动作拒绝。
不猜测“当前笔记”或对话ID：未明确对象时通过现有搜索/澄清或清理建议选取。超过256 Markdown块时转为全文显式选择，保留内容。

## 开工盘点与协作隔离

- 规范目录 pwd -P 为当前worktree；唯一登记worktree；分支main。
- 本轮开始HEAD 91b17a0e7d4df579a9e1d36e5ef497084670cc6e；之前清理视觉基线9fbc4e0b。
- origin https://github.com/Johnie198946/Quantum.git，source https://github.com/Johnie198946/ai-lab-platform.git；实际交付目标origin/main。
- status dirty；并行笔记配图、Hermes恢复、WorkflowDashboard及AGENTS改动均保留，不混入本任务提交。
- 学习/出版发布后fetch origin main，内容三方合成并仅fast-forward至ed673c0c；未创建历史merge/rebase。笔记任务明确暂停后操作，完成后通知恢复。
- 现场完整备份及清单：/private/tmp/chat-cleanup-ff/backup、inventory.json。共享冲突是两方相邻新增字段/注册项；保留learning与illustration双方数据，PCM生成物重新生成。
- 本任务逐文件构建输入：/private/tmp/chat-cleanup-owned/files.json；干净验证/归档输入 /private/tmp/chat-cleanup-release，来源git archive ed673c0c加本任务明确文件/片段。未复制并行未提交配图能力。

## 变更文件

后端：backend/api/{chat,knowledge_actions}.py、backend/capability_handlers.py、backend/services/{capability_catalog,knowledge_action_capability}.py、scripts/hermes_bridge_runtime/knowledge.py。
PCM：capabilities.yaml、bindings.yaml、client_actions.yaml、project_task.yaml、ios-scope.yaml；现有manual/coverage/matrix同步生成。
iOS：UIModels、APIClient、ChatView、ChatMessageStreamView、ChatStatusCards、TenantSessionCoordinator、BlockCardDispatcher；新增CleanupMergeReviewView；AIPlatformApp DEBUG验收入口、工程文件及Build66。
验证：CleanupMergeTests、CleanupMergeUITests、test_cleanup_capabilities、test_product_capabilities、test_ios_capability_matrix。
共享文件仅提交本任务片段，其他任务代码留在工作区。

## 验证与修复

- 干净输入：PYTHONPATH=/private/tmp/cleanup-test-asgi python3 -m pytest tests/test_cleanup_capabilities.py tests/test_product_capabilities.py tests/test_knowledge_actions.py tests/test_ios_capability_matrix.py tests/test_merge_proposal_contract.py tests/test_capability_gateway.py tests/test_pcm_semantic_capabilities.py tests/test_learning_exercises.py -q：111 passed，6条既有弃用warning。日志 /private/tmp/chat-cleanup-release-backend.log。
- xcodebuild test，AIPlatformAppTests全部254项及CleanupMergeUITests两项，0 failures，TEST SUCCEEDED。日志 /private/tmp/chat-cleanup-release-ios-final.log；模拟器A3DA1298-E1BB-42FB-B3D8-D361A0B2F4E4。
- 全量首次发现3项网络测试失败：capabilities/confirm切到长请求transport但丢失注入配置。APIClient的chat/stream配置复制已有sessionConfiguration，保留各自超时；原三项测试及全量回归全部通过。
- changed-file ruff通过；去除knowledge.py两处既有重复导入，复用文件原有集中导入。
- PCM manual及iOS matrix --check通过；新增比较能力未取得线上回执前明确partial，不伪造生产证据。
- git diff --check通过。
- 历史真实设备视觉验证见cleanup-diff-20260927-completion.md；旧Archive不包含本次Chat补丁，不用于本次交付。
