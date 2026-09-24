from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publication_daily_completion.py"


def load_module():
    spec = importlib.util.spec_from_file_location("publication_daily_completion", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_complete_requires_all_expected_series_and_no_attention():
    module = load_module()
    receipt, code = module.evaluate({
        "global_attention": False,
        "today": {"date": "2026-09-24", "expected": 4, "published": 4, "by_series": {"a": 1}},
        "issues": {"missing": []},
    })
    assert code == 0
    assert receipt["status"] == "complete"


def test_missing_series_fails_closed():
    module = load_module()
    receipt, code = module.evaluate({
        "global_attention": True,
        "today": {"date": "2026-09-24", "expected": 4, "published": 3, "by_series": {}},
        "issues": {"missing": [{"series_id": "ai-practice"}]},
    })
    assert code == 2
    assert receipt["status"] == "incomplete"
    assert receipt["missing"] == [{"series_id": "ai-practice"}]
