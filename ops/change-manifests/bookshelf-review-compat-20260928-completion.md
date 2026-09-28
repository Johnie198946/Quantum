# 历史出版审核兼容修复

task_id: bookshelf-review-compat-20260928
status: TESTED
branch: codex/bookshelf-review-compat-20260928
worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/bookshelf-review-compat-20260928
head/local_commit: ecf5fd4881a157c6943ce7915db641f6d4dd58cc / 无新增commit
remote_sha: 未核验；未授权push
server_before: ecf5fd4881a157c6943ce7915db641f6d4dd58cc；release=/opt/releases/ai-lab-platform-ecf5fd4881a1.4UlLvx
server_after: 未执行部署，未改变服务器
health_check: 诊断阶段8容器healthy、/health与认证能力HTTP200；本修复尚未部署验证
functional_check: 本地153测试通过；线上29本已出版正文哈希在修复前全部完整，26本被新增审核字段拦截、3本可见；修复后线上验证未执行
rollback_point: 生产未变更，不适用；部署前需按仓库规则建立回滚点
remaining_risks: 尚未提交/推送/部署；线上仍使用旧代码；原服务器IO故障非本修复范围

## 复用与修改
复用PublicationStore._access_reasons → _editorial_check → validate_editorial。两个生产文件增加仅用于已发布读取的兼容参数：完整旧版五项章节审核可以继续读；出现任何新项即要求全部九项。兼容只由数据库published状态触发，并要求既有审核批准、冻结记录、签名绑定校验通过。新稿审核、暂存和发行继续严格九项；旧正文、签名、哈希、媒体、权限、撤回检查保留。不增加服务、依赖、数据库迁移，不修改历史正文或审核证明。

变更文件：backend/services/publication_editorial.py；backend/services/knowledge_publication_store.py；tests/test_publication_editorial.py；tests/test_publication_editorial_workflow.py；本manifest。

## 验证
- python3 -m pytest -q tests/test_publication_editorial.py tests/test_publication_editorial_workflow.py tests/test_daily_publication.py tests/test_publication_reader_projection.py：153 passed，4条既有Pydantic弃用警告，65.77秒。
- ruff check 四个Python变更文件：通过。
- git diff --check：通过。
- 测试模拟旧版真实签名合成审核先发布，再升级规则：旧书可读、待发布旧稿阻断；正文、审核收据、签名证明篡改后不可读；新审核缺项仍阻断。
- 首轮新测试误期望重复stage历史已发布记录变成blocked，发现现有实现明确保留published冻结状态后修正测试为published；生产实现未因该测试失败作调整。最终完整套件通过。

## 授权与隔离
用户授权修复，未明确授权push/部署。遵循用户直接提供的一任务一分支一worktree规则，优先于产品本地AGENTS的main-only规则。规范产品checkout存在大量他人修改，保持不变。App管理worktree工具固定当前AI Lab仓库，无法指定Quantum仓库，因此从实际服务器SHA在Quantum创建独立worktree；此前诊断worktree仅存报告，不作产品源码依据。
开工盘点：规范产品main=21250c7b8a5290abcf649b9279bbd91b9af1db88、落后本地origin/main25提交，存在他人修改；完整前置盘点见ios-server-diagnosis任务manifest。新worktree在编辑前status干净，HEAD=线上SHA，remote同Quantum仓库。

## 未执行验证与审批
试图通过SSH向独立生产Python进程传入修复源码并使用mode=ro数据库校验29本。自动审批拒绝：将未部署私有修复源码传入生产容器执行的授权不明确，存在本地测试或正式部署后验证替代方案。命令未执行，没有绕过拒绝。待明确生产发布授权后按GitHub先于服务器流程部署并验收。

## 当前Git盘点

```text
$ git status --short --branch
## codex/bookshelf-review-compat-20260928
 M backend/services/knowledge_publication_store.py
 M backend/services/publication_editorial.py
 M tests/test_publication_editorial.py
 M tests/test_publication_editorial_workflow.py
```

```text
$ git branch --show-current
codex/bookshelf-review-compat-20260928
```

```text
$ git rev-parse HEAD
ecf5fd4881a157c6943ce7915db641f6d4dd58cc
```

```text
$ git remote -v
origin	https://github.com/Johnie198946/Quantum.git (fetch)
origin	https://github.com/Johnie198946/Quantum.git (push)
source	https://github.com/Johnie198946/ai-lab-platform.git (fetch)
source	https://github.com/Johnie198946/ai-lab-platform.git (push)
```

```text
$ git worktree list --porcelain
worktree /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
HEAD 21250c7b8a5290abcf649b9279bbd91b9af1db88
branch refs/heads/main

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/bookshelf-review-compat-20260928
HEAD ecf5fd4881a157c6943ce7915db641f6d4dd58cc
branch refs/heads/codex/bookshelf-review-compat-20260928

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/image-studio-v4-20260927
HEAD 43fabf515e990a2b6aa1b0e8baa0891a0eaa021d
branch refs/heads/codex/image-studio-v4-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/jev-pcm-routing-20260927
HEAD ecf5fd4881a157c6943ce7915db641f6d4dd58cc
branch refs/heads/codex/jev-pcm-routing-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/knowledge-ui-refresh-20260927
HEAD ae11b9bd8e30c89269ea8c59da7cf239fac86920
branch refs/heads/codex/knowledge-ui-refresh-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/quantum-confirmation-fix-20260927
HEAD b9e4d128dd5839bae89cff39790fb8240297e23e
branch refs/heads/codex/quantum-confirmation-fix-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-notes-20260927
HEAD 370bd4c479e0f71fd7fed1c7743dc4291d73a7b5
branch refs/heads/codex/travel-notes-20260927

worktree /Users/dengzhaoyu/Documents/AI Lab/.worktrees/image-direct-processing-20260927
HEAD b9e4d128dd5839bae89cff39790fb8240297e23e
branch refs/heads/codex/image-direct-processing-20260927

worktree /Users/dengzhaoyu/Projects/publication-quality-20260928
HEAD 457abcd4284f5ab0910df1d138475894b963a782
branch refs/heads/feat/serial-narrative-quality-20260928

```

## 发布授权
用户明确授权提交、推送、部署。发布以实测线上ecf5fd48为基线，使用独立任务分支，不覆盖main上未部署的其他任务变更。复用现有update.sh精确SHA发布和部署锁。
