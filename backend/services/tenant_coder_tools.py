"""Tenant-scoped coding tools for governed workflow Coder nodes.

File operations are confined to the authenticated tenant/user workspace. Shell
commands are delegated to the root-owned runner, which exposes only that
workspace to a networkless, capability-free container.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import socket
import tempfile
from typing import Any

from backend.services.tenant_hermes_sandbox import TenantHermesSandbox

_MAX_TEXT_BYTES = 2_000_000
_MAX_RESULTS = 200
_RUNNER_SOCKET = Path("/run/quantum-tenant-coder/runner.sock")


def workspace_root(sandbox: TenantHermesSandbox) -> Path:
    root = sandbox.root / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    return root


def resolve_workspace_path(
    sandbox: TenantHermesSandbox, raw_path: str, *, create_parent: bool = False
) -> Path:
    """Resolve one relative path and reject traversal and symlink components."""
    relative = Path(str(raw_path or "").strip())
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("tenant_workspace_relative_path_required")
    root = workspace_root(sandbox).resolve(strict=True)
    current = root
    for part in relative.parts:
        if part in {"", "."}:
            continue
        current = current / part
        if current.is_symlink():
            raise ValueError("tenant_workspace_symlink_forbidden")
    if create_parent:
        current.parent.mkdir(parents=True, exist_ok=True)
        check = root
        for part in current.relative_to(root).parts[:-1]:
            check = check / part
            if check.is_symlink():
                raise ValueError("tenant_workspace_symlink_forbidden")
    try:
        current.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise ValueError("tenant_workspace_escape_denied") from exc
    return current


def read_text(sandbox: TenantHermesSandbox, path: str) -> dict[str, Any]:
    target = resolve_workspace_path(sandbox, path)
    if not target.is_file() or target.is_symlink():
        raise FileNotFoundError("tenant_workspace_file_not_found")
    data = target.read_bytes()
    if len(data) > _MAX_TEXT_BYTES:
        raise ValueError("tenant_workspace_file_too_large")
    return {"path": str(Path(path)), "content": data.decode("utf-8", errors="replace")}


def write_text(sandbox: TenantHermesSandbox, path: str, content: str) -> dict[str, Any]:
    raw = str(content).encode("utf-8")
    if len(raw) > _MAX_TEXT_BYTES:
        raise ValueError("tenant_workspace_file_too_large")
    target = resolve_workspace_path(sandbox, path, create_parent=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return {"path": str(Path(path)), "bytes": len(raw)}


def patch_text(
    sandbox: TenantHermesSandbox, path: str, old_string: str, new_string: str
) -> dict[str, Any]:
    current = read_text(sandbox, path)["content"]
    count = current.count(old_string)
    if not old_string or count != 1:
        raise ValueError("tenant_workspace_patch_requires_unique_match")
    result = write_text(sandbox, path, current.replace(old_string, new_string, 1))
    return {**result, "replacements": 1}


def search_text(
    sandbox: TenantHermesSandbox, pattern: str, *, file_glob: str = "*"
) -> dict[str, Any]:
    expression = re.compile(str(pattern))
    root = workspace_root(sandbox)
    matches: list[dict[str, Any]] = []
    for candidate in root.rglob(file_glob or "*"):
        if len(matches) >= _MAX_RESULTS:
            break
        if candidate.is_symlink() or not candidate.is_file():
            continue
        try:
            candidate.resolve(strict=True).relative_to(root.resolve(strict=True))
            if candidate.stat().st_size > _MAX_TEXT_BYTES:
                continue
            for line_number, line in enumerate(
                candidate.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if expression.search(line):
                    matches.append({
                        "path": candidate.relative_to(root).as_posix(),
                        "line": line_number,
                        "text": line[:1000],
                    })
                    if len(matches) >= _MAX_RESULTS:
                        break
        except OSError:
            continue
    return {"matches": matches, "truncated": len(matches) >= _MAX_RESULTS}


def run_command(
    sandbox: TenantHermesSandbox, command: str, *, timeout: int = 180
) -> dict[str, Any]:
    command = str(command or "").strip()
    if not command or len(command.encode("utf-8")) > 32_000:
        raise ValueError("tenant_workspace_command_invalid")
    timeout = max(1, min(int(timeout), 300))
    request = {
        "workspace": str(workspace_root(sandbox).resolve(strict=True)),
        "tenant_namespace": sandbox.tenant_namespace,
        "user_namespace": sandbox.user_namespace,
        "command": command,
        "timeout": timeout,
    }
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout + 15)
    try:
        sock.connect(str(_RUNNER_SOCKET))
        sock.sendall(json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = sock.recv(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > 2_000_000:
                raise RuntimeError("tenant_coder_runner_response_too_large")
            chunks.append(chunk)
    finally:
        sock.close()
    response = json.loads(b"".join(chunks).decode("utf-8"))
    if not isinstance(response, dict):
        raise RuntimeError("tenant_coder_runner_invalid_response")
    return response
