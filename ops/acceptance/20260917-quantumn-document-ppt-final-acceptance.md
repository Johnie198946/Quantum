---
title: Quantumn iOS 文档与 PPT 最终验收（Gate A–F）
date: 2026-09-17
tags:
  - quantumn
  - acceptance
  - ios
  - document-ppt
status: passed-local-awaiting-gate-g
---

# Quantumn iOS 文档 / PPT 最终验收（Gate A–F）

- 时间：2026-09-17 02:29 CST
- 仓库：`/Users/dengzhaoyu/Projects/ai-lab-platform-ios-document-ppt-final-20260912`
- HEAD：`ec5f9361630e5006510962688f71a8754f0c7985`
- 结论：**Gate A–F 全绿；具备申请 Gate G 授权的条件。**
- 发布结论：**NO-GO**。Gate G 尚未授权，未 commit、push、部署、Archive、上传 TestFlight 或真机发布验收。

## Gate 状态

| Gate | 结果 | 证据 |
|---|---:|---|
| A | PASS | Istanbul 1/1，0 failed，0 skipped |
| B | PASS | Word / Research Report / Academic Paper 共 3/3，0 failed，0 skipped |
| C | PASS | 隔离单测 5/5；重构后 live matrix 4 chat runs / 4 workflows，全隔离断言通过 |
| D | PASS | 单一统一 UI 结果 4/4；14 页 PPTX/PDF/蒙太奇；用户已明确目视确认“通过。后续专项优化” |
| E | PASS | Batch 6 重构；golden 340 → 346，0 行为回归；kill switch 与隔离回滚演练通过 |
| F | PASS | 干净 Build 40；Python 全量、iOS 单测与 11 项统一 UI 验收通过 |

## Gate E

结构边界：

- QWS API → `backend/services/qws_access.py`、`qws_session_context.py`
- Workflow API → `backend/services/workflow_reviews.py`
- Hermes bridge → `backend/services/workflow_document_contracts.py`
- Kill switch → `AI_LAB_BATCH6_EXECUTION_KILL_SWITCH`

验收：

- baseline：340 tests + 16 subtests，0 failed，0 skipped
- post-refactor：346 tests + 16 subtests，0 failed，0 skipped
- 新增 Batch 6 测试：6
- 重构模块相关循环依赖：0
- 重复抽取函数定义：0
- 回滚演练：模拟损坏后恢复，全部 hash 回读一致；源工作树未被演练改变
- 回滚收据：`/tmp/Quantumn-E-Batch6-Rollback-Rehearsal.json`

## Gate F

### Python 全量

- 2639 collected
- 2621 passed
- 0 failed
- 0 errors
- 18 skipped，均有明确原因：
  - 2 个旧 V1 场景已由 V2 测试替代
  - 14 个 installed catalog opt-in
  - 1 个私有本地 Vault opt-in
  - 1 个需真实 Hermes + Writer checkout
- JUnit：`/tmp/Quantumn-F-Python-Full.xml`

首次全量预检曾出现 4 个 research revision 失败。根因是测试默认命中了旧 `ai-lab-vault-deposition` pipeline，缺少 `revision_link`；权威代码真源 `ai-lab-vault-governance` 已实现该契约。固定 `RESEARCH_PIPELINE_MODULE` 指向权威真源后，定向 4/4 与全量 2621 passed 均通过。未以跳过、降级断言或伪造结果处理。

### iOS Build 40

- App：Quantumn `1.0.3 (40)`
- 模拟器：iPhone 17 Pro / iOS 26.1 / `1049CD2E-3EC0-463D-96F9-40DB7AFDE11A`
- DerivedData：`/tmp/QuantumnCloseoutBuild40`
- clean `build-for-testing`：exit 0
- iOS unit：209/209 passed，0 failed，0 skipped
- iOS UI：11/11 passed，0 failed，0 skipped；无 `Executed 0 tests`

11 项 UI 覆盖：

- Batch 4 新手 UX fixtures：6
- Word live product chain：1
- Research Report live product chain：1
- Academic Paper fail-closed live product chain：1
- Istanbul clean-room presentation live product chain：1
- Structured Review CAS conflict + relaunch persistence：1

结果包：

- `/tmp/Quantumn-F-iOS-Unit-Build40.xcresult`
- `/tmp/Quantumn-F-iOS-UI-Build40.xcresult`

Gate F Istanbul 最终预览仍显示 14 页（截图为 `2 / 14`）；未见明显空白、重叠、乱码或渲染破损。此项只作为自动回归佐证；正式视觉确认仍以用户已确认的 Gate D 14 页蒙太奇为准。

### 隔离与运行态

- 重构后 Gate C live matrix：4 个并发 Backend→Hermes sessions、4 workflows
- 无 foreign chat marker
- 跨 owner workflow 读取返回 404
- Backend：HTTP 200 / ok / v0.8.0
- Hermes bridge：HTTP 200 / ok / v6.0 / workflow orchestration enabled

### 安全与工作树

- JWT 文件权限：`0600`
- 变更文本密钥扫描：0 private key / AWS / GitHub / Slack / JWT / literal Bearer matches
- `git diff --check`：通过
- 工作树原有脏改动全部保留；当前 66 个变更路径
- 当前 HEAD 未变化；相对本地 `origin/main`：ahead 11 / behind 0

## Gate G 边界

尚未授权、尚未执行：

- commit main
- push GitHub
- 服务器部署
- Archive
- TestFlight 上传
- 真机发布验收

Gate G 必须另行取得明确授权，并在执行后分别回读 commit/remote SHA、服务器 revision、ASC build 与真机验收结果。
