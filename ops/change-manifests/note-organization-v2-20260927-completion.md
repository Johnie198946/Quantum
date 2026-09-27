# 笔记整理与知识消费增强

task_id: note-organization-v2-20260927
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
head/local_commit: 7414b4e77303ee2aee217a57200806be97ce8ef2（集成基线，待提交）
remote_sha: b07e2cc4fd6c0bcd299990ec58d474761134e577，git ls-remote origin refs/heads/main 已核验
server_before: 7414b4e77303ee2aee217a57200806be97ce8ef2，SSH读取.deployed-sha独立核验
server_after: 本轮未部署
health_check: 本轮未执行服务器检查
functional_check: 首批本地56项后端、34项iOS单元、2项UI通过；九项整体与真机尚未验收
rollback_point: 本轮未部署，不适用；本地改动保留为可审查 diff
remaining_risks: 真机与线上语义质量/端到端延迟尚未验收；本轮未部署、未上传Build67。历史进展以下续作记录为准。

## 目标与既有架构

用户明确要求九项新方案开始实施，并已有最终推送部署授权。三个部分一起验收：数据正确性（合并、归档、废纸篓、Wiki依赖）；整理质量及性能；Chat CRUD/知识消费/门禁简化。沿用 KnowledgeNoteStore、KnowledgeActionExecutor、PCM/Gateway、既有 JEV 路由和 contribution 编译流水线，不新增独立服务或状态库。

## 开工盘点

规范路径 pwd -P 已确认；main/HEAD/唯一 worktree 如上。origin=https://github.com/Johnie198946/Quantum.git，source=https://github.com/Johnie198946/ai-lab-platform.git，发布目标 origin/main。fetch/ls-remote 核验相同 b07e2cc4。开工存在 AGENTS.md 和 chat-cleanup-client-compat/chat-cleanup-pcm/cleanup-exercise-testflight/quantum-notes-release 四份 manifest 未提交修改，以及 receipts、cleanup-diff、hermes-gate manifest 未跟踪；均不混入本任务提交。AGENTS.md 双方规范保留已获用户授权并在前任务完成。

## 已启动的代码改动

- CleanupMergeReviewView：明示保留及归档对象，可交换方向，预览哈希与最终提案绑定所选方向。
- ChatMessageStreamView：先显示已生成的本地笔记/对话建议；待办返回后追加，避免替换正在审阅的候选。
- TenantSessionCoordinator：历史 note_draft 合并改为正式 PCM 签名提案；保留已有目标 ID，来源只由共享执行器在服务端核验后归档，删除旧的直接归档循环。单个既有候选加草稿内容走原有 update 能力。

## 验证

iOS 回归日志：/private/tmp/note-organization-v2-ios-escalated.log。首次沙箱运行无法连接 CoreSimulator；授权扩展权限后重跑。结果待补记。

## 未完成清单

- 合并链全面故障恢复/历史草稿迁移回归及用户选择验收。
- 全量增量体检、四类关系、章节插入和多篇关联候选。
- 性能分段计时与基准；Chat全量批量操作。
- 云端废纸篓查询恢复；归档可追溯、链接定位/重定向。
- Wiki来源撤回回归、知识消费证据、门禁流程简化。
- 集成测试、真机验收、明确文件提交、远端核验、回滚点及部署。

## 首批实现与验证进展

- 历史合并输入的新增回归已验证：保留已有目标ID；单候选走update；多候选走merge；更新草稿使用权威完整正文；错误目标、自归档、正文版本漂移均拒绝。34项iOS单元回归通过（/private/tmp/note-organization-v2-ios-regression.log）。
- knowledge.note.search 增强为1.1.0，新增 mode=organize 和 offset，复用 owner snapshot。共享 user_note_context 返回完整正文重复组、相同段落组、同标题候选和显式引用；组保留全部成员，支持分页，归档排除。明确 semantic_scan_complete=false，不把字面检测冒充语义完成。代码内容保持大小写与缩进差异，不按相同代码处理。
- iOS整理页已改为消费同一PCM结果；移除原本同名分组prefix(2)主路径。只使用与云端hash一致的本地笔记；展示云端检查范围及本机未同步限制。局部重叠与引用只读比较，不进入合并确认单。
- 56项后端测试通过（/private/tmp/note-organization-v2-backend-regression.log）；Ruff、PCM手册与iOS矩阵生成一致性、diff --check通过。
- 合成1000篇笔记本机纯候选计算33.2ms、201组，首屏100组。仅证明本地算法表现，不是用户8秒/23秒端到端延迟改善证据。
- 正在执行34项单元及2项界面集成回归（/private/tmp/note-organization-v2-ios-integration.log）。
- 并行笔记任务独立提交f7e6fa9c88fb5896ed37eb37bfa1a8cdb40dd072修复阅读自动保存；本任务未暂存其文件，后续包应包含。

本批仍未提交、推送或部署。九项统一交付剩余清单保持有效；尤其语义互补/相关判断、章节插入、跨设备废纸篓、批量CRUD、Wiki依赖/消费/门禁均不能声称完成。

## 首批集成结果

