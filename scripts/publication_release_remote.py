#!/usr/bin/env python3
"""Release due publications on production from a trusted local Mac."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


TARGET = "deploy@120.24.248.58"
OPERATOR = (
    "sudo", "-n", "docker", "compose", "-p", "ai-lab-platform",
    "-f", "/opt/ai-lab-platform/docker-compose.yml", "exec", "-T", "api",
    "python", "/app/scripts/publication_operator.py",
    "--root", "/app/data/runtime/publications",
)
STATES = ("draft", "staged", "scheduled", "blocked", "published", "withdrawn")
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,159}$")
UNKNOWN = "unknown"
SHANGHAI = ZoneInfo("Asia/Shanghai")
REQUIRED_DAILY_MEDIA = {
    "shelf_cover", "reader_cover", "illustration_01", "illustration_02", "illustration_03",
}


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity-file")
    parser.add_argument("--known-hosts-file")
    parser.add_argument("--status-only", action="store_true")
    parser.add_argument("--editorial-root", help="opt-in v2 manifest relay before release (or AI_LAB_PUBLICATION_EDITORIAL_ROOT)")
    parser.add_argument("--target-publication-id", help="require this exact publication to read back as published")
    return parser.parse_args(argv)


def _secure_file(value: str, label: str, *, private: bool) -> str:
    path = Path(value).expanduser()
    try:
        info = path.stat()
    except OSError as exc:
        raise ValueError(f"{label} must be an existing secure file") from exc
    forbidden = 0o077 if private else 0o022
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & forbidden:
        raise ValueError(f"{label} must be an owner-controlled secure file")
    return str(path.resolve())


def _trust(args: argparse.Namespace) -> tuple[str, str]:
    config_path = Path("~/.hermes/config/publication-transport.json").expanduser()
    config: dict[str, str] = {}
    identity = args.identity_file or os.environ.get("AI_LAB_PUBLICATION_SSH_KEY")
    known_hosts = args.known_hosts_file or os.environ.get("AI_LAB_PUBLICATION_KNOWN_HOSTS")
    if (not identity or not known_hosts) and config_path.exists():
        config_file = _secure_file(str(config_path), "transport config", private=True)
        value = json.loads(Path(config_file).read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or set(value) - {"identity_file", "known_hosts_file"}
            or any(not isinstance(item, str) or not item for item in value.values())
        ):
            raise ValueError("transport config must contain path-only trust settings")
        config = value
    identity = identity or config.get("identity_file", "~/.ssh/ai_lab_publication_ed25519")
    known_hosts = known_hosts or config.get("known_hosts_file", "~/.ssh/known_hosts")
    return (
        _secure_file(identity, "identity file", private=True),
        _secure_file(known_hosts, "known-hosts file", private=False),
    )


def _ssh(
    identity: str,
    known_hosts: str,
    command: str,
    *,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "ssh", "-F", "/dev/null",
            "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes",
            "-o", "ConnectTimeout=15",
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=2",
            "-o", "StrictHostKeyChecking=yes",
            "-o", f"UserKnownHostsFile={known_hosts}",
            "-i", identity,
            "--", TARGET, command,
        ],
        text=True,
        input=input_text,
        capture_output=True,
        timeout=120,
        check=False,
    )


def _json(stdout: str, label: str) -> tuple[bool | None, dict]:
    value = json.loads(stdout)
    if not isinstance(value, dict):
        raise ValueError(f"{label} returned an invalid JSON envelope")
    ok = value.get("ok")
    if ok is not None and not isinstance(ok, bool):
        raise ValueError(f"{label} returned an invalid ok value")
    if "result" in value:
        if not isinstance(value["result"], dict) or set(value) != {"ok", "result"}:
            raise ValueError(f"{label} returned a conflicting JSON envelope")
        return ok, value["result"]
    return ok, {key: item for key, item in value.items() if key != "ok"}


def _status(stdout: str, returncode: int, label: str = "status") -> dict:
    if returncode != 0:
        raise ValueError(f"{label} command failed (exit {returncode})")
    ok, result = _json(stdout, label)
    if ok is not True:
        raise ValueError(f"{label} command failed")
    items, missing = result.get("items"), result.get("missing")
    if not isinstance(items, list) or not isinstance(missing, list):
        raise ValueError(f"{label} returned an invalid result")
    edition_ids: set[str] = set()
    published_ids: set[str] = set()
    for item in items:
        if (
            not isinstance(item, dict)
            or any(not _valid_id(item.get(key)) for key in ("edition_id", "publication_id", "series_id"))
            or not _valid_date(item.get("issue_date"))
            or item.get("state") not in STATES
            or not isinstance(item.get("edition"), int)
            or isinstance(item.get("edition"), bool)
            or item["edition"] < 1
            or not isinstance(item.get("blocked_reasons", []), list)
            or any(not isinstance(reason, str) or not reason for reason in item.get("blocked_reasons", []))
            or ("body_available" in item and not isinstance(item["body_available"], bool))
            or ("media_roles" in item and (
                not isinstance(item["media_roles"], list)
                or any(not isinstance(role, str) for role in item["media_roles"])
            ))
        ):
            raise ValueError(f"{label} returned an invalid item")
        if item["edition_id"] in edition_ids:
            raise ValueError(f"{label} returned duplicate edition IDs")
        edition_ids.add(item["edition_id"])
        if item["state"] == "published":
            if item["publication_id"] in published_ids:
                raise ValueError(f"{label} returned conflicting published editions")
            published_ids.add(item["publication_id"])
    for item in missing:
        if (
            not isinstance(item, dict)
            or not _valid_id(item.get("series_id"))
            or not _valid_date(item.get("issue_date"))
            or item.get("status") not in {"missing", "overdue_missing", *(f"overdue_{state}" for state in STATES)}
        ):
            raise ValueError(f"{label} returned an invalid missing issue")
    expected = result.get("expected_issues")
    if expected is not None:
        if not isinstance(expected, list):
            raise ValueError("invalid expected publication occurrences")
        keys = set()
        for occurrence in expected:
            if (not isinstance(occurrence, dict)
                    or not _valid_id(occurrence.get("series_id"))
                    or not _valid_date(occurrence.get("issue_date"))
                    or not isinstance(occurrence.get("issue_key"), str)
                    or not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T(?:[01]\d|2[0-3]):[0-5]\d)?", occurrence["issue_key"])
                    or not isinstance(occurrence.get("issue_slot"), str)
                    or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", occurrence["issue_slot"])):
                raise ValueError("invalid expected publication occurrence")
            day, slot = occurrence["issue_date"], occurrence["issue_slot"]
            expected_key = day if slot == "12:00" else f"{day}T{slot}"
            if occurrence["issue_key"] != expected_key or occurrence.get("release_at") != f"{day}T{slot}:00+08:00":
                raise ValueError("publication occurrence identity mismatch")
            key = (occurrence["series_id"], occurrence["issue_key"])
            if key in keys:
                raise ValueError("duplicate expected publication occurrence")
            keys.add(key)
    return result


def _release(stdout: str, returncode: int) -> dict:
    if returncode not in {0, 3}:
        raise ValueError(f"release-due command failed (exit {returncode})")
    ok, result = _json(stdout, "release-due")
    expected_status = {0: "ok", 3: "attention_required"}[returncode]
    if result.get("status") not in {expected_status, "ok"}:
        raise ValueError("release-due exit code disagrees with its status")
    if ok is not None and ok != (returncode == 0):
        raise ValueError("release-due exit code disagrees with its envelope")
    if any(not isinstance(result.get(key), list) for key in ("released", "blocked", "superseded", "missing")):
        raise ValueError("release-due returned an invalid result")
    released, blocked, superseded, missing = (result[key] for key in ("released", "blocked", "superseded", "missing"))
    blocked_ids = [item.get("edition_id") if isinstance(item, dict) and isinstance(item.get("edition_id"), str) else None for item in blocked]
    if (
        any(not _valid_id(item) for item in [*released, *superseded])
        or len(set(released)) != len(released)
        or len(set(superseded)) != len(superseded)
        or len(set(blocked_ids)) != len(blocked)
        or set(released) & set(superseded)
        or set(released) & set(blocked_ids)
        or set(superseded) & set(blocked_ids)
        or any(
            not isinstance(item, dict)
            or not _valid_id(item.get("edition_id"))
            or not isinstance(item.get("reasons"), list)
            or not item["reasons"]
            or any(not isinstance(reason, str) or not reason for reason in item["reasons"])
            for item in blocked
        )
        or any(
            not isinstance(item, dict)
            or not _valid_id(item.get("series_id"))
            or not _valid_date(item.get("issue_date"))
            or item.get("status") not in {"missing", "overdue_missing", *(f"overdue_{state}" for state in STATES)}
            for item in missing
        )
        or not _valid_datetime(result.get("at"))
    ):
        raise ValueError("release-due returned an invalid result")
    overdue = any(item["status"].startswith("overdue_") for item in missing)
    attention = result.get("attention_required", bool(blocked or overdue))
    if not isinstance(attention, bool) or attention != bool(blocked or overdue):
        raise ValueError("release-due returned a contradictory result")
    if returncode == 3 and not attention:
        raise ValueError("release-due returned a contradictory result")
    return result


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and SAFE_ID.fullmatch(value) is not None


def _valid_date(value: object) -> bool:
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _valid_datetime(value: object) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else None
        return parsed is not None and parsed.tzinfo is not None and parsed.utcoffset() is not None
    except ValueError:
        return False


def _command(action: str) -> str:
    return " ".join((*OPERATOR, action))


def _today() -> str:
    return datetime.now(SHANGHAI).date().isoformat()


def _summary(status: dict | None = None, before: dict | None = None) -> dict:
    day = _today()
    if status is None:
        return {
            "issues": {"blocked": UNKNOWN, "missing": UNKNOWN},
            "observed_published_publication_id_delta": UNKNOWN,
            "released_edition_ids": UNKNOWN,
            "today": {
                "date": day, "expected": UNKNOWN, "published": UNKNOWN, "by_series": UNKNOWN,
            },
            "totals": {**{state: UNKNOWN for state in STATES}, "missing": UNKNOWN},
        }
    items, missing = status["items"], status["missing"]
    occurrences = status.get("expected_issues")
    if occurrences is None:
        # Compatibility with the old server: each observed series had one daily issue.
        daily_series = sorted(
            {item["series_id"] for item in items if item["issue_date"] == day}
            | {item["series_id"] for item in missing if item["issue_date"] == day}
        )
        occurrences = [{"series_id": series, "issue_key": day, "issue_date": day,
                        "issue_slot": "12:00", "release_at": f"{day}T12:00:00+08:00"}
                       for series in daily_series]
    else:
        occurrences = [item for item in occurrences if item["issue_date"] == day]
        daily_series = sorted({item["series_id"] for item in occurrences})
    totals = {state: sum(item["state"] == state for item in items) for state in STATES}
    totals["missing"] = len(missing)
    published = {}
    for series in daily_series:
        slots = []
        for occurrence in (value for value in occurrences if value["series_id"] == series):
            rows = [item for item in items if item.get("state") == "published"
                    and item.get("issue_date") == day and item.get("series_id") == series
                    and item.get("issue_key", item["issue_date"]) == occurrence["issue_key"]]
            slots.append({
                **{key: occurrence[key] for key in ("issue_key", "issue_slot", "release_at")},
                "published": len(rows),
                "body_available": len(rows) == 1 and rows[0].get("body_available") is True,
                "media_roles": rows[0].get("media_roles", []) if len(rows) == 1 else [],
            })
        good_media = all(set(slot["media_roles"]) == REQUIRED_DAILY_MEDIA for slot in slots)
        published[series] = {
            "published": sum(slot["published"] for slot in slots),
            "body_available": bool(slots) and all(slot["body_available"] for slot in slots),
            "media_roles": sorted(REQUIRED_DAILY_MEDIA) if good_media else (slots[0]["media_roles"] if len(slots) == 1 else []),
        }
        if "expected_issues" in status:
            published[series].update(expected=len(slots), slots=slots)
    before_ids = {
        item["publication_id"] for item in (before or {}).get("items", []) if item.get("state") == "published"
    }
    after_ids = {item["publication_id"] for item in items if item.get("state") == "published"}
    return {
        "issues": {
            "blocked": [
                {
                    "publication_id": item["publication_id"],
                    "series_id": item["series_id"],
                    "issue_date": item["issue_date"],
                    "state": item["state"],
                    "blocked_reasons": item.get("blocked_reasons", []),
                }
                for item in items if item.get("state") in {"blocked", "failed"}
            ],
            "missing": [
                {key: item[key] for key in ("series_id", "issue_date", "status", "issue_key", "issue_slot", "release_at") if key in item}
                for item in missing
            ],
        },
        "observed_published_publication_id_delta": sorted(after_ids - before_ids) if before is not None else UNKNOWN,
        "released_edition_ids": UNKNOWN,
        "today": {
            "date": day, "expected": len(occurrences),
            "published": sum(item["published"] for item in published.values()),
            "by_series": published,
        },
        "totals": totals,
    }


def _attention(summary: dict) -> bool:
    day = summary["today"]["date"]
    current_blocked = [item for item in summary["issues"]["blocked"] if item.get("issue_date") == day]
    return bool(current_blocked or summary["issues"]["missing"] or any(
        item.get("published") != 1 or item.get("body_available") is not True
        or set(item.get("media_roles", [])) != REQUIRED_DAILY_MEDIA
        for item in summary["today"]["by_series"].values()
    ))


def _target(status: dict, publication_id: str) -> dict:
    rows = [item for item in status["items"] if item["publication_id"] == publication_id]
    if not rows:
        return {"publication_id": publication_id, "state": "missing"}
    published = [item for item in rows if item["state"] == "published"]
    row = published[0] if published else max(rows, key=lambda item: item["edition"])
    return {
        "publication_id": publication_id,
        "edition_id": row["edition_id"],
        "series_id": row["series_id"],
        "issue_date": row["issue_date"],
        "state": row["state"],
    }


def main(argv: list[str] | None = None) -> int:
    summary = _summary()
    exit_code = 1
    errors: list[Exception] = []
    target_id: str | None = None
    target_status: dict | None = None
    try:
        args = _args(argv)
        target_id = args.target_publication_id
        if target_id is not None and not _valid_id(target_id):
            raise ValueError("target publication ID is invalid")
        identity, known_hosts = _trust(args)
        if args.status_only:
            post_status = _ssh(identity, known_hosts, _command("status"))
            exit_code = post_status.returncode
            status = _status(post_status.stdout, post_status.returncode)
            summary = _summary(status)
            summary["released_edition_ids"] = []
            target_status = status
        else:
            editorial_root = args.editorial_root or os.environ.get("AI_LAB_PUBLICATION_EDITORIAL_ROOT")
            if editorial_root:
                try:
                    from scripts.publication_editorial_remote import Remote, finalize
                except ImportError:
                    from publication_editorial_remote import Remote, finalize
                finalize(Path(editorial_root), Remote(identity, known_hosts))
            pre_status = _ssh(identity, known_hosts, _command("status"))
            exit_code = pre_status.returncode or 1
            before = _status(pre_status.stdout, pre_status.returncode, "pre-release status")
            release = None
            try:
                release = _ssh(identity, known_hosts, _command("release-due"))
                exit_code = release.returncode
            except (OSError, subprocess.SubprocessError) as exc:
                errors.append(exc)
            try:
                post_status = _ssh(identity, known_hosts, _command("status"))
                if not exit_code and post_status.returncode:
                    exit_code = post_status.returncode
                status = _status(post_status.stdout, post_status.returncode)
                summary = _summary(status, before)
                target_status = status
            except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
                errors.append(exc)
            if release is not None:
                try:
                    receipt = _release(release.stdout, release.returncode)
                    summary["released_edition_ids"] = sorted(receipt["released"])
                except (ValueError, json.JSONDecodeError) as exc:
                    errors.append(exc)
            if errors:
                if release is not None and release.returncode not in {0, 3}:
                    exit_code = release.returncode
                else:
                    exit_code = 1
            elif release is not None and target_status is not None:
                # Missing or blocked sibling series are alerts, not a cross-series release failure.
                exit_code = 0
        if summary["totals"]["published"] != UNKNOWN:
            attention = _attention(summary)
            summary["global_attention"] = attention
            if target_id is not None and target_status is not None:
                summary["target"] = _target(target_status, target_id)
                if not errors and summary["target"]["state"] == "published":
                    exit_code = 0
                elif not errors:
                    exit_code = exit_code or 3

    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
        errors.append(exc)
        exit_code = exit_code or 1
    for exc in errors:
        print(f"publication release failed: {exc}", file=sys.stderr)
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
