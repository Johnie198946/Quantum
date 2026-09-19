"""Deterministic source claims and slide provenance for presentations."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

_APPROVAL_STATES = {"pending", "approved", "rejected"}
_TRANSFORMS = {"verbatim", "translated", "summarized", "visualized"}
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_SENTENCE_ENDINGS = frozenset(".!?。！？")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _nonblank_paragraph_spans(text: str) -> Iterable[tuple[int, int]]:
    """Yield each non-blank source line as a provenance paragraph.

    User-authored briefs frequently use emoji headings and numbered lines without
    blank separators. Treating the whole block as one paragraph would merge
    unrelated itinerary items until the next punctuation mark.
    """
    offset = 0
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        if body.strip():
            start = offset + len(body) - len(body.lstrip())
            end = offset + len(body.rstrip())
            if end > start:
                yield start, end
        offset += len(line)


def _sentence_spans(text: str, start: int, end: int) -> Iterable[tuple[int, int]]:
    cursor = start
    while cursor < end:
        while cursor < end and text[cursor].isspace():
            cursor += 1
        if cursor >= end:
            return
        sentence_start = cursor
        while cursor < end:
            cursor += 1
            if text[cursor - 1] in _SENTENCE_ENDINGS:
                while cursor < end and text[cursor] in "\"'”’)]}」』":
                    cursor += 1
                yield sentence_start, cursor
                break
        else:
            yield sentence_start, end


def build_source_claims(
    text: str,
    *,
    source_id: str,
    source_client_session_id: str,
    approval_state: str = "pending",
) -> list[dict[str, Any]]:
    """Split source text into stable, exact-span claims without rewriting it."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("source text must not be empty")
    if len(text) > 80_000:
        raise ValueError("source text exceeds 80000 characters; truncation is forbidden")
    if not _ID_PATTERN.fullmatch(source_id):
        raise ValueError("source_id is invalid")
    if not _ID_PATTERN.fullmatch(source_client_session_id):
        raise ValueError("source_client_session_id is invalid")
    if approval_state not in _APPROVAL_STATES:
        raise ValueError("approval_state is invalid")

    claims: list[dict[str, Any]] = []
    for paragraph_start, paragraph_end in _nonblank_paragraph_spans(text):
        for claim_start, claim_end in _sentence_spans(text, paragraph_start, paragraph_end):
            claim = text[claim_start:claim_end]
            digest = _sha256(claim)
            claims.append(
                {
                    "claim_id": f"{source_id}:c{len(claims) + 1:03d}:{digest[:12]}",
                    "source_id": source_id,
                    "span": {"start": claim_start, "end": claim_end},
                    "claim": claim,
                    "slide_id": None,
                    "transform": "verbatim",
                    "approval_state": approval_state,
                    "source_client_session_id": source_client_session_id,
                    "content_hash": digest,
                }
            )
    if not claims:
        raise ValueError("source text contains no claims")
    return claims


def bind_claims_to_slides(
    claims: Iterable[Mapping[str, Any]],
    bindings: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Create explicit claim-to-slide records; unknown and rejected claims fail closed."""
    by_id = {str(item.get("claim_id") or ""): dict(item) for item in claims}
    if not by_id or "" in by_id:
        raise ValueError("claims contain a missing claim_id")
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for binding in bindings:
        claim_id = str(binding.get("claim_id") or "")
        slide_id = str(binding.get("slide_id") or "")
        transform = str(binding.get("transform") or "verbatim")
        if claim_id not in by_id:
            raise ValueError(f"unknown source claim: {claim_id}")
        if not _ID_PATTERN.fullmatch(slide_id):
            raise ValueError("slide_id is invalid")
        if transform not in _TRANSFORMS:
            raise ValueError("transform is invalid")
        # A claim may legitimately support more than one slide.  Never mutate
        # the canonical claim object: reusing it here aliases earlier records,
        # so a later binding rewrites their slide_id and creates false
        # duplicate trace records during validation.
        source = dict(by_id[claim_id])
        if source.get("approval_state") != "approved":
            raise ValueError(f"source claim is not approved: {claim_id}")
        key = (claim_id, slide_id)
        if key in seen:
            raise ValueError("duplicate claim-to-slide binding")
        seen.add(key)
        source["slide_id"] = slide_id
        source["transform"] = transform
        result.append(source)
    return result


def validate_trace_matrix(
    records: Iterable[Mapping[str, Any]],
    *,
    source_texts: Mapping[str, str],
    source_client_session_id: str,
    require_mapped: bool = True,
) -> list[dict[str, Any]]:
    """Validate exact spans, hashes, approvals, mapping, and session provenance."""
    validated: list[dict[str, Any]] = []
    identities: set[tuple[str, str | None]] = set()
    for raw in records:
        record = dict(raw)
        required = {
            "claim_id",
            "source_id",
            "span",
            "claim",
            "slide_id",
            "transform",
            "approval_state",
            "source_client_session_id",
            "content_hash",
        }
        if set(record) != required:
            raise ValueError("source trace contains unsupported or missing fields")
        source_id = str(record["source_id"])
        source = source_texts.get(source_id)
        if source is None:
            raise ValueError(f"source text is unavailable: {source_id}")
        span = record["span"]
        if not isinstance(span, dict) or set(span) != {"start", "end"}:
            raise ValueError("source span is invalid")
        start, end = span.get("start"), span.get("end")
        if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(source):
            raise ValueError("source span is out of bounds")
        claim = str(record["claim"])
        if source[start:end] != claim or _sha256(claim) != record["content_hash"]:
            raise ValueError("source claim span or hash was tampered")
        if record["source_client_session_id"] != source_client_session_id:
            raise ValueError("source claim belongs to another client session")
        if record["approval_state"] not in _APPROVAL_STATES:
            raise ValueError("approval_state is invalid")
        if record["transform"] not in _TRANSFORMS:
            raise ValueError("transform is invalid")
        if require_mapped and (record["approval_state"] != "approved" or not record["slide_id"]):
            raise ValueError("final presentation claims must be approved and mapped")
        identity = (str(record["claim_id"]), record["slide_id"])
        if identity in identities:
            raise ValueError("duplicate source trace record")
        identities.add(identity)
        validated.append(record)
    if not validated:
        raise ValueError("source trace matrix must not be empty")
    return validated


def build_trace_manifest(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    canonical_records = [dict(item) for item in records]
    canonical = json.dumps(
        canonical_records, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        "schema_version": 1,
        "record_count": len(canonical_records),
        "source_ids": sorted({str(item["source_id"]) for item in canonical_records}),
        "slide_ids": sorted({str(item["slide_id"]) for item in canonical_records if item.get("slide_id")}),
        "content_hash": _sha256(canonical),
        "records": canonical_records,
    }
