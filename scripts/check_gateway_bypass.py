#!/usr/bin/env python3
"""Fail closed on QCP authority and dispatcher bypass patterns."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = (ROOT / "backend", ROOT / "scripts", ROOT / "frontend/src", ROOT / "ios/AIPlatformApp")
SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".swift"}
ALLOWED_EXECUTION_FILES = {
    ROOT / "backend/services/capability_catalog.py",
    ROOT / "backend/services/capability_gateway.py",
}
CONFIRMED_TRUE = re.compile(r"(?:['\"]confirmed['\"]|\bconfirmed)\s*[:=]\s*(?:true|True)\b")
DIRECT_EXECUTION = re.compile(r"\bexecute_verified_capability\s*\(")


def scan() -> list[dict[str, object]]:
    violations: list[dict[str, object]] = []
    for base in RUNTIME_ROOTS:
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            relative = path.relative_to(ROOT).as_posix()
            for number, line in enumerate(text.splitlines(), 1):
                if CONFIRMED_TRUE.search(line) and (
                    "capabil" in text.casefold() or "qcp" in text.casefold()
                ):
                    violations.append({
                        "kind": "boolean_confirmation_authority",
                        "path": relative,
                        "line": number,
                    })
                if path not in ALLOWED_EXECUTION_FILES and DIRECT_EXECUTION.search(line):
                    violations.append({
                        "kind": "direct_verified_dispatch",
                        "path": relative,
                        "line": number,
                    })
    return violations


def main() -> int:
    violations = scan()
    print(json.dumps({"violations": violations, "count": len(violations)}, indent=2))
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
