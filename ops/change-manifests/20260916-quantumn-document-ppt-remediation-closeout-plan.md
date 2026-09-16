---
title: Quantumn 文档与 PPT 修复计划收口执行方案
date: 2026-09-16
status: approved-scope-pending-execution
parent_plan: ops/change-manifests/20260915-quantumn-document-ppt-product-remediation-plan.md
current_gate: NO-GO
branch: main
---

# Quantumn 文档与 PPT 修复计划收口执行方案

## 一、执行结论

不再以伊斯坦布尔单链通过替代完整方案验收。执行按依赖顺序一次性收口：先补齐本地缺失的 iOS 产品 E2E 和隔离矩阵，再完成 Batch 6，最后进入需要外部写入授权的 GitHub、服务器、TestFlight 与回滚验收。

在全部门禁关闭前，总状态保持 `NO-GO / PARTIAL`。

## 二、已知基线

- Build：Quantumn `1.0.3 (40)`。
- 伊斯坦布尔 Build 40 模拟器主链：`1 passed / 0 failed / 0 skipped`。
- iOS 单测：`209 passed / 0 failed / 0 skipped`。
- Structured Review 本地真实 Backend UI E2E：`1 passed / 0 failed / 0 skipped`。
- Batch 4 离线 UI：`6 passed / 0 failed / 0 skipped`。
- Word/研究报告/论文：后端确定性测试 `3 passed`，但没有 iOS 模拟器产品 E2E。
- Batch 3：单元/后端隔离测试存在，完整双账号双会话 UI/生产矩阵缺失。
- Batch 6：未开始。
- Git：`main` 比 `origin/main` ahead 11，工作树有未提交修改；未 push、未部署、未上传 TestFlight。

## 三、执行顺序

### Gate A：验收真源纠偏

1. 保留两个状态层：
   - `istanbul_user_input_subtask`：已通过本地 Build 40 模拟器主链。
   - `full_remediation_plan`：`NO-GO / PARTIAL`。
2. 所有 completion、acceptance matrix、coverage 和最终通报统一引用完整方案状态。
3. 旧 Build 38、失败/跳过/中断 `.xcresult` 不进入最终门禁。

**退出条件：**所有验收文件不再用子任务 8/8 通过外推完整方案完成。

### Gate B：Batch 5 三条 iOS 模拟器真实产品链

分别新增并执行三个 clean-room UI E2E：

1. Word：iOS 发起 → Backend → Hermes → planning/execution Worker → 多页 DOCX → Structured Review 修改两处 → 保存 → 重新下载 → 页数、文本、版本、SHA-256 一致。
2. 研究报告：至少三个可访问且独立的来源 → iOS 发起 → 真实产品链生成 → 引用逐条对应 → 修改一处 → 重新下载 → 引用、版本、SHA-256 验证。
3. 学术论文：摘要、正文、参考文献与文内引用对应 → 未核实来源 fail closed → iOS 修改/保存/重新下载 → 结构、引用、版本和 SHA-256 验证。

每条必须使用独立 owner/session/generation，不得直接调用测试 fixture 投影最终 Hermes 事件来冒充真实链路。

**退出条件：**三份独立 `.xcresult` 均为目标测试实际执行、`0 failures`、`0 skipped`、`xcodebuild exit 0`；三个最终文件与下载回执可回读；`pcm-ios-coverage.yaml` 三项由 `partial` 更新为有真实证据的状态。

### Gate C：Batch 3 完整隔离矩阵

在真实本地 Backend/Hermes/Worker 与模拟器上执行：

- 两个账号 × 每账号两个会话；
- 四个任务并发；
- A/B 会话快速切换；
- 退出登录、重新登录；
- 杀 App、冷启动恢复；
- 注入网络延迟，让旧响应晚于新响应；
- 混入缺少可信 session provenance 的 legacy workflow；
- 分别检查聊天、activity、deep link、artifact、review 和下载列表。

