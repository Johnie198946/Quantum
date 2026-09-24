#!/usr/bin/env python3
"""Provision the pinned resident JEV model and YAML settings."""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import os
from pathlib import Path
import platform
import subprocess
import sys
from urllib.request import urlopen

REPO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
ARTIFACTS = {
    "arm64": (
        "onnx/model_qint8_arm64.onnx",
        "783fea82d71a58179b830a4dbd2d58447e640609e98eedf9ffa12622d375a672",
    ),
    "x86_64": (
        "onnx/model_quint8_avx2.onnx",
        "98a01d88b7de996cdea58c32ca71208c09968d143798814b2ea09d3439dc334f",
    ),
}
TOKENIZER = (
    "tokenizer.json",
    "2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8",
)
DEPENDENCIES = {
    "numpy": "2.4.3",
    "onnxruntime": "1.27.0",
    "tokenizers": "0.23.1",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(home: Path, relative: str, expected: str) -> Path:
    destination = home / "models" / "jev-multilingual-minilm" / relative
    if destination.is_file() and sha256(destination) == expected:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.part")
    url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{relative}?download=true"
    try:
        with urlopen(url, timeout=120) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        actual = sha256(temporary)
        if actual != expected:
            raise RuntimeError(f"hash mismatch for {relative}: {actual}")
        temporary.chmod(0o644)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def set_config(home: Path, key: str, value: str) -> None:
    hermes = Path(sys.executable).with_name("hermes")
    if not hermes.is_file():
        raise RuntimeError(f"Hermes CLI not found beside Python: {hermes}")
    env = dict(os.environ, HERMES_HOME=str(home))
    subprocess.run([str(hermes), "config", "set", key, value], check=True, env=env)


def verify_dependencies() -> None:
    mismatches: list[str] = []
    for package, expected in DEPENDENCIES.items():
        try:
            actual = metadata.version(package)
        except metadata.PackageNotFoundError:
            actual = "missing"
        if actual != expected:
            mismatches.append(f"{package}={actual} (expected {expected})")
    if mismatches:
        raise SystemExit(
            "resident JEV dependency gate failed: "
            + ", ".join(mismatches)
            + ". Install the approved Hermes environment lock; this provisioner "
            "never mutates the shared runtime environment."
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hermes-home", default=os.environ.get("HERMES_HOME", "~/.hermes"))
    parser.add_argument("--skip-config", action="store_true")
    parser.add_argument("--decision-provider", default="")
    parser.add_argument("--decision-model", default="")
    parser.add_argument("--decision-api-mode", default="")
    args = parser.parse_args()

    machine = platform.machine().lower()
    if machine in {"aarch64", "arm64"}:
        machine = "arm64"
    if machine not in ARTIFACTS:
        raise SystemExit(f"Unsupported architecture: {machine}")
    home = Path(args.hermes_home).expanduser().resolve()

    verify_dependencies()

    model = download(home, *ARTIFACTS[machine])
    tokenizer = download(home, *TOKENIZER)

    if not args.skip_config:
        prefix = "plugins.entries.ai-lab-capabilities.settings.jev"
        for key, value in {
            f"{prefix}.mode": "resident",
            f"{prefix}.shortlist_per_kind": "20",
            f"{prefix}.fast_abstain_similarity": "0.36",
            f"{prefix}.provider_timeout_seconds": "7.0",
            f"{prefix}.embedding_threads": "4",
        }.items():
            set_config(home, key, value)
        for name, value in {
            "provider": args.decision_provider,
            "model": args.decision_model,
            "api_mode": args.decision_api_mode,
        }.items():
            if value:
                set_config(home, f"auxiliary.jev_selection.{name}", value)

    print(f"JEV_RESIDENT_READY model={model} tokenizer={tokenizer} revision={REVISION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
