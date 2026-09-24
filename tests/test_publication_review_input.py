from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publication_review_input.py"


def load_module():
    spec = importlib.util.spec_from_file_location("publication_review_input", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_review_input_uses_global_output_root(monkeypatch):
    module = load_module()
    captured = {}

    def fake_execv(executable, argv):
        captured["executable"] = executable
        captured["argv"] = argv
        raise RuntimeError("exec intercepted")

    monkeypatch.setattr(module.os, "execv", fake_execv)

    try:
        module.main()
    except RuntimeError as exc:
        assert str(exc) == "exec intercepted"
    else:
        raise AssertionError("main did not exec the editorial client")

    assert captured["argv"][-2:] == ["--root", str(module.OUTPUT_ROOT)]
    assert "active-review-root.txt" not in SCRIPT.read_text(encoding="utf-8")
