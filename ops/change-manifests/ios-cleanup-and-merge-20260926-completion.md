# iOS 帮我清理与既有合并接管

task_id: ios-cleanup-and-merge-20260926
status: COMMITTED（本地完成，未推送/部署；提交身份由 Git 记录核验）

## 目标与授权

用户授权“由你接手解决这次已有合并，再继续全部开发”。先整合既有冲突，再完成对话、笔记、待办的清理建议、筛选、确认与结果回执。仅复用/增强 PCM、现有 Hermes/JEV、领域存储和现有 iOS 设计，不建立第二条写入链。

## 开工盘点

- 规范目录：/Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
- branch: main（遵循本仓库 AGENTS.md；既有合并由用户明确授权接管）
- HEAD: 6aa8c072d052b9ddb3532a828be7c0e5f7a58fd6
- MERGE_HEAD: 9871743416f6e39d06a62d4057aaca5107c69161
- 初始 status: main ahead 105/behind 20；10 个 UU 文件，既有 staged 合并变更；AGENTS.md 未暂存修改与未跟踪 quantum-2.0-hermes-gate-i0-20260909-completion.md 均保留。
- fetch 后 origin/main: 00a847bbde1a288e053ee60880fe203daa0943b2（另有 23 个后续提交；尚未整合）
- 回滚取证备份：/private/tmp/cleanup-merge-20260926-baseline/（status、unmerged index、双向 diff、冲突工作文件）。

### Remote
```
origin	https://github.com/Johnie198946/Quantum.git (fetch)
origin	https://github.com/Johnie198946/Quantum.git (push)
source	https://github.com/Johnie198946/ai-lab-platform.git (fetch)
source	https://github.com/Johnie198946/ai-lab-platform.git (push)
```
### Worktree
```
worktree /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
HEAD 6aa8c072d052b9ddb3532a828be7c0e5f7a58fd6
branch refs/heads/main

```

## 合并处理

- 出版：保留角色插图与已校验正文图；未经绑定的公网图片仍拒绝。补齐视觉审阅素材绑定和两边测试 fixture 的兼容。
- 阅读器：保留阅读定位、批注、正文块，同时显示新角色插图；API 同源白名单覆盖 covers/media/assets。
- Hermes：保留运行时模块化及唯一 JEV 语义路由，将本地 PCM 原生工具、受控提案、owner session 和 Skill CRUD 迁入既有模块；不恢复关键词语义路由。
- 会话测试隔离映射文件；旧协议只保留读取兼容，新写入走现有知识动作/PCM。

## 清理功能交付

- 三个部分一并实现：真实数据建议/四类筛选；逐项确认、合并差异与批量执行；恢复、版本冲突、幂等、回执恢复与账号隔离。
- 对话复用 ChatHistoryStore 生命周期与 PCM client action，新增 conversation.lifecycle 契约及现有 SQLite 内动作幂等表；不删除消息。动作账号必须同时匹配笔记授权命名空间与对话存储命名空间。
- 笔记复用 knowledge.note.*、签名 knowledge-action ledger 与 KnowledgeActionExecutor；受限本地快照避免远端旧内容覆盖设备内容。来源归档可单独恢复，不自动回退合并目标。
- 待办复用 task.list 查重、现有合并预览/撤销、project change proposal/确认与 CAS。task.update 扩展同项目批量组织操作；原归档路由共用实现。DONE 归档保留完成状态，其余恢复时还原原状态。
- 客户端确认响应丢失时读取现有 proposal status/result，不重复执行；最终 Gateway 集成测试验证真实落库及回执序列化。
- 沿用 PaperCard/首页插画/筛选条；无独立清理服务、无新依赖。Hermes/JEV 保留唯一自然语言语义路由，明确按钮意图直接使用 PCM。
- PCM 新能力与三个升级契约未部署，生产回执标记 unverified/coverage partial；旧版本回执移至 previous_production_receipt 保留历史，未伪造新版证据。

## 验证

合并阶段：
- Python compileall、git diff --check、Swift parse：通过。
- 产品能力/客户端笔记/出版流程：140 passed。
- 出版/学习/Bridge/JEV/Gateway：204 passed（含本地 loopback 测试）。
- iOS Debug generic simulator 完整构建：BUILD SUCCEEDED。