发现失败后必须读取 `.xcresult`、UI hierarchy、SQLite、Backend/Hermes/Worker 日志，修复、clean build、重跑；不得只记录失败。

**退出条件：**任何页面都没有其他 owner/session 数据；迟到响应被拒绝且有审计；legacy 项只进入历史隔离区；整套矩阵 `0 failures / 0 skipped`。

### Gate D：Batch 1/2/4 最终回归与用户确认

1. 用完成 Gate B/C 后的同一 Build 40 clean 构建重跑：
   - 伊斯坦布尔完整原文主链；
   - Structured Review CAS/412/重启持久化；
   - 小屏、键盘、底栏、失败重试与 Agent 描述；
   - PPTX/PDF 下载。
2. 程序化检查最终 PPTX/PDF 页数、文本、图片、地图、SVG、来源 trace、审批、owner/session/generation 与哈希。
3. 渲染全页 montage，提交最新版成品给用户最终视觉确认；旧版确认不自动覆盖新 revision。

**退出条件：**目标测试全部 `0 failures / 0 skipped`，最新版 PPTX/PDF 通过用户确认。

### Gate E：Batch 6 结构拆分

仅在 Gate B–D 全绿后执行：

- 拆分 `quantum_workspace.py` 的路由、状态机和 session mapping；
- 拆分 `hermes_bridge.py` 的 presentation/document prompt、结构验证和 transport；
- 拆分 `workflows.py` 的 API DTO、review、scope 和 artifact projection；
- 不复制状态机、不新增第二 Runtime、不改变 PCM Registry 真源。

先冻结行为 golden，再逐步移动纯函数；每一步运行目标回归和完整回归。

**退出条件：**行为 golden 前后一致、无循环依赖、无双状态机、无重复 Prompt 真源，回滚演练成功。

### Gate F：最终测试包

- Python 完整回归：失败为 0；所有 skip 逐项消除或形成明确、批准且不属于本计划门禁的排除说明，不能把 skipped 当 passed。
- iOS 单测：同一 clean Build 40，`0 failures / 0 skipped`。
- iOS UI：伊斯坦布尔、Structured Review、Batch 4、Batch 5 三文档、Batch 3 隔离矩阵全部使用同一 Build 40 测试产物。
- 回读 App、UITest Runner、`.xctestrun`、安装包与产物版本；临时 JWT 和 `.xctestrun` 权限保持 `0600`，凭据不进入仓库。
- 生成统一 completion manifest、session matrix、artifact manifest、测试汇总和回滚报告。

### Gate G：外部发布链（需单独授权）

本地全部门禁通过后，才请求并执行外部写入：

1. 显式暂存本任务文件并提交 `main`；
2. 获得 push 授权后推送 GitHub，核验本地 HEAD 与远端 SHA；
3. 获得部署授权后建立服务器回滚点，以同一远端 SHA 部署并回读服务版本、健康和功能；
4. 获得 TestFlight 授权后新 Archive Build 40、上传、回读 ASC、安装真机；
5. 真机执行关键主链与下载验收；
6. 执行并回读回滚演练。

**退出条件：**GitHub SHA、服务器 before/after、TestFlight Build 40、真机结果和回滚点全部一致且可回读。

## 四、失败处理规则

- `Executed 0 tests`、任何 skip、exit 65、设备锁屏、SIGKILL、超时、中断或不完整 `.xcresult` 均不算通过。
- 单测通过不替代 UI E2E；Backend E2E 不替代 iOS 产品链；artifact 生成不替代下载；HTTP 200 不替代内容验收；用户确认不替代自动化门禁。
- 每次失败都必须定位根因、修复并从受影响的最早门禁重跑。
- 若修复引入跨模块行为变化，则回退到最近可验证 SHA/工作树快照，不带故障进入下一 Gate。

## 五、最终完成定义

只有 Gate A–G 全部关闭，才将完整方案改为 `GO / VERIFIED`。在未取得外部写入授权时，最高状态只能是 `LOCAL_TESTED`，不能表述为已上线。
