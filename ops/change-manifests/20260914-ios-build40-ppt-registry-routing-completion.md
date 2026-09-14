# Quantumn iOS Build 40 PPT Registry routing repair

```text
task_id: 20260914-ios-build40-ppt-registry-routing
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-ios-document-ppt-final-20260912
head/local_commit: pending
remote_sha: pending
server_before: 3444d3b08b1bedb674ca91deaef7ea97bf74522c
server_after: pending
health_check: pending deployment
functional_check: local backend/iOS gates passed; production iOS E2E pending deployment
rollback_point: /opt/releases/ai-lab-platform-3444d3b08b1b.Fup8VU
manifest: ops/change-manifests/20260914-ios-build40-ppt-registry-routing-completion.md
remaining_risks: original Build 40 archive is an iPhoneOS binary and cannot contain this source fix; final validation must use a newly built iOS App, without representing a Simulator build as the archive binary.
```

## Scope and behavior

- Added Registry capability `presentation.create_from_text@1.0.0` with governed input schema, `text_material`, audience/use/layout/slide defaults, clarification strategy, confirmation points, editable PPTX contract, same-version PDF preview, authenticated preview/download references, idempotency, receipt, policy and renderer binding.
- Bound the capability to QCP and the existing presentation Workflow/Hermes execution path. Text material, presentation defaults, artifact contract and QCP request hash survive requirement confirmation.
- Removed iOS keyword classification and direct PPT/Word workflow creation from Chat. Natural-language goals now continue through the normal Hermes session, where Registry-compiled native tools select the capability.
- Removed iOS `createWorkflow` selection between `workflow.create` and `presentation.create_from_document`; the method now invokes only the capability explicitly named by its API contract. Hermes proposals for `presentation.create_from_text` are decoded, rendered and confirmed by iOS through QCP.
- Placed the Chat tab and parent-owned Workflow activity/floating navigation chrome in one vertical layout. The bars now consume layout space below Chat instead of overlaying the input; keyboard presentation hides the parent chrome.
- Hardened exact-SHA deployment for the private GitHub repository by exporting the reviewed commit locally, validating its SHA-256 remotely, and feeding the immutable archive to the existing release script. Corrected the public-download fallback repository name.

## Verification completed before commit

- Registry/generated-doc synchronization: `python3 scripts/generate_product_capability_manual.py --check` — passed.
- Python lint/compile: Ruff on changed backend/tests and `python3 -m compileall -q backend scripts/hermes_bridge.py` — passed.
- Backend acceptance: 139 passed across product capabilities, workflows, event projection, presentation, knowledge and consumption gates.
- iOS acceptance: `WorkflowLifecycleDTOTests` + `KnowledgeNoteStoreTests` — `xcodebuild` exited 0; result bundle under DerivedData test logs dated `2026-09-14_18-30-19-+0800`.
- `git diff --check` — passed.
- Post-layout Simulator build — passed; authenticated App screenshot `/tmp/quantumn-ppt-layout-structural-fix.png` shows the Chat input and floating navigation in separate, non-overlapping regions.
- The pre-fix archive `/tmp/Quantumn-1.0.3-40.xcarchive` was read back as `CFBundleVersion=40`, `CFBundleSupportedPlatforms=[iPhoneOS]`, `arm64`; it is not a Simulator artifact and is not claimed as the post-fix binary.

## Pending release evidence

- GitHub push, exact-SHA deployment, server health and production iOS App natural-language PPT run will be recorded after execution.
- The first exact-SHA attempt for `51093d78d7d1254acc4bdcf72a1bc9719b1f6926` stopped before mutation with HTTP 404 because the release script referenced the wrong codeload repository. Production remained on `3444d3b08b1bedb674ca91deaef7ea97bf74522c`; the deployment transport was corrected before retry.
- A valid temporary QA access token was minted from the production verifier context for `qa-interlaken-user`; the current agreement `2026-09-06` was accepted with an iOS source receipt and read back. No credential is stored in Git.
