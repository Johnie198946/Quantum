#!/usr/bin/env python3
"""Select the next pending editorial request from the global output root."""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if not (PROJECT / "backend/services/knowledge_publication_store.py").is_file():
    PROJECT = Path.cwd().resolve()
if not (PROJECT / "backend/services/knowledge_publication_store.py").is_file():
    raise RuntimeError("publication repository root is unavailable")
OUTPUT_ROOT = Path("/Users/dengzhaoyu/.hermes/outputs/quantumn-editorial-v2")
EDITORIAL_CLIENT = PROJECT / "scripts/publication_editorial_remote.py"


def main() -> None:
    os.environ["PYTHONPATH"] = str(PROJECT)
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
