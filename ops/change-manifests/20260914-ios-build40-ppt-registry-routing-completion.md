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
- Moved the Chat input to a bottom safe-area inset so the parent Workflow activity bar and floating navigation reserve space instead of covering the input.

## Verification completed before commit

- Registry/generated-doc synchronization: `python3 scripts/generate_product_capability_manual.py --check` — passed.
- Python lint/compile: Ruff on changed backend/tests and `python3 -m compileall -q backend scripts/hermes_bridge.py` — passed.
- Backend acceptance: 139 passed across product capabilities, workflows, event projection, presentation, knowledge and consumption gates.
- iOS acceptance: `WorkflowLifecycleDTOTests` + `KnowledgeNoteStoreTests` — 164 passed, 0 failures; result bundle under DerivedData test logs dated `2026-09-14_18-30-19-+0800`.
- `git diff --check` — passed.
- The pre-fix archive `/tmp/Quantumn-1.0.3-40.xcarchive` was read back as `CFBundleVersion=40`, `CFBundleSupportedPlatforms=[iPhoneOS]`, `arm64`; it is not a Simulator artifact and is not claimed as the post-fix binary.

## Pending release evidence

- GitHub push, exact-SHA deployment, server health and production iOS App natural-language PPT run will be recorded after execution.
- A valid temporary QA access token was minted from the production verifier context for `qa-interlaken-user`; the current agreement `2026-09-06` was accepted with an iOS source receipt and read back. No credential is stored in Git.
