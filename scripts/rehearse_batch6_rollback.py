#!/usr/bin/env python3
"""Deterministic, non-destructive Batch 6 rollback rehearsal.

The rehearsal snapshots the refactor files into an isolated temporary release,
corrupts one staged file, restores the staged release from its rollback point,
and proves both staged and working-tree hashes match the pre-drill manifest.
It never edits the repository targets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from backend.services.batch6_refactor_guard import (
    BATCH6_KILL_SWITCH_ENV,
    require_batch6_execution_enabled,
)

REPO = Path(__file__).resolve().parents[1]
TARGETS = (
    "backend/api/quantum_workspace.py",
    "backend/api/workflows.py",
    "scripts/hermes_bridge.py",
    "backend/services/qws_access.py",
    "backend/services/qws_session_context.py",
    "backend/services/workflow_reviews.py",
    "backend/services/workflow_document_contracts.py",
    "backend/services/batch6_refactor_guard.py",
    "tests/test_batch6_refactor.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest(root: Path) -> dict[str, str]:
    return {relative: sha256(root / relative) for relative in TARGETS}


def copy_targets(source: Path, destination: Path) -> None:
    for relative in TARGETS:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)


def rehearse() -> dict[str, Any]:
    source_before = manifest(REPO)
    original_switch = os.environ.get(BATCH6_KILL_SWITCH_ENV)
    try:
        os.environ[BATCH6_KILL_SWITCH_ENV] = "1"
        try:
            require_batch6_execution_enabled("rollback_rehearsal")
        except HTTPException as exc:
            kill_switch = {
                "blocked": exc.status_code == 503,
                "status_code": exc.status_code,
                "detail": exc.detail,
            }
        else:  # pragma: no cover - guarded by the test and explicit assertion below
            kill_switch = {"blocked": False}
    finally:
        if original_switch is None:
            os.environ.pop(BATCH6_KILL_SWITCH_ENV, None)
        else:
            os.environ[BATCH6_KILL_SWITCH_ENV] = original_switch
    if not kill_switch.get("blocked"):
        raise RuntimeError("Batch 6 kill switch did not block new execution")

    with tempfile.TemporaryDirectory(prefix="quantumn-batch6-rollback-") as raw:
        root = Path(raw)
        rollback = root / "rollback-point"
        staged = root / "staged-release"
        copy_targets(REPO, rollback)
        copy_targets(REPO, staged)
        rollback_manifest = manifest(rollback)
        staged_before = manifest(staged)
        if rollback_manifest != source_before or staged_before != source_before:
            raise RuntimeError("rollback snapshot does not match source manifest")

        victim = staged / "backend/services/workflow_document_contracts.py"
        with victim.open("ab") as handle:
            handle.write(b"\n# simulated-corruption\n")
        corrupted_hash = sha256(victim)
        if corrupted_hash == source_before["backend/services/workflow_document_contracts.py"]:
            raise RuntimeError("rollback rehearsal did not alter staged release")

        copy_targets(rollback, staged)
        staged_after = manifest(staged)
        if staged_after != source_before:
            raise RuntimeError("restored staged release differs from rollback point")

    source_after = manifest(REPO)
    if source_after != source_before:
        raise RuntimeError("rollback rehearsal modified the working tree")
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "isolated_local_release_copy",
        "targets": list(TARGETS),
        "source_manifest_before": source_before,
        "rollback_manifest": rollback_manifest,
        "staged_manifest_after_restore": staged_after,
        "source_manifest_after": source_after,
        "simulated_corruption": {
            "path": "backend/services/workflow_document_contracts.py",
            "sha256": corrupted_hash,
        },
        "kill_switch": kill_switch,
        "rollback_verified": True,
        "working_tree_unchanged": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    receipt = rehearse()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
