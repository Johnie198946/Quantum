# Production JEV resident recovery — 2026-10-08

## Scope

Restore the resident JEV selector and the exact Agent Agency loader on production host `120.24.248.58` without changing the deployed application release.

## Root cause

Two runtime-state drifts prevented the intended route:

1. `/etc/ai-lab-platform/hermes-egress.env` still pointed Bridge and Chat Worker at the emergency Mac reverse-tunnel proxy `127.0.0.1:17897`. No listener existed there. The durable server-side `mihomo.service` was healthy on `127.0.0.1:7890`; direct checks through that proxy reached the Codex upstream.
2. The production Hermes home contained `ai-lab-capabilities` but not `agency-agents-router`. Its pinned `agents.json` catalog was absent, so `_agency_capabilities()` returned no Agent Agency candidates and `agency_agents_load` was unavailable before repair.

The earlier successful OAuth/client construction only proved credential parsing. It did not prove the Bridge resident was ready.

## Production changes

- Restored `HTTP_PROXY` and `HTTPS_PROXY` to `http://127.0.0.1:7890` in `/etc/ai-lab-platform/hermes-egress.env`.
- Preserved the pre-change egress file as `/etc/ai-lab-platform/hermes-egress.env.before-jev-fix-20261008T170544+0800`.
- Installed the exact loader under `/var/lib/quantumn-hermes/.hermes/plugins/agency-agents-router`.
- Enabled both `ai-lab-capabilities` and `agency-agents-router` in the production Hermes config.
- Installed the 273-agent catalog generated from pinned upstream commit `msitarzewski/agency-agents@3c9588880b7cafaec325a104899fd8bbe27e7d72`.
- Preserved the pre-change Hermes config in `/var/lib/quantumn-hermes/.hermes/backups/agency-router-before-jev-fix-20261008T171636+0800`.
- Restarted Chat Worker and Bridge only after confirming the durable chat queue was empty.
- The deployed application release remained `388b948630731a63a7a5ba45584c204805f1b7b4`.

## Supply-chain verification

The pinned upstream source was fetched independently, converted with its Hermes converter, and validated with `scripts/check-hermes-plugin.py`.

- Generated catalog count: `273`
- Generated and installed catalog SHA-256: `ad8c498e80f99836a3ec2dc71d78a8234a3286a4fc5ee5ac986c7a882de92e08`
- Exact loader `__init__.py` SHA-256: `1415fbf807fa909559c5ad5a99d9e436d97f19cc5b28bb076b2c783f60bd5fbd`
- Exact loader `plugin.yaml` SHA-256: `9c0bb0ad3ca0d13d0b3b9d60bd1474e949d0478801d1537b49bd148daaf3d2de`

## Runtime acceptance

At `2026-10-08T17:26:33+08:00`:

- `hermes-bridge.service`: active, PID `24901`, `NRestarts=0`
- Bridge `MemoryCurrent=773505024`, `MemoryPeak=1191604224`, below the existing `MemoryMax=1280M`
- `hermes-chat-worker.service`: active, PID `24896`, `NRestarts=0`
- Proxy listener present on `127.0.0.1:7890`
- Bridge journal after final restart: zero `JEV resident warmup unavailable`, zero missing-Codex-token errors, zero plugin-load errors
- Exact production environment resident probe: `ready=true`, `provider_ready=true`, provider `openai-codex`, model `gpt-6-luna`, API mode `codex_responses`
- Real semantic selection probe against real Agent Agency cards: selected `agency:multi-agent-systems-architect`, confidence `0.91`, reason `MATCHED`, validated `true`
- Exact loader receipt: `success=true`, slug `multi-agent-systems-architect`
- Bridge HTTP health: OK
- API HTTP health: OK
- Public TLS health: HTTP `200`, certificate verification result `0`
- Unauthenticated bookshelf route: expected HTTP `401`
- Docker containers: `8/8` healthy
- Orphaned JEV probe processes: `0`
- Swap used: `0`

## Rollback

1. Restore `/etc/ai-lab-platform/hermes-egress.env.before-jev-fix-20261008T170544+0800` only if the emergency Mac tunnel is deliberately restored and listening on port `17897`.
2. Restore the backed-up Hermes config from `/var/lib/quantumn-hermes/.hermes/backups/agency-router-before-jev-fix-20261008T171636+0800/config.yaml`.
3. Move `/var/lib/quantumn-hermes/.hermes/plugins/agency-agents-router` aside rather than deleting it until rollback verification is complete.
4. Restart Bridge and Chat Worker with the existing memory and restart-storm limits, then repeat health and route acceptance.
