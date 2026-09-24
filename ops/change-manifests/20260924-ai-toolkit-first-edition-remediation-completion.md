# 首期《AI 工具实战》整改与双封面接入 — 完成清单

- task_id: `20260924-ai-toolkit-first-edition-remediation`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/quantum-2.0-publication-main`
- base/local_head: `b6d40a7990a5a2c668c08afe3a356bb5e8a44661`
- remote_sha: `b6d40a7990a5a2c668c08afe3a356bb5e8a44661`（本轮按用户已核验结果记录；未 fetch）

## 盘点与复用

- 复用唯一 `PublicationStore → subscriptions API → iOS KnowledgeView/reader` 主链；Hermes 仍是唯一 Runtime。
- 复用 `evidence` ingest receipt、SHA-256、发布/withdraw/权限门禁和现有 iOS API base URL/JWT 请求合同。
- 没有新增服务、数据库表、发行链、依赖或 Markdown 图片权限。
- 生产旧版仍为 `publication-9b5b298fb96bd44dfccb04c36fad8134`；本任务没有读取或改变生产状态。

## 本地变更

- 出版 `assets` 合同新增严格 `shelf_cover` / `reader_cover` 角色；分别只接受 1440×2560 和 2560×1440 的真实 PNG/JPEG。
- 新 `ai-toolkit` edition 缺任一角色即进入 blocked；迁移前已发布、没有封面的历史 edition 继续可读。
- 封面由现有 evidence receipt 保存和逐次哈希/格式/尺寸验证；新增认证后的只读角色端点，不暴露私有路径。
- 书架投影 `shelf_cover_url`，正文投影 `reader_cover_url`；均为严格相对 API 路径。
- operator 新增 `--shelf-cover-file` / `--reader-cover-file`，公开 bundle 只保留 receipt 与受控元数据。
- iOS DTO 字段可选；书架和概述页优先真实 9:16 封面，失败保留程序化封面；正文标题下显示 16:9 hero，失败或无图时收起；请求复用 JWT，带加载态与 VoiceOver 标签。
- 整改正文、审计、编辑提示和双封面原始资产保留在 `ops/drafts` / `ops/audits`；图片 SHA-256 与 `image-manifest.json` 一致。

## 校验

- `PYTHONPATH=. python3 -m pytest -q tests/test_daily_publication.py tests/test_publication_reader_projection.py tests/test_publication_editorial_workflow.py tests/test_subscription_api.py tests/test_book_subscriptions.py`：`66 passed`。
- `python3 -m ruff check ...`（本任务 Python 实现与测试文件）：通过。
- `xcodebuild ... -sdk iphonesimulator ... build`：`BUILD SUCCEEDED`。
- Swift DTO/reader/认证图片相对 URL 定向测试：`4 passed`。
- 最终 9:16 画框调整后 `xcrun swiftc -frontend -parse`：通过；随后 simulator/device rebuild 均因 CoreSimulatorService 崩溃停在 Asset Catalog，非 Swift 编译错误。
- `git diff --check`：通过。

## Hermes 生产发行步骤（未执行）

1. 由独立 Hermes writer 基于 `revision-5/body.md` 和既有来源/rights 材料构建 editorial-v2 候选，不把仓库或 intake 本地路径写入 bundle。
2. 由独立 Hermes reviewer 对正文、来源、权利、图片 manifest 和两张封面字节复核并签署 exact-byte review/proof。
3. 在已部署并核验的 GitHub SHA 上，将正文、来源、rights、review/proof 与两张封面放入服务器私有 intake。
4. 调用现有 operator `stage`，同时传 `--shelf-cover-file` 与 `--reader-cover-file`；确认 edition 为 scheduled 且两个 receipt 哈希匹配。
5. 到期后由现有 deterministic `release-due` 发行；回读书架、正文、两个认证图片端点、Chat/订阅，并记录 server SHA、健康检查和回滚点。

## 状态字段

```text
task_id: 20260924-ai-toolkit-first-edition-remediation
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/quantum-2.0-publication-main
head/local_commit: b6d40a7990a5a2c668c08afe3a356bb5e8a44661 (no task commit)
remote_sha: b6d40a7990a5a2c668c08afe3a356bb5e8a44661 (user-verified; no fetch)
server_before: not changed
server_after: not changed
health_check: not applicable; no deployment
functional_check: local Python, Swift DTO and iOS simulator build checks passed
rollback_point: not applicable; no external write
manifest: ops/change-manifests/20260924-ai-toolkit-first-edition-remediation-completion.md
remaining_risks: production Hermes review/stage/release and authenticated device UI readback remain unexecuted; production old edition remains published; final post-layout Xcode rebuild awaits CoreSimulatorService recovery (prior build and 4 targeted tests passed)
```
