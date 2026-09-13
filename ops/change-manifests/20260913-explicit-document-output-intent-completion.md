# Completion Manifest

- task_id: `20260913-explicit-document-output-intent`
- goal: 拆分“上传解析入库”和“显式生成文档”两条路径；PPT 不依赖上传或 Wiki；扩充 Word/DOCX 的澄清、生成、预览、确认、下载与系统分享闭环。
- changed_files:
  - `backend/api/workflows.py`
  - `backend/services/presentation_scenario.py`
  - `backend/services/document_sources.py`
  - `backend/services/workflow_planner.py`
  - `scripts/hermes_bridge.py`
  - `ios/AIPlatformApp/Networking/APIClient.swift`
  - `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
  - `ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift`
  - `ios/AIPlatformAppTests/KnowledgeNoteStoreTests.swift`
  - `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
  - `tests/test_document_presentation.py`
  - `tests/test_workflows_api.py`
  - `ios/project.yml`
  - `ios/AIPlatformApp.xcodeproj/project.pbxproj`

## Start inventory

- status: clean `main...origin/main`
- branch: `main`
- HEAD: `bc791e55c543473f139bc2778744c144bf5347bf`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/quantum-document-output-intent-20260913`
- other worktree preserved: `/private/tmp/quantum-document-ppt-e2e-20260913` on `codex/build36-device-acceptance-fixes`

## Architecture reuse

- Reused the existing `POST /api/v1/workflows` lifecycle, clarification sessions, planning worker, Hermes DAG runtime, approval gates, artifact storage, real PPTX/DOCX renderers, authenticated preview/download, and iOS system `ShareLink`.
- Added one explicit `output_kind` discriminator; `source_document_id` is now optional material and no longer selects the PPT scenario.
- Upload continues through the existing document receipt, private note, knowledge compilation, preview card, and compilation monitor only.
- Explicit PPT/DOCX plans use an empty Wiki scope by default; without a source file they begin with topic research based on the user's instruction.

## Verification

- `PYTHONPATH=. pytest -q tests/test_document_presentation.py tests/test_workflows_api.py tests/test_workflow_artifact_reading.py`: **81 passed, 1 skipped**.
- `xcodebuild ... test -only-testing:AIPlatformAppTests/WorkflowLifecycleDTOTests -only-testing:AIPlatformAppTests/KnowledgeNoteStoreTests`: **161 passed, 0 failures**.
- `xcodebuild ... -sdk iphonesimulator ... build`: **BUILD SUCCEEDED**.
- `git diff --check`: **passed**.

## Delivery status

- status: `TESTED`（用户已授权提交、推送、部署及 TestFlight 上传，交付执行中）
- testflight_target: `1.0.3 (38)`；Build 37 已占用，不复用。
- commit_sha: 待创建。
- github_remote_ref_sha: 待推送并用 `git ls-remote` 核验。
- server_before: `/opt/releases/ai-lab-platform-0ec9b84a5242.PIKs1Y`，`.deployed-sha=0ec9b84a524288d076aac0e6831f671e14e8d883`；API `/ready` 正常；Hermes Bridge 与 chat worker active，gateway/serve inactive，Bridge `127.0.0.1:9118` 不监听（部署前既有状态）。
- server_after: 未部署。
- health_check: 未执行远端健康检查。
- functional_check: 本地 API/规划/产物测试与 iOS 构建、单测通过；尚未在已部署服务和真机上验收本次新增逻辑。
- rollback_point: 生产 `/opt/releases/ai-lab-platform-0ec9b84a5242.PIKs1Y` / `0ec9b84a524288d076aac0e6831f671e14e8d883`；任务起始 GitHub main 为 `bc791e55c543473f139bc2778744c144bf5347bf`。

## Remaining risks / rollback

- 私有源文档生成上限已从 8,000 提升到 80,000 字符并禁止静默截断；更长文件仍需后续引入可核验的分块汇总协议，上传解析入库本身不受此生成限制。
- Chat 的显式输出识别采用受测试的保守关键词规则；未明确出现 PPT/PPTX/演示文稿或 Word/DOCX 的请求仍走普通 Hermes 对话。
- 回滚：在未提交状态下可按本 manifest 的 changed_files 逐一恢复到 rollback point；不得影响另一 worktree 的 build 36 任务。
