# Gemini 审核空跑优化完成记录

task_id: gemini-review-gate-20261008
status: VERIFIED（本地 Hermes 两个审核入口；不涉及远程服务器部署）
branch: codex/gemini-review-gate-20261008
worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/gemini-review-gate-20261008
head/local_commit: f098218bd7d37a6c5fb986523cab0c50ccb411f9（功能修复提交；最终验收文档另行提交）
remote_sha: f098218bd7d37a6c5fb986523cab0c50ccb411f9
remote/ref: https://github.com/Johnie198946/Quantum.git / refs/heads/main
GitHub evidence: git ls-remote origin refs/heads/main => f098218bd7d37a6c5fb986523cab0c50ccb411f9 refs/heads/main（部署前核验；后续文档提交不改变功能版本）
server_before: 本地 Hermes publication-releases/a5ffbfdcbdf7d6abb37bf7d3b1d6ba9d05e52daa
server_after: 本地 Hermes publication-releases/f098218bd7d37a6c5fb986523cab0c50ccb411f9；.deployed-sha 与已核验的 GitHub 功能 commit 一致
health_check: 两个 wrapper 的 SHA-256、两个 job 的 workdir、运行版本 .deployed-sha 全部核对通过
functional_check: default 与 supervision 实际预检查均返回 no_await_review/wakeAgent=false；已安装 Hermes run_job 原生路径均成功且抑制投递；模型构造调用数=0（验收中用断言禁止模型构造，避免付费用量）
rollback_point: /Users/dengzhaoyu/.hermes/rollback/gemini-review-gate-20261008
manifest: ops/change-manifests/gemini-review-gate-20261008-completion.md
remaining_risks: 真正有待审稿时仍有模型用量；全局 Gemini fallback 保留。supervision 自然调度记录截至21:10、next_run_at仍21:20，未把手动原生路径验收冒充自然定时触发；未重启或擅自恢复整个profile调度。未执行全仓pytest或远程服务器部署。

## 变更与复用
- 复用 review_input 的待审候选筛选、profile隔离、已审核稿去重及精确材料重试预算；复用 Hermes 的既有 wakeAgent 门禁。
- scripts/publication_editorial_remote.py：一行增加 wakeAgent=false，无稿时不启动模型。保留10分钟轻量检查和真实审核质量门禁。
- tests/test_publication_editorial_remote.py：补充 default/supervision 空队列测试、更新四个现有空队列断言；正常候选及无效待审稿失败路径由既有测试覆盖。
- scripts/hermes_bridge_runtime/{agent_config,endpoints,session_runtime}.py：删除重复导入，以通过仓库发布静态检查；保留已有导入和别名。
- tests/fixtures/image_studio_server.py：拆分导入/语句，不改变认证和路由行为。
- ops/change-manifests/gemini-review-gate-20261008-completion.md：验收和交付记录。

## 证据
2026-10-08排查时，supervision审核任务111次空队列调度消耗909次请求、8,939,587输入token（该任务当天输入约80%）。来源为只读supervision/state.db的sessions及第一条user消息；其余18会话有请求或未知，不武断认定全部真实审核。
当前运行发布与修复前最新源码的publication_editorial_remote.py字节一致；新客户端仅相差wakeAgent一行。a5ffbfd..669fba1版本间其他差异仅在iOS与验收文档。

## 验证
- 审核入口两个测试文件：110 passed, 4 warnings in 383.17s。
- 删除重复导入后的桥接相关测试：73 passed, 8 warnings in 4.63s。
- 全仓 ruff check backend/ scripts/ tests/：通过。原14个基线错误已清理。
- git diff --check：通过。
- 实际安装版本 _parse_wake_gate：旧空队列输出唤醒、新空队列输出跳过、真实审核请求唤醒，断言通过。
- 两个已切换的真实wrapper：返回码0，wakeAgent=false。
- 原生run_job：成功、SILENT_MARKER、无错误、模型构造0次；没有调用模型、发消息、审核或发行稿件。

## 授权与运行更新
用户在当前任务明确授权提交、推送并更新Hermes运行版本。仅更新default/fbd1cd1217d7和supervision/0dd3884f173c审核入口的wrapper与job workdir；schedule/model/provider/snapshot/enabled/script逐项比对不变。
新运行目录从已推送并核验的精确Git commit导出；保留仓库唯一tools软链接。首次安全解压拒绝绝对软链接时未切换入口，随后核验链接并重新导出。旧版本及首次失败的staging保留，未删除用户文件。
不部署远程应用服务器，不更新其他作者/素材/发行/controller入口，不替换模型，不重启gateway。
回滚：按receipt.json记录恢复wrapper-0.py、wrapper-1.py；用Hermes cron.jobs.update_job在use_cron_store对应profile下只恢复workdir_before（保留后续运行计数和任务状态，不覆盖整份jobs.json）。旧目录保持可用。

## 实际运行验收收据

```json
{
  "commit": "f098218bd7d37a6c5fb986523cab0c50ccb411f9",
  "health_check": {
    "release_sha": "f098218bd7d37a6c5fb986523cab0c50ccb411f9",
    "wrappers_match": true,
    "jobs_match": true
  },
  "functional_check": [
    {
      "job_id": "fbd1cd1217d7",
      "wrapper_returncode": 0,
      "wake_agent": false,
      "release": "/Users/dengzhaoyu/.hermes/publication-releases/f098218bd7d37a6c5fb986523cab0c50ccb411f9",
      "empty_queue": true,
      "native_scheduler_success": true,
      "model_constructions": 0,
      "delivery_suppressed": true
    },
    {
      "job_id": "0dd3884f173c",
      "wrapper_returncode": 0,
      "wake_agent": false,
      "release": "/Users/dengzhaoyu/.hermes/publication-releases/f098218bd7d37a6c5fb986523cab0c50ccb411f9",
      "empty_queue": true,
      "native_scheduler_success": true,
      "model_constructions": 0,
      "delivery_suppressed": true
    }
  ],
  "verified_at": "2026-10-08T23:17:31.471713+08:00",
  "entries": [
    {
      "job_id": "fbd1cd1217d7",
      "wrapper": "/Users/dengzhaoyu/.hermes/scripts/publication_review_input.py",
      "wrapper_sha256_before": "61f7c84a17a7ddd7781878cab8ef3e79be0c10c07fabb94e19e64c067eb6242c",
      "wrapper_sha256_after": "4d48c77e7b735f5a7a103701de9ae52b4b468407ac5c7f492ec33e6f8597c56a"
    },
    {
      "job_id": "0dd3884f173c",
      "wrapper": "/Users/dengzhaoyu/.hermes/profiles/supervision/scripts/publication_review_input.py",
      "wrapper_sha256_before": "1850a91990b5e05997974aee8caf1872b17484b8fbabffbd84b2a662e9066398",
      "wrapper_sha256_after": "3393135df4d3ea4c096c15a8f4ce9a4e035b3be6399e44773777c9135169dc3c"
    }
  ]
}
```

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