最终 `/private/tmp/note-organization-v2-ios-integration.log` 明确 TEST SUCCEEDED：34项iOS单元、2项UI全部通过；后端56项通过，静态和生成物检查通过。本批最高状态 TESTED，仅适用于已改动内容；全部九项并未完成，也未提交/推送/部署。当前共享基线随并行任务前进到 f7e6fa9c88fb5896ed37eb37bfa1a8cdb40dd072，本任务保持所有非本任务改动。

## 完整交付继续执行

2026-09-27续作：已fetch并fast-forward至c1c5788c，保留原未提交变更与AGENTS。新增云端回收站查询/显式恢复、阻止后台PUT复活删除笔记、生命周期时间戳、客户端回收站同步。验证进行中；整体状态LOCAL_ONLY。最终App必须包括f7e6fa9c笔记保存授权修复及全部九项验收。

## 后续实现与证据（仍在开发，未整体交付）

- 回收站：复用knowledge_sync的`.trash`，支持include_trashed查询与显式restore；后台PUT不再复活归档/删除笔记。私人恢复不重新授权已撤回平台贡献。客户端跨设备恢复、轻扫/详情统一账号删除；删除失败保留原稿。
- PCM：注册已有move_to_trash为knowledge.note.trash，复用签名确认、CAS、幂等记录；更新restore说明。Chat organize不再错误转换为关键词查询，新增catalog分页供Hermes完整读取。
- 合并：H2章节对齐，确认前可编辑全文/位置；保留回滚副本直到同步完成，以create_only补齐未同步原稿；合并来源双链沿merged_into定位保留笔记，云端生命周期元数据持久恢复。
- 消费：修复云端检索命中被旧本机缓存挤出前10条；云端目录发现的笔记可沿既有PCM读全文并加入已验证工作区。
- 门禁：当前测试明确已删除旧回答强制门禁。纠正文档旧描述及客户端未知状态误报“审核完成”，保留Gateway授权/撤回检查。知识无需等待Wiki编译才可作为私人上下文。
- 已验证：65项后端生命周期/PCM/整理；63项Chat/生命周期；92项Chat/PCM综合；23项现有无门禁与工具可用性。对应日志note-organization-v2-combined-tests/chat-tests/deep-tests/gates-tests。中间iOS生命周期与基线同步回归TEST SUCCEEDED，最新双链及入口回归进行中。后续改动仍需最终复跑，不可累计宣称全部验收。
- 未完成：批量全部删除的冻结范围与恢复；语义整理实际覆盖与真机质量验收；性能端到端测量；Wiki撤回重试/引用回归；归档阅读体验；最终集成测试、发布与TestFlight。未推送、未部署本轮改造。


## 集成交付候选（2026-09-27 12:22）

最新盘点：main，HEAD/origin main均7414b4e77303ee2aee217a57200806be97ce8ef2；fetch及ls-remote独立核对。规范工作区/remote如上；另有travel-notes-20260927历史worktree，不使用、不修改。全部无关AGENTS/manifest/receipts变更保留且不暂存。

九项实现对应：
1. 既有原子merge保留目标ID，源归档；H2章节对齐、逐项差异选择、全文位置可编辑。同步重试绑定本地结果hash，保护后续编辑。
2. 全量owner快照正文/段落/标题/显式链接索引，完整分组与分页；不再仅取同名两篇。
3. 快速检查明确字面证据边界；深度整理复用Hermes、PCM catalog/read/compare及签名修改提案，要求四类关系、全文证据与未读范围。没有新增语义服务；真实笔记效果仍需真机验证。
4. 快速候选与任务查询并行，本机建议先显示；报告网络分页耗时。合成1000篇33.2ms只是算法基准，不代表8秒/23秒用户耗时已解决。
5. Chat复用既有CRUD，trash注册同一执行器；批量删除冻结最多1000篇的精确版本，增量笔记不进入旧确认范围，失败保留原范围可重提案。手动删除走云端CAS，失败不删本地。
6. 云端既有.archive/.trash与本机目录同步，归档/回收站可阅读恢复；禁止普通PUT复活已删除或已归档数据。
7. 复用contribution撤回/重编译与merge outbox，撤回失败保持pending而不伪报完成；旧标题双链沿merged_into指向保留笔记。JEV沿用既有路由职责，不加第二条编译/授权链。
8. 修复检索命中被旧缓存挤出；目录发现的云端笔记可经既有PCM读取全文进入已验证上下文。
9. 核验旧强制回答门禁已经移除；修正文档与未知审核状态展示，保留Gateway权限/撤回/确认门禁；私人笔记无需等待Wiki编译。

验证：223项后端通过（/private/tmp/note-organization-v2-final-backend.log）；全量281项iOS单元+2项差异UI先前通过，最新变更38项相关iOS回归通过（/private/tmp/note-organization-v2-retry-ios.log）。Ruff、PCM手册和iOS矩阵生成一致性、git diff --check通过。真机自动化因手机锁定等待中；Release Build67编译进行中。

App集成包含f7e6fa9c笔记保存授权修复与7414出版修复。待完成：真机只读实际整理/消费/延迟检查、隔离fixture CRUD；Git提交推送、配套后端部署及回滚记录；Build67上传与处理状态。不得将TESTED表述为完整交付。
