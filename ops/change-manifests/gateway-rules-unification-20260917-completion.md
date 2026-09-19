# Gateway engineering rules unification

- task_id: `gateway-rules-unification-20260917`
- status: `PUSHED`
- branch: `main`
- base_sha: `2cfa3c827da3dbc0cf899f96d7b4bda753c5fdf1`
- rules_commit: `f92cfa74a9535f215bde5f597bc604ec2fb784f8`
- receipt_commit: commit containing this manifest
- remote_rules_sha: `f92cfa74a9535f215bde5f597bc604ec2fb784f8` (verified with `git ls-remote`)
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
- Post-push CI exposed five repository-wide Ruff findings: two missing EOF newlines in this change and three pre-existing findings (one dead Gateway variable, one test lambda, one missing EOF newline). All five were corrected without semantic expansion.
- Expanded regression after the lint repair: `36 passed, 8 warnings`; repository-wide `python3 -m ruff check backend/ scripts/ tests/`: passed.
- Final Python syntax, CI YAML parse, generated parity and `git diff --check`: passed.
- GitHub Actions run `35198639870`: lint and frontend passed; build executed both new governance checks successfully, then failed at the repository-wide pytest step. This preserves the existing full-suite baseline blocker rather than weakening or skipping the gate.
- A local Python 3.12 full-suite diagnostic is not an acceptance substitute for CI's Python 3.11 environment; it exposed broad dependency/test-isolation failures and is recorded only as diagnostic evidence.
- Worktree check: clean baseline on `main`; rules changes and the five bounded Ruff remediations are isolated from unrelated work.

## Remaining risks

- Repository-wide CI remains red at the pre-existing full pytest gate; the new governance checker, PCM parity check, repository Ruff gate and focused regressions pass.
- This change does not deploy or alter production runtime behavior.