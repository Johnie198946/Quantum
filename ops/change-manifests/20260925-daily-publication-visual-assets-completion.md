# 每日连载视觉资产门禁与 iOS 正文插图

- task_id: `20260925-daily-publication-visual-assets`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/quantum-2.0-publication-main`
- start/local HEAD: `873cc27e676915cc8a69adf48921479e512b24f8`
- remote SHA before work: `873cc27e676915cc8a69adf48921479e512b24f8`

## 盘点与变更

- 复用 `PublicationStore`、private evidence receipts、冻结 edition、订阅鉴权 API 与 iOS 同源图片读取；Hermes 仍是唯一 AI runtime。
- 四个每日系列在 stage 与发行前固定要求双封面及 `illustration_01..03` 三张插图；少图、多余角色或不连续角色均失败关闭，正文不接受公网图片作为每日插图。
- operator 的 stage / prepare-editorial / record-editorial-review 支持重复的绝对路径 `--illustration-file`；未新增上传服务或外部图床。
- catalog/reader 仅返回同源 `illustration_urls`，通用 media 读取复核 published、权限、receipt、哈希、格式和尺寸；旧 covers 端点保留。
- iOS 在正文 section 间顺序加载插图；单张图片失败不会阻断正文。no-agent completion 确定性检查四系列正文和五个媒体。
- editorial retry budget 按审核周期计算：只统计同一 issue 最新 `approved` revision 之后的 `failed/rejected`；无批准历史仍保留 4 次门禁和既有缺口闭环例外。

## 验证

- `python3 -m pytest -q tests/test_daily_publication.py tests/test_publication_editorial_workflow.py tests/test_publication_daily_completion.py tests/test_publication_release_remote.py tests/test_publication_reader_projection.py tests/test_follow_builders_public_bookshelf.py --tb=short`
  - 原 89 项集合连同新增回归共 `107 passed, 4 warnings in 46.64s`（warnings 为既有 Pydantic V2 class Config 弃用提示）。
- `python3 -m pytest -q tests/test_publication_editorial_remote.py --tb=short`
  - `29 passed, 4 warnings in 27.95s`；验证 prepare/review 不上传媒体，批准后的 stage 才上传五媒体并摄取 receipt。
- `PYTHONPATH=. python3 -m pytest -q tests/test_publication_editorial_workflow.py tests/test_daily_publication.py tests/test_publication_editorial_remote.py tests/test_publication_daily_completion.py tests/test_publication_release_remote.py tests/test_publication_reader_projection.py tests/test_follow_builders_public_bookshelf.py --tb=short`
  - `137 passed, 4 warnings in 100.18s`；新增回归覆盖批准前 4 次历史失败、批准并发布后的新周期、新周期连续 4 次失败、无批准历史门禁及跨 issue 隔离。
- `xcodebuild test -project ios/AIPlatformApp.xcodeproj -scheme AIPlatformApp -destination 'platform=iOS Simulator,id=E3C1B641-E8C3-482D-B154-066846D275F2' -only-testing:AIPlatformAppTests/WorkflowLifecycleDTOTests`
  - `141 tests, 0 failures`；`** TEST SUCCEEDED **`。
- 修改过的 Python 文件语法编译与 `git diff --check`: 通过。

## 交付与风险

- commit: 尚未创建；当前阶段先完成本地代码、资产和测试闭环。
- remote SHA: 未变更；尚未推送。
- server_before/server_after: 未读取；未部署。
- health_check/functional_check: 未执行线上检查。
- rollback_point: 无；本地未提交改动可按文件审查后撤销。
- remaining_risks: 未在真实生产 API、真实发行数据或实体 iOS 设备上验证；retry 周期语义已用合成 SQLite workflow 覆盖，尚未对生产数据库做只读抽样核验；模拟器测试日志含测试夹具既有 SQLite vnode 警告，但测试全部通过。
