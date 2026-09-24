#!/usr/bin/env python3
"""Trusted, deterministic operator interface for Quantumn serial editions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from PIL import Image

from backend.services.knowledge_publication_store import (
    PUBLICATION_COVERS, PublicationError, PublicationStore, receipt_set_hash,
)
from backend.services.follow_builders_publication import load_candidate


def _file(value: str) -> tuple[str, Path]:
    try:
        kind, path = value.split("=", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected KIND=/absolute/path") from exc
    return kind, Path(path)


def _cover(store: PublicationStore, path: Path, role: str) -> dict:
    try:
        with Image.open(path) as image:
            image_format, size = image.format, image.size
            image.verify()
    except OSError as exc:
        raise PublicationError(f"invalid {role} image") from exc
    media_type = {"PNG": "image/png", "JPEG": "image/jpeg"}.get(image_format)
    if not media_type or size != PUBLICATION_COVERS[role]["size"]:
        raise PublicationError(f"invalid {role} format or dimensions")
    return {"role": role, "receipt": store.ingest_file(path, PUBLICATION_COVERS[role]["kind"]),
            "media_type": media_type, "width": size[0], "height": size[1]}


def _ingest_covers(store: PublicationStore, bundle: dict, args) -> None:
    paths = {"shelf_cover": args.shelf_cover_file, "reader_cover": args.reader_cover_file}
    if not any(paths.values()):
        return
    provided = {role for role, path in paths.items() if path}
    bundle["assets"] = [item for item in bundle.get("assets", [])
                        if not isinstance(item, dict) or item.get("role") not in provided]
    bundle["assets"].extend(_cover(store, path, role) for role, path in paths.items() if path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Operate frozen Quantumn publication editions")
    parser.add_argument("--root", type=Path, help="publication runtime directory")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare-editorial", "record-editorial-review"):
        command = commands.add_parser(name)
        command.add_argument("bundle", type=Path, nargs="?")
        command.add_argument("--bundle", type=Path, dest="bundle_option")
        command.add_argument("--body-file", type=Path)
        command.add_argument("--source-file", action="append", type=_file, default=[])
        command.add_argument("--rights-file", action="append", type=_file, default=[])
        command.add_argument("--execution-file", action="append", type=_file, default=[])
        command.add_argument("--proof-file", type=Path)
        if name == "record-editorial-review":
            command.add_argument("--review-file", type=Path, required=True)
    stage = commands.add_parser("stage")
    stage.add_argument("bundle", type=Path)
    stage.add_argument("--body-file", type=Path, help="reviewed body bytes; never stored in the bundle path")
    stage.add_argument("--source-file", action="append", type=_file, default=[])
    stage.add_argument("--rights-file", action="append", type=_file, default=[])
    stage.add_argument("--review-file", type=Path)
    stage.add_argument("--proof-file", type=Path)
    stage.add_argument("--execution-file", action="append", type=_file, default=[])
    stage.add_argument("--shelf-cover-file", type=Path)
    stage.add_argument("--reader-cover-file", type=Path)
    source_index = commands.add_parser("stage-source-index")
    source_index.add_argument("package", type=Path)
    source_index.add_argument("--review-file", type=Path)
    status = commands.add_parser("status")
    status.add_argument("--publication-id")
    commands.add_parser("release-due")
    withdraw = commands.add_parser("withdraw")
    withdraw.add_argument("publication_id")
    args = parser.parse_args()
    store = PublicationStore(args.root)
    try:
        if args.command in {"prepare-editorial", "record-editorial-review"}:
            bundle_path = args.bundle_option or args.bundle
            if not bundle_path or (args.bundle_option and args.bundle):
                raise PublicationError("provide exactly one bundle path")
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            if args.body_file:
                body = args.body_file.read_bytes()
                if hashlib.sha256(body).hexdigest() != bundle.get("body_hash"):
                    raise PublicationError("body_hash mismatch")
                bundle["body"] = body.decode("utf-8")
                bundle["body_receipt"] = store.ingest_file(args.body_file, "publication_body", bundle["body_hash"])
            if args.source_file:
                bundle["source_receipts"] = [store.ingest_file(path, kind) for kind, path in args.source_file]
                bundle["source_snapshot_hash"] = receipt_set_hash(bundle["source_receipts"])
            if args.rights_file:
                bundle["rights_evidence"] = [store.ingest_file(path, kind) for kind, path in args.rights_file]
            if args.execution_file:
                bundle["execution_evidence"] = [store.ingest_file(path, kind) for kind, path in args.execution_file]
            if args.proof_file:
                receipt = store.ingest_file(args.proof_file, "editorial_proof")
                bundle["editorial_proof_file"] = f"evidence/{receipt['sha256']}.bin"
                bundle["editorial_proof_sha256"] = receipt["sha256"]
            result = (store.prepare_editorial(bundle) if args.command == "prepare-editorial"
                      else store.record_editorial_review(bundle, args.review_file))
        elif args.command == "stage-source-index":
            bundle, body_file, record_files = load_candidate(args.package)
            bundle["body"] = body_file.read_text(encoding="utf-8")
            bundle["body_receipt"] = store.ingest_file(body_file, "publication_body")
            bundle["source_receipts"] = [store.ingest_file(path, kind) for kind, path in record_files]
            bundle["source_snapshot_hash"] = receipt_set_hash(bundle["source_receipts"])
            if args.review_file:
                review = json.loads(args.review_file.read_text(encoding="utf-8"))
                bundle["review"] = {**review, "receipt": store.ingest_file(args.review_file, "content_review")}
            vault = Path(os.environ.get("AI_LAB_HOME", Path(__file__).resolve().parent.parent / "data" / "vault"))
            result = store.stage(bundle, vault=vault)
        elif args.command == "stage":
            bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
            if args.body_file:
                bundle["body"] = args.body_file.read_text(encoding="utf-8")
                bundle["body_receipt"] = store.ingest_file(args.body_file, "publication_body")
                bundle["body_hash"] = bundle["body_receipt"]["sha256"]
            if args.source_file:
                bundle["source_receipts"] = [store.ingest_file(path, kind) for kind, path in args.source_file]
                bundle["source_snapshot_hash"] = receipt_set_hash(bundle["source_receipts"])
            if args.rights_file:
                bundle["rights_evidence"] = [store.ingest_file(path, kind) for kind, path in args.rights_file]
            if args.execution_file:
                bundle["execution_evidence"] = [store.ingest_file(path, kind) for kind, path in args.execution_file]
            if args.review_file:
                review = json.loads(args.review_file.read_text(encoding="utf-8"))
                receipt = store.ingest_file(args.review_file, "content_review")
                if "reviewer_session" in review:
                    bundle["review"] = {"content_hash": review.get("content_hash"), "decision": review.get("decision"),
                        "reviewed_by": review["reviewer_session"], "reviewed_at": review.get("reviewed_at"), "receipt": receipt}
                else:
                    bundle["review"]["receipt"] = receipt
            if args.proof_file:
                receipt = store.ingest_file(args.proof_file, "editorial_proof")
                bundle["editorial_proof_file"] = f"evidence/{receipt['sha256']}.bin"
                bundle["editorial_proof_sha256"] = receipt["sha256"]
            _ingest_covers(store, bundle, args)
            vault = Path(os.environ.get("AI_LAB_HOME", Path(__file__).resolve().parent.parent / "data" / "vault"))
            result = store.stage(bundle, vault=vault)
        elif args.command == "status":
            result = store.status_report(args.publication_id)
        elif args.command == "release-due":
            result = store.release_due()
        else:
            result = store.withdraw(args.publication_id)
    except (OSError, UnicodeError, json.JSONDecodeError, PublicationError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
