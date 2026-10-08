# Gemini 审核空跑优化

task_id: gemini-review-gate-20261008
status: TESTED（相关110个测试通过；全仓lint有已验证基线失败，全仓 lint 已清理通过）
branch: codex/gemini-review-gate-20261008
worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/gemini-review-gate-20261008
head/local_commit: 1f7985edc78731dbcf200fa6ff994897eb15ceeb / 未提交
remote_sha: 未授权 push；未执行 ls-remote
server_before: 未连接服务器；本地 Hermes 当前引用 publication-releases/a5ffbfdcbdf7d6abb37bf7d3b1d6ba9d05e52daa
server_after: 未部署；运行脚本保持原版本
health_check: 未执行线上检查；无需网络的已安装 Hermes wake-gate 自检通过
functional_check: 110 passed, 4 warnings in 383.17s；已安装 Hermes wake-gate 三项断言通过；未调用真实模型或发布稿件
rollback_point: 本地修复仅为独立 worktree 中的未提交差异；线上激活前须备份精确运行脚本并记录 SHA-256
manifest: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/gemini-review-gate-20261008/ops/change-manifests/gemini-review-gate-20261008-completion.md
remaining_risks: 修复尚未在运行环境生效；全局 Gemini fallback 保留；真实审核仍有成本；仓库整体 ruff 有14个基线错误。

## 需求判定和范围
既有 review_input 已实现候选筛选、已审核稿去重、profile 隔离、精确材料重试预算。缺少空队列 wakeAgent=false 标志，导致每10分钟空队列仍启动模型。复用 Hermes 原有 _parse_wake_gate，不另建状态或调度层。
变更文件：scripts/publication_editorial_remote.py、tests/test_publication_editorial_remote.py、本 manifest。
业务代码仅变更一行返回值；普通审核和 supervision 共用入口，均受益。新增两种 profile 空队列回归断言，更新四个现有空队列断言。
保留无效待审稿报错、正常候选请求、真实视觉检查、作者/审核者身份隔离及原生签名门禁。保持10分钟轻量检查，不降低真实审核及时性。

## 已验证消耗证据
2026-10-08 至排查时，supervision cron 111 个会话的预运行输出明确是 no_await_review，累计909次请求、8,939,587输入token、34,045输出token；其余18个会话累计307次请求、2,186,459输入token、39,637输出token。来源为只读 supervision/state.db 中 sessions 和第一条user消息；后一组标为有请求或未知，未武断认定全部是真实审核。
现有全局预脚本输出 no_await_review 不含 wakeAgent，Hermes _parse_wake_gate 默认 True。实测新输出返回 False，真实请求输出返回 True。

## 验证
- 变更文件 ruff：通过。
- git diff --check：通过。
- 已安装 Hermes 调度器原函数隔离执行：旧输出唤醒、新空队列输出跳过、真实请求唤醒，三项断言通过。
- 仓库要求的 ruff check backend/ scripts/ tests/：失败，14个基线错误；逐文件与 HEAD 字节一致（agent_config.py:3、endpoints.py:4、session_runtime.py:4、image_studio_server.py:3）。未修改无关文件。
- /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 -m pytest -q tests/test_publication_editorial_remote.py tests/test_publication_review_input.py：110 passed, 4 warnings in 383.17s（Pydantic既有弃用告警）。
- 未运行全仓 pytest、生产定时验收、模型调用或部署。

## 激活边界与回滚
当前工作完成的是可审查的代码补丁；Hermes wrapper 仍指向原发布目录。用户本任务未明确授权 push 或生产部署，不改冻结发布目录、不重启 cron、不停用审核、不替换模型。
后续授权激活应使用既有交付流程，核对远端 SHA、运行版本、备份和空队列跳过日志；不得把本地测试通过当作用量已下降。

