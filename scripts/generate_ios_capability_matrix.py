#!/usr/bin/env python3
"""Generate the iOS/QWS capability closure matrix from the PCM manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
PCM = ROOT / "backend/contracts/product-capabilities"
OUTPUT = ROOT / "ops/acceptance/ios-capability-matrix.json"
COVERAGE = ROOT / "ops/acceptance/pcm-ios-coverage.yaml"
REQUIRED_COLUMNS = (
    "capability", "schema", "handler", "policy",
    "confirmation_cas_idempotency", "event", "renderer",
    "ios_consumer", "qws_consumer", "automated_tests", "production_receipt",
)


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected mapping")
    return value


def generate() -> dict[str, Any]:
    manifest = load_yaml(PCM / "manifest.yaml")
    scope = load_yaml(PCM / str(manifest["ios_scope"]))
    capability_files = manifest["capabilities"]
    if isinstance(capability_files, str):
        capability_files = [capability_files]
    capability_docs = [load_yaml(PCM / str(name)) for name in capability_files]
    binding_doc = load_yaml(PCM / str(manifest["bindings"]))
    capabilities = {
        item["id"]: item
        for document in capability_docs
        for item in document["capabilities"]
    }
    bindings = {item["id"]: item["handler"] for item in binding_doc["bindings"]}
    annotations = scope.get("annotations") or {}
    coverage_doc = load_yaml(COVERAGE)
    coverage = {item["capability"]: item for item in coverage_doc.get("features") or []}
    requested = list(scope.get("capabilities") or [])
    if len(requested) != len(set(requested)):
        raise SystemExit("ios scope contains duplicate capability ids")
    rows: list[dict[str, Any]] = []
    for capability_id in requested:
        cap = capabilities.get(capability_id)
        annotation = annotations.get(capability_id) or {}
        evidence = coverage.get(capability_id) or {}
        receipt = evidence.get("production_receipt") or {"status": "unverified", "evidence": None}
        if cap is None:
            status = "absent"
        elif cap.get("implementation_status") != "implemented":
            status = "unverified"
        elif not annotation.get("ios_consumer") or not annotation.get("qws_consumer"):
            status = "partial"
        elif receipt.get("status") != "implemented" or not receipt.get("evidence"):
            status = "partial"
        else:
            status = "implemented"
        rows.append({
            "capability": capability_id,
            "schema": None if cap is None else {
                "version": cap["version"],
                "input": cap["input_schema"],
                "output": cap["output_schema"],
            },
            "handler": None if cap is None else bindings.get(cap["handler_binding"]),
            "policy": None if cap is None else cap["policy_ref"],
            "confirmation_cas_idempotency": None if cap is None else {
                "confirmation": cap["confirmation"],
                "cas": cap.get("preconditions") or [],
                "idempotency": cap["idempotency"],
            },
            "event": None if cap is None else cap["result_event"],
            "renderer": None if cap is None else f"{cap['renderer']}@{cap['renderer_version']}",
            "ios_consumer": annotation.get("ios_consumer"),
            "qws_consumer": annotation.get("qws_consumer"),
            "automated_tests": [] if cap is None else list(cap.get("tests") or []),
            "production_receipt": receipt,
            "status": status,
        })
    counts = {value: sum(row["status"] == value for row in rows) for value in scope["status_values"]}
    return {
        "protocol": manifest["protocol"],
        "pcm_version": manifest["version"],
        "scope_version": scope["version"],
        "source": "backend/contracts/product-capabilities/manifest.yaml#ios_scope",
        "required_columns": list(REQUIRED_COLUMNS),
        "counts": counts,
        "total": len(rows),
        "capabilities": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    result = generate()
    encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != encoded:
            raise SystemExit("iOS capability matrix is stale; regenerate it")
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(encoded, encoding="utf-8")
    if args.require_complete:
        incomplete = [row["capability"] for row in result["capabilities"] if row["status"] != "implemented"]
        if incomplete:
            raise SystemExit(f"incomplete iOS capability matrix ({len(incomplete)}): {', '.join(incomplete)}")
    print(json.dumps(result["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
