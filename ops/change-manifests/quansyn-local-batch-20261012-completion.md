# QuanSyn local batch command and progress UX — completion

Date: 2026-10-12

## Scope

- Add `/quansyn` as the no-argument local-owner entry point.
- Automatically collect all server-pending Mac requests plus locally imported retryable requests.
- Execute the collected requests in one trusted Hermes turn while recording each result independently.
- Preserve `/quansyn qs_…` and the existing Chinese single-item commands for compatibility.
- Replace a clicked Feishu card immediately with an orange, non-actionable “执行中” card.
- Render green success, orange partial-success, or red failure completion cards.
- For every completed batch item, send an independent result card with an explicit “推送完整结果到 QuanSyn” confirmation button.
- A card callback updates that same card to “执行中” and then to its final state; a published result removes the push button so repeat clicks cannot append duplicate receipt cards.
- Deterministic card actions (`查看`, `拉取`, `推送`) execute in the authenticated plugin handler without an LLM turn; only content-producing actions (`执行`, `拉取并执行`, `批量执行`) enter Hermes generation.
- Keep failed requests in the local queue; skip active/completed requests to prevent duplicate execution.

## Security and state invariants

- Only the configured local owner in the established Feishu/Lark private route is admitted.
- Native card operator, sender and chat route must match.
- Batch output IDs must exactly equal the trusted turn’s batch IDs.
- Output files remain restricted to each request’s output directory and are hash-registered.
- Imported requests survive partial failure and Gateway restart through the plugin state queue.
- The command never automatically publishes results back to QuanSyn Web.

## Verification

- `python3 -m py_compile` passed for the plugin package.
- `git diff --check` passed.
- `pytest tests/test_quansyn.py tests/test_quansyn_mac.py tests/test_travel_pcm_capabilities.py -q`: 37 passed.
- Tests cover slash normalization, all-pending batch collection, independent success/failure recording, failed-item retry, duplicate-active suppression, immediate original-card replacement, completion-card delivery from the adapter event loop, in-place published-card finalization without another push button, and deterministic callback execution without an LLM turn.

## Rollout

- Canonical source: `agency/hermes-plugins/ai-lab-capabilities/`.
- Runtime copy: default-profile plugin directory under `~/.hermes/plugins/ai-lab-capabilities/`.
- Gateway must be restarted after synchronizing the runtime copy.
