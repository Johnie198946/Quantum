#!/usr/bin/env python3
"""Generate deterministic PCM manual and coverage from the governed catalog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.capability_catalog import catalog_digest, load_catalog  # noqa: E402


MANUAL = ROOT / "docs" / "product-capability-manual.md"
COVERAGE = ROOT / "docs" / "product-capability-coverage.json"
IOS_COVERAGE = ROOT / "ops" / "acceptance" / "pcm-ios-coverage.yaml"


def outputs() -> tuple[str, str]:
    catalog = load_catalog()
    capabilities = sorted(catalog["capabilities"], key=lambda item: item["id"])
    ios_coverage = yaml.safe_load(IOS_COVERAGE.read_text(encoding="utf-8"))
    ios_features = ios_coverage.get("features") or []
    capability_ids = {item["id"] for item in capabilities}
    unknown = sorted(
        {item.get("capability") for item in ios_features} - capability_ids
    )
    if unknown:
        raise ValueError(f"iOS coverage references unknown capabilities: {unknown}")
    lines = [
        "# Product Capability Manual",
        "",
        f"QCP version: `{catalog['version']}`",
        f"Catalog digest: `{catalog_digest()}`",
        "",
        "| Capability | Domain | Effect | Confirmation | Receipt | Event | Renderer | Status |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in capabilities:
        lines.append(
            f"| `{item['id']}@{item['version']}` | {item['domain']} | {item['effect']} | "
            f"{item['confirmation']} | {item['receipt']} | `{item['result_event']}` | "
            f"`{item['renderer']}@{item['renderer_version']}` | {item['implementation_status']} |"
        )
    lines.extend([
        "", "## Consumption contracts", "",
        "| Contract | Kind | Receipt | Status |", "|---|---|---|---|",
    ])
    for item in sorted(catalog["consumptions"], key=lambda value: value["id"]):
        lines.append(
            f"| `{item['id']}` | {item['kind']} | `{item['receipt']}` | {item['status']} |"
        )
    lines.extend([
        "", "## iOS document-class E2E coverage", "",
        "| iOS user function | Capability | Event | Renderer | Handler | Consumer | Policy | Automated evidence | Production receipt | Status |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ])
    for item in ios_features:
        lines.append(
            f"| {item['ios_user_function']} | `{item['capability']}` | `{item['event']}` | "
            f"`{item['renderer']}` | `{item['handler']}` | `{item['consumer']}` | "
            f"{item['policy']} | {', '.join(f'`{test}`' for test in item['automated_tests'])} | "
            f"{item['production_receipt']['status']} | {item['status']} |"
        )
    lines.extend([
        "",
        "PCM compiles every implemented, client-supported capability into a native Hermes tool at session assembly. Normal business execution does not depend on capability search or describe. QCP validates every invocation against the allowlisted contract; domain handlers remain the authorization truth.",
        "",
    ])
    counts = {status: sum(item["implementation_status"] == status for item in capabilities)
              for status in ("implemented", "partial", "unverified")}
    coverage = {
        "protocol": catalog["protocol"], "version": catalog["version"],
        "catalog_digest": catalog_digest(), "total": len(capabilities),
        "counts": counts,
        "capabilities": [{"id": item["id"], "status": item["implementation_status"], "tests": item["tests"]}
                         for item in capabilities],
        "consumptions": [{
            "id": item["id"], "status": item["status"], "receipt": item["receipt"],
            "implementation_refs": item["implementation_refs"], "gates": item["gates"],
        } for item in sorted(catalog["consumptions"], key=lambda value: value["id"])],
        "ios_coverage": {
            "source": str(IOS_COVERAGE.relative_to(ROOT)),
            "status_values": ios_coverage["status_values"],
            "features": ios_features,
        },
    }
    return "\n".join(lines), json.dumps(coverage, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manual, coverage = outputs()
    if args.check:
        return 0 if MANUAL.read_text(encoding="utf-8") == manual and COVERAGE.read_text(encoding="utf-8") == coverage else 1
    MANUAL.write_text(manual, encoding="utf-8")
    COVERAGE.write_text(coverage, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
