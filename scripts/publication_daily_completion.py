#!/usr/bin/env python3
"""Emit one truthful end-of-day Quantumn publication receipt."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
STATUS_CLIENT = Path(__file__).resolve().with_name("publication_release_remote.py")
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
    declared_expected = 0
    for series, item in by_series.items():
        count = item.get("expected", 1) if isinstance(item, dict) else None
        if type(count) is not int or count < 1:
            failures.append(series)
            continue
        declared_expected += count
        roles = set(item.get("media_roles", [])) if isinstance(item, dict) else set()
        if (not isinstance(item, dict) or item.get("published") != count
                or item.get("body_available") is not True or roles != REQUIRED_MEDIA):
            failures.append(series)
        slots = item.get("slots") if isinstance(item, dict) else None
        if slots is not None and (
            not isinstance(slots, list) or len(slots) != count
            or any(not isinstance(slot, dict) or slot.get("published") != 1
                   or slot.get("body_available") is not True
                   or set(slot.get("media_roles", [])) != REQUIRED_MEDIA for slot in slots)
            or len({slot.get("issue_key") for slot in slots if isinstance(slot, dict)}) != count
        ):
            failures.append(series)
    complete = (
        type(expected) is int
        and expected >= 0
        and expected == declared_expected
        and type(published) is int
        and published == expected
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
            f"今日计划的 {expected} 期连载均已发布，正文及双封面、三张正文插图校验通过（{today.get('date')}）。"
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
