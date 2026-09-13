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

- status: `VERIFIED`
- testflight_target: `1.0.3 (38)`；Build 37 已占用，不复用。
- commit_sha: `5bcb0dac4e89baf33df11ee7822ed9444d867bc9`。
- github_remote_ref_sha: `ai-lab-platform/main@5bcb0dac4e89baf33df11ee7822ed9444d867bc9` 与 `Quantum/main@5bcb0dac4e89baf33df11ee7822ed9444d867bc9`，均已用 `git ls-remote` 核验；后者是精确 SHA 部署器的下载源。
- server_before: 首次只读检查为 `/opt/releases/ai-lab-platform-0ec9b84a5242.PIKs1Y` / `0ec9b84a524288d076aac0e6831f671e14e8d883`；执行期间另一发布将生产推进到 `/opt/releases/ai-lab-platform-a9725bbc9e5a.x3WRsy` / `a9725bbc9e5ac7277982cf6ddd6a6291161dcf71`，本任务重新读回且确认无并发部署后才继续。
- server_after: `/opt/releases/ai-lab-platform-5bcb0dac4e89.fZdeXk`，`.deployed-sha=5bcb0dac4e89baf33df11ee7822ed9444d867bc9`；API 与三个 worker 的镜像 ID 均为 `sha256:8bdb61ad3aa4ca5e1fcfd82a264fb4be6d4a22d1d37220d85d321f8a182070eb`，revision 与目标 SHA 一致。
- health_check: 精确 SHA 部署器完成 additive migration、runtime contract audit、原子切换与最终检查；8/8 Compose 服务 running/healthy；API `/ready=ready/0.8.0`，Hermes Bridge `ok/v6.0`，公网 `t-react.com/health` 与 `www.t-react.com/health` 均为 `ok/0.8.0`。
- functional_check: 本地后端 `81 passed, 1 skipped`、iOS `161 passed`；运行容器的 `WorkflowCreate` 明确暴露 `general/presentation/document` 三种 `output_kind`，未认证创建请求返回 401（非 422）；Build 38 已安装到配对 iPhone，自动启动因设备锁定被 iOS 拒绝，待解锁后补启动验收。
- rollback_point: `/opt/ai-lab-shared/deployment-checkpoints/20260913-document-output-before-5bcb0da`，保存成功部署前 `a9725bbc9e5ac7277982cf6ddd6a6291161dcf71` release 与离线镜像证明；部署器回滚 release 为 `/opt/releases/ai-lab-platform-a9725bbc9e5a.x3WRsy`。

## TestFlight receipt

- Archive: `/private/tmp/Quantumn-1.0.3-38.xcarchive`，bundle `com.ailab.AIPlatformApp`，版本 `1.0.3 (38)`，签名严格校验通过。
- Archive binary SHA-256: `1148c24509976b826b1b223df7551ca5cf4176a588a8af204fea2407e35499c2`。
- App Store Connect: Xcode 返回 `Upload succeeded`、`Uploaded package is processing` 与 `EXPORT SUCCEEDED`；Apple 处理及测试组可见性仍需等待。

## Remaining risks / rollback

- 私有源文档生成上限已从 8,000 提升到 80,000 字符并禁止静默截断；更长文件仍需后续引入可核验的分块汇总协议，上传解析入库本身不受此生成限制。
- Chat 的显式输出识别采用受测试的保守关键词规则；未明确出现 PPT/PPTX/演示文稿或 Word/DOCX 的请求仍走普通 Hermes 对话。
- TestFlight Build 38 已被 Apple 接收但仍在 processing；尚未证明测试组可见，也尚未在解锁真机内完成业务账号的上传—解析—PPT/Word 全流程点击验收。
- 回滚：按上述 checkpoint 恢复离线镜像证明并重新部署 `a9725bbc9e5ac7277982cf6ddd6a6291161dcf71`；不得影响另一 worktree 的历史 build 36 任务。
