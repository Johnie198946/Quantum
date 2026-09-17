# Gateway engineering rules unification

- task_id: `gateway-rules-unification-20260917`
- status: `COMMITTED`
- branch: `main`
- base_sha: `2cfa3c827da3dbc0cf899f96d7b4bda753c5fdf1`
- local_commit: commit containing this manifest
- remote_sha: pending external-write approval
- server_before: not applicable; documentation and CI governance only
- server_after: not deployed
- rollback_point: base SHA above

## Scope

- Make root `AGENTS.md` the mandatory engineering entry for Gateway/Bridge development, integration, joint debugging, incident diagnosis and delivery.
- Keep `docs/product-specs/capability-gateway.md` as the sole semantic source instead of copying the full contract into rules.
- Keep PCM as a generated product view and Hermes Chat architecture as a non-authoritative runtime explanation.
- Add deterministic CI checks for references, required lifecycle rules and source-to-generated-view parity.

## Verification

- `python3 scripts/generate_product_capability_manual.py`: passed; regenerated PCM from the governed source.
- `python3 scripts/generate_product_capability_manual.py --check`: passed.
- `PYTHONPATH=. python3 scripts/check_governed_engineering_rules.py`: passed with `Gateway engineering rules: synchronized`.
- `PYTHONPATH=. python3 -m pytest -q tests/test_governed_engineering_rules.py tests/test_product_capabilities.py`: `28 passed, 8 warnings`.
- Final Python syntax, CI YAML parse, generated parity and `git diff --check`: passed.
- Worktree check: clean baseline on `main`; only the nine task-scoped files listed by `git status` are modified or added.

## Remaining risks

- GitHub push and CI execution require explicit external-write authorization.
- This change does not deploy or alter production runtime behavior.