清理阶段：
- 初始能力/PCM/客户端动作/矩阵：54 passed。
- 领域、任务操作循环、PCM 语义、Gateway 与产品契约：71 passed。
- QWS API、客户端笔记、知识动作权限、清理能力与矩阵扩展回归：125 passed。
- 最终完整 PCM 提案→确认→落库→幂等回放→归档恢复→合并撤销→列表回读，以及项目任务契约：18 passed。
- 最终生成矩阵/产品能力：35 passed；两份生成脚本 --check 与 git diff --check 通过。
- iOS WorkflowLifecycleDTOTests + KnowledgeNoteStoreTests：185 passed，0 failures；包含 SQLite 批量原子性、版本冲突、重复回放及已消费令牌回执恢复。
- 最后补充对话存储账号一致性 guard 后，重新编译及 2 项清理专用回归：TEST SUCCEEDED。
- 独立测试模拟器：Cleanup-Acceptance-20260927 / A3DA1298-E1BB-42FB-B3D8-D361A0B2F4E4；未使用其他模拟器数据。
- 本机预装 FastAPI/Starlette 低于 requirements.txt，首次 TestClient 回归无法初始化。使用 /private/tmp/cleanup-test-asgi 下 FastAPI 0.115.14、Starlette 0.46.2（系统证书验证下载）后复验通过；未修改全局或项目依赖。

日志：/private/tmp/cleanup-final-backend.log、cleanup-pcm-roundtrip.log、cleanup-domain-tests.log、cleanup-catalog-final.log、cleanup-ios-final-tests.log、cleanup-ios-scope-tests.log、cleanup-feature-ios.log。

## 交付字段

branch: main
worktree: /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
merge_commit: 53052df094b31275f083f3bddccb6a8c55201c96
feature_commit: 本文件所在提交；执行 git log -1 --format=%H -- ops/change-manifests/ios-cleanup-and-merge-20260926-completion.md 核验（避免自引用 SHA）。最终对话另记录实际 SHA。
remote_sha: origin/main 仅 fetch 观察值 00a847bbde1a288e053ee60880fe203daa0943b2；本次未授权/未执行 push，未作发布 ls-remote 核验。
server_before: 不适用，未授权部署。
server_after: 不适用，未部署。
health_check: 不适用，未部署服务器。
functional_check: 上述本地自动测试通过；未进行生产账号或真机验收。
rollback_point: 合并前 HEAD 6aa8c072d052b9ddb3532a828be7c0e5f7a58fd6 与基线备份；功能前 HEAD 为 merge_commit。需要回退时使用审阅后的逆向提交，不覆盖其他工作；新增本地收据表无破坏性迁移。
remaining_risks: origin/main 仍有 23 个既有 MERGE_HEAD 之后的提交未整合；仓库禁止擅自进行额外分叉合并。没有 push/deploy 授权，线上仍不是本次版本。生产功能与真机视觉验收未执行。每次最多 32 项、前 20 项目/100 有效任务/50 对候选、单笔记 20,000 字符的上限已在界面说明；自然语言偏好沿现有会话处理，不新增独立偏好存储。

## 变更文件

既有合并的文件见 merge_commit。本次功能提交如下；排除其他任务的 AGENTS.md 修改及 quantum-2.0-hermes-gate-i0-20260909-completion.md。

- `backend/api/capabilities.py`
- `backend/api/knowledge_actions.py`
- `backend/api/quantum_workspace.py`
- `backend/capability_handlers.py`
- `backend/contracts/product-capabilities/bindings.yaml`
- `backend/contracts/product-capabilities/client_actions.yaml`
- `backend/contracts/product-capabilities/ios-scope.yaml`
- `backend/contracts/product-capabilities/project_task.yaml`
- `backend/services/capability_catalog.py`
- `backend/services/capability_gateway.py`
- `backend/services/client_actions.py`
- `backend/services/knowledge_action_capability.py`
- `docs/product-capability-coverage.json`
- `docs/product-capability-manual.md`
- `docs/product-specs/capability-gateway.md`
- `ios/AIPlatformApp/Models/UIModels.swift`
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformApp/Services/ChatHistoryStore.swift`
- `ios/AIPlatformApp/Views/Chat/Components/ChatMessageStreamView.swift`
- `ios/AIPlatformApp/Views/Chat/NativeClientActionHost.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
- `ops/acceptance/ios-capability-matrix.json`
- `ops/acceptance/pcm-ios-coverage.yaml`
- `ops/change-manifests/ios-cleanup-and-merge-20260926-completion.md`
- `scripts/hermes_bridge_runtime/knowledge.py`
- `tests/test_cleanup_capabilities.py`
- `tests/test_ios_capability_matrix.py`
- `tests/test_product_capabilities.py`
