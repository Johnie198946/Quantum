# iOS 帮我清理与既有合并接管

task_id: ios-cleanup-and-merge-20260926
status: TESTED（仅既有合并；清理功能未完成）

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

## 验证（持续更新）

- Python compileall：通过。
- git diff --check：通过。
- Swift frontend parse（3 个冲突 Swift 文件）：通过。
- 产品能力、客户端笔记、出版远端审核与流程集成：140 passed。
- Bridge 锁、Capability Gateway、PCM 语义能力：43 passed；最终出版/学习/Bridge/JEV/Gateway 复验 204 passed。
- 正文图片绑定/隔离/篡改回归：3 passed。
- iOS 完整构建：BUILD SUCCEEDED（Debug，generic iOS Simulator，CODE_SIGNING_ALLOWED=NO）。
- 清理功能实施与验收：未完成。

## 交付字段

commit SHA: 未执行；既有 HEAD 见上。
GitHub remote/ref/SHA: origin/refs/heads/main；仅 fetch 观察值，未 push，未进行发布核验。
server_before: 不适用，未授权部署。
server_after: 未执行。
health_check: 未执行，未部署。
functional_check: 本地测试如上；端到端清理尚未完成。
rollback_point: 开工 HEAD/MERGE_HEAD 和临时备份；禁止 reset --hard 或覆盖其他任务改动。
remaining_risks: 合并尚未提交；后续远端提交尚未整合；清理三个领域完整实施、iOS 测试尚未完成。

## 变更文件

合并冲突的 10 个文件及相关 Hermes 运行时模块和回归测试。最终清单在完成后更新；不包含其他任务的 AGENTS.md 修改及既有未跟踪 manifest。
