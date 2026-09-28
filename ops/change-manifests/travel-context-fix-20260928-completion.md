# Travel chat and workflow context fix

task_id: travel-context-fix-20260928
status: TESTED
branch: codex/travel-context-fix-20260928
worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/travel-context-fix-20260928
head/local_commit: baseline 43fabf515e990a2b6aa1b0e8baa0891a0eaa021d; fast-forwarded to 9e393b76b0bb01cb69827567a94ee5c403233afa; task commit pending
remote_sha: origin/main verified at 9e393b76b0bb01cb69827567a94ee5c403233afa before integration; task push pending
server_before: /opt/ai-lab-platform/.deployed-sha = 9e393b76b0bb01cb69827567a94ee5c403233afa; release /opt/releases/ai-lab-platform-9e393b76b0bb.48oi45
server_after: pending deployment
health_check: preflight hermes-bridge/health status=ok, bridge and chat worker active; final check pending
functional_check: backend targeted 219 passed plus JEV routing contract 8 passed; iOS WorkflowLifecycleDTOTests 198 passed and targeted edit confirmation test 1 passed; final verification pending
rollback_point: preflight release above; production backup and image attestations pending deployment
manifest: ops/change-manifests/travel-context-fix-20260928-completion.md
remaining_risks: User's particular historical timeout source cannot be proved without the production request log; TestFlight delivery pending.

## Objective and changes

The existing JEV/PCM/QCP/travel-workflow chain remains the execution path. The travel confirmation card now shows proposal data and explicit missing fields, accepts edits, and obtains a new QCP proposal instead of confirming the old token. Confirmed structured details are prepended to the existing workflow description and saved in its requirements snapshot. The authenticated chat route reads only the latest workflow bound to the same tenant, owner, and client session. JEV sees the opening user turn and five recent turns within a fixed budget for long sessions. The authorized knowledge gateway receives one bounded retry on timeout; repeat timeout is attributed to that dependency in the existing workflow failure record. No new router, service, dependency or parallel workflow was added.

Files: agency/hermes-plugins/ai-lab-capabilities/capability_router.py; backend/api/chat.py; backend/capability_handlers.py; backend/contracts/product-capabilities/capabilities.yaml; backend/services/workflow_session_scope.py; scripts/hermes_bridge_runtime/workflow_runtime.py; iOS UIModels.swift, ChatStatusCards.swift, TenantSessionCoordinator.swift, BlockCardDispatcher.swift, PluginRenderContext.swift, MessageBubbleView.swift, project.yml and project.pbxproj; existing tests/test_product_capabilities.py, tests/test_travel_plan.py, tests/test_pcm_jev_routing_contract.py, WorkflowLifecycleDTOTests.swift; generated PCM manual, coverage and iOS matrix; this manifest.

## Inventory and isolation

Quantum canonical repo /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0 was main at 21250c7b8a5290abcf649b9279bbd91b9af1db88, behind origin/main by 25 and carrying unrelated tracked/untracked edits. Its remote origin is https://github.com/Johnie198946/Quantum.git and source is https://github.com/Johnie198946/ai-lab-platform.git. `git worktree list --porcelain` showed active bookshelf, image-studio, JEV, knowledge, confirmation, travel-notes and other task worktrees; none was reused or modified. The managed worktree tool targets AI Lab, so Quantum's isolated worktree was created with `git worktree add -b codex/travel-context-fix-20260928 ... origin/main`. New worktree inventory: clean status, branch codex/travel-context-fix-20260928, HEAD 43fabf515e990a2b6aa1b0e8baa0891a0eaa021d, same origin/source remotes, listed as its own worktree. GitHub main subsequently advanced to 9e393b76; the two new publication commits touch no task files, and this worktree fast-forwarded to that SHA.

## Validation and delivery gates

- `/private/tmp/quantum-image-venv/bin/python -m pytest tests/test_chat_stream_api.py tests/test_workflows_api.py tests/test_travel_plan.py tests/test_product_capabilities.py tests/test_capability_gateway.py tests/test_pcm_semantic_capabilities.py tests/test_jev_selector.py tests/test_pcm_jev_routing_contract.py -q --disable-warnings --maxfail=1`: 203 passed. This required local loopback bind; sandbox run had 179 passed then local port PermissionError, and rerun with local port permission passed. After fast-forward, related publication tests were added: 219 passed. The final JEV opening-turn preservation change passed 8 focused routing tests.
- iOS `xcodebuild test` for WorkflowLifecycleDTOTests on a separate iPhone 17 Pro simulator: 198 passed. The new edit test is in ClarifyAnswerPaginationRegressionTests; a first targeted run selected the wrong class and executed zero tests. The corrected targeted run executed 1 test with 0 failures.
- Ruff on touched Python and `git diff --check`: passed after final code changes.
- `generate_product_capability_manual.py` and `generate_ios_capability_matrix.py` regenerated PCM artifacts; both check modes passed.
- No real user request or production logs read. Prior automatic approval review rejected export of journal/container logs as they may contain sensitive request data. This release authorization does not imply authorization to export those logs.
- Commit/push/deploy not yet executed as of this manifest version. User explicitly authorized push and deployment in this task. Server cutover must preserve a rollback point and verify exact GitHub SHA and functions.
