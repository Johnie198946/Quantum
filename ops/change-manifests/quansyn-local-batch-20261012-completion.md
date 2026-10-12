# QuanSyn local batch command and progress UX — completion

Date: 2026-10-12

## Scope

- Add `/quansyn` as the no-argument local-owner entry point.
- Automatically collect all server-pending Mac requests plus locally imported retryable requests.
- Execute the collected requests in one trusted Hermes turn while recording each result independently.
- Preserve `/quansyn qs_…` and the existing Chinese single-item commands for compatibility.
- Replace a clicked Feishu card immediately with an orange, non-actionable “执行中” card.
- Render green success, orange partial-success, or red failure completion cards.
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
- `pytest tests/test_quansyn.py tests/test_quansyn_mac.py tests/test_travel_pcm_capabilities.py -q`: 35 passed.
- Tests cover slash normalization, all-pending batch collection, independent success/failure recording, failed-item retry, duplicate-active suppression, immediate original-card replacement, and completion-card delivery from the adapter event loop.

## Rollout

- Canonical source: `agency/hermes-plugins/ai-lab-capabilities/`.
- Runtime copy: default-profile plugin directory under `~/.hermes/plugins/ai-lab-capabilities/`.
- Gateway must be restarted after synchronizing the runtime copy.