## Git 盘点
规范源码主目录：main，HEAD 21250c7b8a5290abcf649b9279bbd91b9af1db88，behind49，含其他任务多处已修改/未跟踪文件，全部保留。
本任务基于开工时本地 origin/main=1f7985edc78731dbcf200fa6ff994897eb15ceeb；未声称这是实时远端SHA。
用户在当前会话提供的一任务一分支/Worktree规则优先于仓库内旧main-only规则。
隔离目录编辑前干净。以下盘点在写 manifest 前捕获；源码和测试文件的 M 属于本任务。

```text
git status --short --branch
## codex/gemini-review-gate-20261008...origin/main
 M scripts/publication_editorial_remote.py
 M tests/test_publication_editorial_remote.py
```

```text
git branch --show-current
codex/gemini-review-gate-20261008
```

```text
git rev-parse HEAD
1f7985edc78731dbcf200fa6ff994897eb15ceeb
```

```text
git remote -v
origin	https://github.com/Johnie198946/Quantum.git (fetch)
origin	https://github.com/Johnie198946/Quantum.git (push)
source	https://github.com/Johnie198946/ai-lab-platform.git (fetch)
source	https://github.com/Johnie198946/ai-lab-platform.git (push)
```

```text
git worktree list --porcelain
worktree /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
HEAD 21250c7b8a5290abcf649b9279bbd91b9af1db88
branch refs/heads/main

worktree /private/tmp/quantum-ryg-audit-fc1b2f8
HEAD fc1b2f88c4a4e0c1d0a393e2e58eb62b92626114
detached
prunable gitdir file points to non-existent location

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/bookshelf-review-compat-20260928
HEAD 9e393b76b0bb01cb69827567a94ee5c403233afa
branch refs/heads/codex/bookshelf-review-compat-20260928

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/chat-media-refresh-20260928
HEAD 9e393b76b0bb01cb69827567a94ee5c403233afa
branch refs/heads/codex/chat-media-refresh-20260928

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/gemini-review-gate-20261008
HEAD 1f7985edc78731dbcf200fa6ff994897eb15ceeb
branch refs/heads/codex/gemini-review-gate-20261008

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/image-studio-refresh-20260928
HEAD 9e393b76b0bb01cb69827567a94ee5c403233afa
branch refs/heads/codex/image-studio-refresh-20260928

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/image-studio-v4-20260927
HEAD 43fabf515e990a2b6aa1b0e8baa0891a0eaa021d
branch refs/heads/codex/image-studio-v4-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/ios-travel-pages-20261007
HEAD 0ab83f67bc89501f91d989444414d21796ca95a3
branch refs/heads/codex/ios-travel-pages-20261007

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/jev-pcm-routing-20260927
HEAD ecf5fd4881a157c6943ce7915db641f6d4dd58cc
branch refs/heads/codex/jev-pcm-routing-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/keyboard-dismiss-20260928
HEAD 9e393b76b0bb01cb69827567a94ee5c403233afa
branch refs/heads/codex/keyboard-dismiss-20260928

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/knowledge-ui-refresh-20260927
HEAD ae11b9bd8e30c89269ea8c59da7cf239fac86920
branch refs/heads/codex/knowledge-ui-refresh-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/quantum-confirmation-fix-20260927
HEAD b9e4d128dd5839bae89cff39790fb8240297e23e
branch refs/heads/codex/quantum-confirmation-fix-20260927

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-actions-20261008
HEAD 1f7985edc78731dbcf200fa6ff994897eb15ceeb
branch refs/heads/codex/travel-actions-20261008

worktree /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-context-fix-20260928
HEAD fc1b2f88c4a4e0c1d0a393e2e58eb62b92626114
branch refs/heads/codex/travel-context-fix-20260928

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

## 授权后交付
用户于当前任务明确授权提交、推送并更新 Hermes 运行版本。
- 从 origin/main fast-forward 到 669fba1c；新变更仅包含修复、回归测试及发布检查清理。
- 清理四个文件的重复导入/夹具格式；73个桥接相关测试通过（4.63s），全仓 ruff 通过。
- 本地旧发布目录与最新源码的审核客户端仅相差本次测试过的一行门禁，版本间其他差异仅在 iOS 与验收文档；不部署远程服务器。
