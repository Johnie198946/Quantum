# Bookshelf functionality

task_id: bookshelf-functionality-20260927
status: TESTED

目标：真实阅读筛选、个人书单、目录主题、系统刊物订阅、单层返回和加载优化。
复用：现有订阅 API、SQLAlchemy、SwiftUI 书架；不增加服务或状态库。

## 开工盘点
```
$ pwd -P
/Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0

$ git status --short --branch
## main...origin/main
 M AGENTS.md
 M backend/capability_handlers.py
 M backend/contracts/product-capabilities/capabilities.yaml
 M backend/services/user_note_context.py
 M ops/change-manifests/chat-cleanup-client-compat-20260927-completion.md
 M ops/change-manifests/chat-cleanup-pcm-20260927-completion.md
 M ops/change-manifests/cleanup-exercise-testflight-20260927-completion.md
 M ops/change-manifests/note-audit-recovery-20260927-completion.md
 M ops/change-manifests/note-organization-v2-20260927-completion.md
 M ops/change-manifests/quantum-note-save-consent-20260927-completion.md
 M ops/change-manifests/quantum-notes-release-20260927-completion.md
 M ops/change-manifests/reader-experience-release-20260927-completion.md
 M scripts/hermes_bridge_runtime/knowledge.py
 M tests/test_cleanup_capabilities.py
 M tests/test_user_note_context.py
?? ops/acceptance/receipts/
?? ops/change-manifests/cleanup-diff-20260927-completion.md
?? ops/change-manifests/quantum-2.0-hermes-gate-i0-20260909-completion.md

$ git branch --show-current
main

$ git rev-parse HEAD
b696d13bdcef18cc23b1707dc00501ca012ee224

$ git remote -v
origin	https://github.com/Johnie198946/Quantum.git (fetch)
origin	https://github.com/Johnie198946/Quantum.git (push)
source	https://github.com/Johnie198946/ai-lab-platform.git (fetch)
source	https://github.com/Johnie198946/ai-lab-platform.git (push)

$ git worktree list --porcelain
worktree /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
HEAD b696d13bdcef18cc23b1707dc00501ca012ee224
branch refs/heads/main

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-notes-20260927
HEAD c1c5788c7a94a25f8f4cb6ed81c50614b4feeba1
branch refs/heads/codex/travel-notes-20260927

```

其他 dirty 文件属于笔记并行任务或先前交付记录，不纳入本任务。双方已协调源码范围与后续发布窗口。

server_before: b696d13bdcef18cc23b1707dc00501ca012ee224（上一任务验证；本轮部署前重新核验）
server_after: 未执行
health_check: 未执行
functional_check: 待测试
rollback_point: 本轮未建立
remote_sha: 878744d9d3a2164a39409557b2de53617c279043
remaining_risks: 尚未完成实现和验收

## 实现与复用
- backend/api/subscriptions.py：复用现有 GET knowledge-bookshelves，include_reader=true 同次目录返回账号订阅（包含已读历史期次）与个人书单；PUT/DELETE me/book-lists/{UUID}，有效书籍检查、租户/用户复合隔离。
- backend/models/tenant.py：KnowledgeBookList 使用现有数据库和 create_all 启动门禁，新增表为书单持久化必要数据，无新增服务或状态库。
- backend/services/knowledge_publication_store.py：published 可选 content_kind SQL 过滤，来源索引读取不再校验无关刊物；所有命中的内容仍通过完整 _access_reasons。
- iOS：现有 APIClient DTO/API、SubscriptionCenterView、KnowledgeView 主路径；去掉假在读/空已读回填、静态主题、假书单；增加书单编辑/选书/删除和系统刊物订阅入口；正文单层显示，返回不等待网络，进度沿用 onDisappear flush。
- 笔记去重：与 ac78d723 Store 的本次认证快照返回配合，内容哈希及生命周期一致不再上传，取消时停止遍历。
- Build 70：仅版本号，不包含并行图片任务的 Mantis / media 改动。

## 定位与验证证据
- Build69 先前真机复现：笔记→中间书架→管理书架→详情→正文多层返回；书架加载出现超时/499。
- 代码证据：原来新建书单只设置 showsAllBooks；固定主题枚举+关键词猜测；已读空列表回填 recent；订阅/目录/备用接口串行；每次恢复笔记后全量上传，try? 吞取消。
- 生产独立只读诊断：25 本公开目录三次 4.724/4.524/5.054 秒；候选 SQL 过滤诊断 2.903/2.156/1.751 秒。诊断进程未修改运行服务，不能替代部署后测量。
- 后端第一轮 99 passed，加公开来源6 passed；有界读取执行器34 passed（干净候选）。
- iOS 联合 Store + WorkflowLifecycleDTO 单元测试 213 passed；首次书架三项 UI 通过，随后长正文目录/书籍信息+新书架两项共3 UI 通过。
- 最终干净候选快照：/private/tmp/bookshelf-functionality-20260927/Candidate；来自 HEAD 9d1e2f02 + 审查后的 candidate.patch，排除同目录未完成图片任务。终轮仍在进行，结果后续追加。
- 证据目录：/private/tmp/bookshelf-functionality-20260927；本地截图/测试产物不提交仓库。

## 发布协调
- notes ac78d723865cb93d7fb30f7fc8b82914e18f889e 已独立提交。
- watchdog 74c23c 已审查并 cherry-pick 为 9d1e2f02670fc00a10c26638260e7876aee351c8，保留 Python 子进程解释器修复。
- publication 任务掌管 cron 暂停/自然清空/重 pin，尚未交出服务器窗口。
- 本轮服务器只读核对 server_before=b696d13bdcef18cc23b1707dc00501ca012ee224，磁盘18G可用。

## 最终干净候选验收
- clean-backend.log：105 passed。
- read-scaling.log：34 passed。
- clean-check.log：书单 wire contract 1 passed，空筛选/真实书单编辑/大字号书架入口/单次返回中3项 UI passed，TEST SUCCEEDED。
- ui-navigation-final.log：长正文目录/书籍信息与两个书架交互共3项 UI passed。
- 共享工作区最后一次编译因并行 media 未完成类型失败；未修改或混入该任务，干净候选重新构建通过。

## GitHub 与不可变归档
- branch: main
- worktree: /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
- local_commit: 878744d9d3a2164a39409557b2de53617c279043
- remote: https://github.com/Johnie198946/Quantum.git
- ref: refs/heads/main
- git push origin main: b696d13b..878744d9 main -> main
- git ls-remote origin refs/heads/main: 878744d9d3a2164a39409557b2de53617c279043 refs/heads/main
- 归档 SHA256: dd892888071034498ccc558b81b4b47dce50c88cbe5d339207049cf2df38ffd3
- 产品提交文件与干净候选逐字节对比 passed；并行图片任务的依赖与源码仍留在未提交工作区，未包含。
- server_after: 尚未切换，等待出版素材自然完成及窗口确认。
- Build70: 已交联合客户端任务从该SHA干净归档；安装/真机验收未完成。

## 书单草稿边界补查
书单编辑页原先关闭sheet后打开书籍，会离开未保存编辑上下文。改为同一sheet内部切换既有ReaderView，返回恢复同一草稿；新增UI回归，尚待本轮结果。878候选安装/上传已暂停，服务端未切换。

书单草稿回归：draft-final.log TEST SUCCEEDED；阅读前输入 Keep my draft，关闭书籍后名称仍保留。最终补丁仅Reader复用及一项UI测试。
