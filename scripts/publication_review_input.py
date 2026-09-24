#!/usr/bin/env python3
"""Select the next pending editorial request from the global output root."""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT = Path("/Users/dengzhaoyu/Projects/quantum-2.0-publication-main")
OUTPUT_ROOT = Path("/Users/dengzhaoyu/.hermes/outputs/quantumn-editorial-v2")
EDITORIAL_CLIENT = Path("/Users/dengzhaoyu/.hermes/scripts/publication_editorial_remote.py")


def main() -> None:
    current = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = str(PROJECT) + (":" + current if current else "")
    os.execv(
        sys.executable,
        [
            sys.executable,
            str(EDITORIAL_CLIENT),
            "review-input",
            "--root",
            str(OUTPUT_ROOT),
        ],
    )


if __name__ == "__main__":
    main()
