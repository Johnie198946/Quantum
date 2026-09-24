#!/usr/bin/env python3
"""Finalize eligible native reviews independently, then release."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT = Path("/Users/dengzhaoyu/Projects/quantum-2.0-publication-main")
ROOT = Path("/Users/dengzhaoyu/.hermes/outputs/quantumn-editorial-v2")

sys.path.insert(0, str(PROJECT))
os.chdir(PROJECT)

from publication_editorial_remote import main as editorial_main  # noqa: E402
from publication_release_remote import main as release_main  # noqa: E402


def eligible_roots() -> list[Path]:
    roots: list[Path] = []
    for manifest_path in sorted(ROOT.rglob("draft-manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        eligible = False
        for item in manifest.get("items", []):
            if item.get("status") != "await_review" or item.get("error"):
                continue
            review_path = manifest_path.parent / str(item.get("review_file") or "")
            if not review_path.is_file():
                continue
            try:
                decision = json.loads(review_path.read_text(encoding="utf-8")).get("decision")
            except (OSError, json.JSONDecodeError):
                continue
            if decision in {"approved", "rejected"}:
                eligible = True
                break
        if eligible:
            roots.append(manifest_path.parent)
    return roots


def main() -> int:
    finalize_failures: list[dict[str, object]] = []
    for root in eligible_roots():
        try:
            code = editorial_main(["finalize", "--root", str(root)])
        except Exception as exc:  # stale local history must not block current release/readback
            code = 1
            finalize_failures.append({"root": str(root), "error": str(exc)})
        else:
            if code:
                finalize_failures.append({"root": str(root), "exit_code": code})
    if finalize_failures:
        print(json.dumps({"editorial_finalize_warnings": finalize_failures}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    return release_main([])


if __name__ == "__main__":
    raise SystemExit(main())
