---
title: Quantumn 文档与 PPT 产品修复计划完整验收审计
date: 2026-09-16
status: superseded-by-20260917-final-acceptance
scope: full-remediation-plan
---

# Quantumn 文档与 PPT 产品修复计划完整验收审计

> [!success] 后续状态更新
> 本文保留 2026-09-16 当时的审计快照。Gate A–F 已于 2026-09-17 全绿，最新真值见 `20260917-quantumn-document-ppt-final-acceptance.json` 与 `20260917-quantumn-document-ppt-final-acceptance.md`。Gate G 仍未授权，发布继续 NO-GO。

## 事实

审计对象是 `ops/change-manifests/20260915-quantumn-document-ppt-product-remediation-plan.md` 的完整范围，而不是仅限伊斯坦布尔 PPT 子任务。方案第 326–327 行规定：只有全部门禁通过，并把基于用户原文生成的新 PPTX/PDF 交给用户人工确认，才能宣布完成。方案还包含 Batch 0–6、生产隔离矩阵、Word/研究报告/论文三条真实 E2E、GitHub/服务器/TestFlight 对照以及回滚演练。

当前可回读证据如下：

1. **伊斯坦布尔主链**：`/tmp/IstanbulUserInputSimulatorBuild40-signed-final-r12.xcresult` 为 iPhone 17 Pro / iOS 26.1 模拟器，实际只执行 `testCleanRoomIstanbulPresentationCompletesEveryGateAndDownloadsPPTX()` 一项，结果 `1 passed / 0 failed / 0 skipped`。该链使用 Quantumn 1.0.3 Build 40，最终工作流完成并生成 16 页 PPTX/PDF。
2. **iOS 单元测试**：`/tmp/AIPlatformAppTests-build40-signed-final.xcresult` 为 `209 passed / 0 failed / 0 skipped`。其中能识别出结构化审核相关测试 4 项、owner/session/generation 等隔离相关测试 31 项；没有 Word、ResearchReport、AcademicPaper 命名的 iOS 测试项。
3. **Batch 2**：`/tmp/StructuredReviewLocalE2E.xcresult` 可回读，结果 `1 passed / 0 failed / 0 skipped`，覆盖真实本地 Backend 的 CAS 冲突、HTTP 412、重载和 App 重启持久化。
4. **Batch 4**：`/tmp/AIPlatformAppUITests-fixtures.xcresult` 可回读，结果 `6 passed / 0 failed / 0 skipped`；截图目录存在。它是离线 fixture UI 验收，不是生产/TestFlight 观察。
5. **Batch 5**：本次现场重跑 `tests/e2e/test_word_workflow.py`、`test_research_report_workflow.py`、`test_academic_paper_workflow.py`，结果 `3 passed / 0 failed`。但 `tests/e2e/conftest.py` 明确表明它们直接调用本地 PCM handler、人工投影捕获的 Hermes 输出事件，并使用 `provider=test-fixture`；没有启动 iOS App，也没有通过真实 Hermes 非确定性生成或生产服务器。因此它们是后端确定性 E2E，不是 iOS 模拟器产品 E2E。
6. **视觉包**：静态伊斯坦布尔验收包为 12 页，含 8 个图片对象、7 个不同图片、6 个可编辑矢量图标、9 个可编辑地图地标，视觉门禁无错误。它支持 Batch 1 的静态素材/结构要求，但不能替代最新版 16 页 live deck 的用户最终确认。
7. **未交付状态**：当前 Git 为 `main...origin/main [ahead 11]` 且工作树有大量未提交文件；completion manifest 明确记录未 push、未部署、未上传 TestFlight。`pcm-ios-coverage.yaml` 将 Word、研究报告、论文三项均标为 `partial`，生产收据为 `unverified`。主 completion 记录仍是 `status: in-progress`、发布门禁 `NO-GO`，并写明 Batch 6 尚未启动。
8. **缺失验收物**：没有完整生产双账号×双会话×四任务并发矩阵，没有生产退出/重登、冷启动、迟到响应与 legacy 混入回执；没有服务器 before/after、远端 SHA 对照、TestFlight Build 40 回读、数据库迁移与回滚演练；没有 Batch 6 行为 golden/拆分/回滚完成证据。

Apple 对 XCTest/Xcode 测试结果的公开说明仅用于界定 `.xcresult` 是测试执行证据，而不是生产部署、TestFlight 或业务人工验收的替代物：https://developer.apple.com/documentation/xctest 。本审计的产品结论以仓库计划、completion 文件、可回读 `.xcresult`、本地测试和 Git 状态为准。

## 分析

按完整计划逐批判断：Batch 0 的基线、原文 fixture 和主要失败测试已落地，可视为本地完成；Batch 1 的内容保真、来源追踪、地图、摄影、SVG、PPTX/PDF 和 Build 40 伊斯坦布尔模拟器主链已通过，但最新版 r12 没有独立的用户最终视觉确认，因此是“本地实现通过、最终人工门禁未闭合”；Batch 2 的本地真实 Backend 模拟器 E2E 已通过，但未进入发布链；Batch 3 只有后端矩阵和模拟器单元级隔离证据，完整生产矩阵未执行；Batch 4 有 6 项离线模拟器 UI 测试，但生产/TestFlight 观察未执行；Batch 5 三项后端确定性 E2E 通过，但三项 iOS 行为仍被官方覆盖矩阵标为 partial，且没有 iOS 模拟器端从创建、编辑到下载的三条产品链；Batch 6 按计划未启动。

因此，“所有要求都完成”和“所有要求都做过模拟器测试”均不成立。现有 `20260916-quantumn-document-ppt-acceptance-matrix.json` 的 8/8 通过只覆盖伊斯坦布尔子任务与研究入库，不能外推为完整 remediation plan 通过。最强反例是：即使伊斯坦布尔 E2E、结构化审核和 Batch 4 UI 全绿，Batch 5 仍明确为 partial、Batch 6 未启动、生产矩阵和发布/回滚链缺失；这些都是原计划的完成定义，而不是可选项。

## 启示

应把验收状态拆成两层：

- `istanbul_user_input_subtask`：本地实现与 Build 40 模拟器主链通过，研究体已保存并排队，但 Writer 编译另行记录。
- `full_remediation_plan`：维持 `NO-GO / PARTIAL`，直到生产隔离矩阵、三条文档 iOS 模拟器/真实产品链、最新版 PPT 用户确认、Batch 6、GitHub/服务器/TestFlight 对照和回滚演练全部有可回读收据。

后续不得再用“209 个 iOS 单测全部通过”替代“所有功能都做过模拟器端到端测试”；也不得用后端 deterministic E2E、workflow completed、HTTP 200 或 artifact 可打开替代 iOS 产品链、生产回执和人工视觉确认。当前审计停止于可决定结论的本地证据：缺口均由计划原文、completion 状态、coverage matrix、`.xcresult` 和 Git 状态直接界定，无需联网扩展事实。
