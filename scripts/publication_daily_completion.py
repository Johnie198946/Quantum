#!/usr/bin/env python3
"""Emit one truthful end-of-day Quantumn publication receipt."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path("/Users/dengzhaoyu/Projects/quantum-2.0-publication-main")
STATUS_CLIENT = Path("/Users/dengzhaoyu/.hermes/scripts/publication_release_remote.py")


def evaluate(summary: dict) -> tuple[dict, int]:
    raw_today = summary.get("today")
    raw_issues = summary.get("issues")
    today: dict = raw_today if isinstance(raw_today, dict) else {}
    issues: dict = raw_issues if isinstance(raw_issues, dict) else {}
    expected = today.get("expected")
    published = today.get("published")
    missing = issues.get("missing") if isinstance(issues.get("missing"), list) else []
    complete = (
        isinstance(expected, int)
        and expected > 0
        and published == expected
        and not missing
        and not summary.get("global_attention")
    )
    receipt = {
        "status": "complete" if complete else "incomplete",
        "date": today.get("date"),
        "expected": expected,
        "published": published,
        "by_series": today.get("by_series", {}),
        "missing": missing,
    }
    return receipt, 0 if complete else 2


def main() -> int:
    completed = subprocess.run(
        [sys.executable, str(STATUS_CLIENT), "--status-only"],
        cwd=PROJECT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        print(json.dumps({
            "status": "status_check_failed",
            "exit_code": completed.returncode,
            "stderr": completed.stderr.strip(),
        }, ensure_ascii=False, sort_keys=True))
        return completed.returncode
    try:
        summary = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        print(json.dumps({"status": "status_check_invalid_output"}, sort_keys=True))
        return 1
    receipt, code = evaluate(summary)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
