#!/usr/bin/env python3
"""Atomically deploy AI Lab's Hermes plugin and select its extract provider."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import yaml


PLUGIN_NAME = "ai-lab-capabilities"
EXTRACT_BACKEND = "ai-lab-native"
SEARCH_BACKEND = "ddgs"


def prepare_browser(hermes_home: Path) -> None:
    """Provision Hermes' existing headless backend before serving requests."""
    if hermes_home.stat().st_uid != os.geteuid():
        raise RuntimeError("run_browser_setup_as_hermes_home_owner")
    # Match the deployed Hermes 0.21.1 browser contract, without floating npx
    # downloads or npm lifecycle scripts on a user's first travel request.
    env = {key: os.environ[key] for key in
           ("HOME", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "LANG") if key in os.environ}
    env.update(PATH=os.pathsep.join([str(hermes_home / "node/bin"), os.defpath]),
               XDG_CACHE_HOME=str(hermes_home / "cache"),
               npm_config_cache=str(hermes_home / "cache/npm"))
    runtime = hermes_home / "browser-runtime"
    subprocess.run(["npm", "install", "--prefix", str(runtime), "--ignore-scripts",
                    "--no-audit", "--no-fund", "agent-browser@0.26.0"],
                   env=env, check=True, timeout=240)
    binary = str(runtime / "node_modules/.bin/agent-browser")
    subprocess.run([binary, "install"], env=env, check=True, timeout=480)
    subprocess.run([binary, "--version"], env=env, check=True, timeout=15)
    # agent-browser 0.26 uses Chrome for Testing, not Playwright's cache.
    # Hermes 0.21.1 needs an explicit executable to recognize that layout.
    browsers = Path(env.get("HOME") or Path.home()) / ".agent-browser/browsers"
    candidates = sorted(browsers.glob("chrome-*/chrome"),
                        key=lambda p: tuple(int(v) for v in p.parent.name.removeprefix("chrome-").split(".")))
    if not candidates:
        raise RuntimeError("server_chrome_executable_missing")
    subprocess.run([str(candidates[-1]), "--version"], env=env, check=True, timeout=15)
    temporary = runtime / f".chrome-{os.getpid()}"
    try:
        temporary.symlink_to(candidates[-1])
        os.replace(temporary, runtime / "chrome")
    finally:
        temporary.unlink(missing_ok=True)


def _document(path: Path) -> dict:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Hermes config root must be a mapping: {path}")
    return payload


def _atomic_yaml(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(document, handle, allow_unicode=True, sort_keys=False)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def configure(hermes_home: Path, plugin_source: Path, backup_root: Path) -> dict[str, str]:
    required = {
        "plugin.yaml", "__init__.py", "capability_router.py",
        "native_extract_provider.py", "requirements-html.txt",
    }
    missing = sorted(name for name in required if not (plugin_source / name).is_file())
    if missing:
        raise ValueError("Plugin source is incomplete: " + ", ".join(missing))

    config_path = hermes_home / "config.yaml"
    plugin_root = hermes_home / "plugins"
    destination = plugin_root / PLUGIN_NAME
    if destination.name != PLUGIN_NAME:
        raise ValueError(f"Unsafe plugin destination: {destination}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_root / f"hermes-web-extract-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    if config_path.exists():
        shutil.copy2(config_path, backup / "config.yaml")
    if destination.exists():
        shutil.copytree(destination, backup / PLUGIN_NAME)

    plugin_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=PLUGIN_NAME + ".", dir=plugin_root))
    previous = plugin_root / f".{PLUGIN_NAME}.previous-{os.getpid()}"
    try:
        shutil.copytree(
            plugin_source,
            temporary,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        if destination.exists():
            os.replace(destination, previous)
        os.replace(temporary, destination)
        if previous.exists():
            shutil.rmtree(previous)
    except Exception:
        if not destination.exists() and previous.exists():
            os.replace(previous, destination)
        raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)

    document = _document(config_path)
    plugins = document.setdefault("plugins", {})
    if not isinstance(plugins, dict):
        raise ValueError("Hermes plugins config must be a mapping")
    enabled = plugins.get("enabled") or []
    if not isinstance(enabled, list) or not all(isinstance(item, str) for item in enabled):
        raise ValueError("Hermes plugins.enabled must be a string list")
    if PLUGIN_NAME not in enabled:
        enabled.append(PLUGIN_NAME)
    plugins["enabled"] = enabled

    web = document.setdefault("web", {})
    if not isinstance(web, dict):
        raise ValueError("Hermes web config must be a mapping")
    web["search_backend"] = SEARCH_BACKEND
    web["extract_backend"] = EXTRACT_BACKEND
    # The Bridge never grants terminal to iOS tenant agents.  Keep Hermes on
    # its built-in task-isolated browser tools by leaving the backend unset;
    # ``backend: off`` disables browser_navigate as well and silently defeats
    # the narrow WeChat verification-page fallback.
    browser = document.setdefault("browser", {})
    if not isinstance(browser, dict):
        raise ValueError("Hermes browser config must be a mapping")
    browser.pop("backend", None)
    _atomic_yaml(config_path, document)
    return {
        "backup": str(backup),
        "plugin": str(destination),
        "config": str(config_path),
        "search_backend": SEARCH_BACKEND,
        "extract_backend": EXTRACT_BACKEND,
        "browser_backend": "builtin",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hermes-home", type=Path, required=True)
    parser.add_argument("--plugin-source", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--prepare-browser", action="store_true",
                        help="Install the server headless browser; does not restart services")
    args = parser.parse_args()
    if args.prepare_browser:
        prepare_browser(args.hermes_home.expanduser().resolve())
    result = configure(
        args.hermes_home.expanduser().resolve(),
        args.plugin_source.expanduser().resolve(),
        args.backup_root.expanduser().resolve(),
    )
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
