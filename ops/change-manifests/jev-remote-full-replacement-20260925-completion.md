# Remote semantic JEV full replacement — completion receipt

Date: 2026-09-25

## Decision

Owner accepted the measured remote semantic selector latency in exchange for routing accuracy. Remote semantic JEV is therefore the default and sole Skill/Agent selector. Hermes remains the only runtime. The retained Agency plugin is an exact catalog loader only; it no longer searches, ranks, recommends, inspects, or delegates.

## Source changes

- `ai-lab-capabilities` version `2.2.0`.
- `agency-agents-router` compatibility plugin version `2.0.0`, exposing only `agency_agents_load`.
- Parent turns block `agency_agents_search`, `agency_agents_inspect`, `agency_agents_delegate`, and direct `agency_agents_load`.
- JEV-selected child turns may load only the exact selected Agent and version.
- Installer overlays the pinned upstream Agency catalog with the exact-loader adapter.
- Resident remote JEV is enabled by default; explicit `JEV_RESIDENT_ENABLE=0` is required to disable it.
- Provider timeout increased from `7.0 s` to `12.0 s`; warmup timeout from `15.0 s` to `20.0 s`.
- Agency business prompts and backend orchestration no longer instruct the model to use the legacy Agency selector.
- PCM contract updated to `1.3.0`, activation `enabled_remote_semantic_default`, with explicit owner latency waiver and bounded acceptance evidence.

## Verification

Focused regression:

```text
195 passed, 1 skipped
frontend agency runbook: 2 passed
Ruff: passed
py_compile: passed
git diff --check: passed
```

Final focused rerun after timeout/config changes:

```text
130 passed
frontend agency runbook: 2 passed
Ruff: passed
py_compile: passed
git diff --check: passed
```

Plugin Doctor:

```text
ai-lab-capabilities 2.2.0: OK; 2 tools, 11 hooks
agency-agents-router 2.0.0: OK; 1 tool, 0 hooks
```

Active disk smoke:

```text
skills=306
agents=273
Agency tools=['agency_agents_load']
```

## Remote selector acceptance

Scope: controlled fresh Gateway-resident process, 579 candidates, 12 unique intents repeated three times.

```text
Skill accuracy:        100.00%
Agent accuracy:         97.22%
Strict joint accuracy:  97.22%
Abstain accuracy:      100.00%
Fallback count:          0/36
Cache miss P50:       2193.255 ms
Cache miss P95:       3404.529 ms
```

Strongest counterexample: one harness-acceptance request selected the plausible but gold-disallowed `agency:test-results-analyzer`, so the bounded set is not 100% strict joint accuracy. The evidence set has only 12 unique intents and is not a release-quality blind corpus.

## Hermes Runtime A/B

Twelve paired requests, same fresh Runtime and main model:

```text
No JEV TTFT P50:       2016.432 ms
Remote JEV TTFT P50:   4442.364 ms
Aggregate P50 delta:  +2425.932 ms
Paired median delta:  +2337.143 ms
Paired P95 delta:     +4046.812 ms
Remote JEV slower:          11/12
```

The owner explicitly accepts this latency tradeoff. Timeout, malformed output, unauthorized ID, stale version, nonfinite confidence, and low confidence continue to fail safely to direct Hermes execution.

## Active-file verification

Source and active file hashes matched for:

- `capability_router.py`: `ae5db933bf27a7d4b5dc8c8e2f4fa397d5339a013d35bdf5f268a5c92fb104fb`
- `jev_selector.py`: `36656304b425b6409772e66ea8c2085544cde46d5668974231e8728a8c5f036d`
- `jev_resident.py`: `4d061f1f0d2cb73e7e8fe40d72fd9e148924e112723116c75111619d6c3e0daa`
- exact Agency loader: `1415fbf807fa909559c5ad5a99d9e436d97f19cc5b28bb076b2c783f60bd5fbd`

Stale discoverable plugin backup was moved out of `~/.hermes/plugins` into `~/.hermes/backups/plugin-discovery`.

## Evidence

- `/Users/dengzhaoyu/.hermes/cache/jev-remote-full-replacement-acceptance-20260925.json`
  - SHA-256: `a618518e1de9c826c5cf5e77bcd56668a466d09eb76a92c5886d35f43d99c531`
- `/Users/dengzhaoyu/.hermes/cache/jev-runtime-remote-full-replacement-20260925.json`
  - SHA-256: `c3c3d2dec33d78ae8adb938e7614e123ffa31f9967e30488221549993a37148f`
- PCM SHA-256 before commit: `86890b413e13da8bd10445c5c47cd8cd14e16572b92a87745d551f1c6492ede2`

## Activation boundary

Active plugin files and configuration were synchronized on disk, but no Gateway restart/shutdown command was executed or verified. Therefore this receipt proves disk state and fresh-process consumption, not that the already-running long-lived Gateway process has reloaded version `2.2.0`.
