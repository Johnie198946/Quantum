#!/usr/bin/env python3
"""Emit one truthful end-of-day Quantumn publication receipt."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path("/Users/dengzhaoyu/Projects/quantum-2.0-publication-main")
STATUS_CLIENT = PROJECT / "scripts/publication_release_remote.py"
SERIES = ("ai-history", "ai-practice", "concept-fables", "ai-toolkit")
REQUIRED_MEDIA = {
    "shelf_cover", "reader_cover", "illustration_01", "illustration_02", "illustration_03",
}


def evaluate(summary: dict) -> tuple[dict, int]:
    raw_today = summary.get("today")
    raw_issues = summary.get("issues")
    today: dict = raw_today if isinstance(raw_today, dict) else {}
    issues: dict = raw_issues if isinstance(raw_issues, dict) else {}
    expected = today.get("expected")
    published = today.get("published")
    missing = issues.get("missing") if isinstance(issues.get("missing"), list) else []
    by_series = today.get("by_series") if isinstance(today.get("by_series"), dict) else {}
    failures = []
    for series in SERIES:
        item = by_series.get(series)
        roles = set(item.get("media_roles", [])) if isinstance(item, dict) else set()
        if (not isinstance(item, dict) or item.get("published") != 1
                or item.get("body_available") is not True or roles != REQUIRED_MEDIA):
            failures.append(series)
    complete = (
        isinstance(expected, int)
        and expected == len(SERIES)
        and published == len(SERIES)
        and not missing
        and not failures
        and not summary.get("global_attention")
    )
    receipt = {
        "status": "complete" if complete else "incomplete",
        "date": today.get("date"),
        "expected": expected,
        "published": published,
        "by_series": by_series,
        "missing": missing,
        "bot_message": (
            f"今日四个每日连载均已发布，正文及双封面、三张正文插图校验通过（{today.get('date')}）。"
            if complete else
            f"今日连载验收失败，未通过正文或五媒体检查：{', '.join(failures) or '全局状态异常'}；请勿发送完成通知。"
        ),
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
