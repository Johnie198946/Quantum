#!/usr/bin/env python3
"""Root-owned executor for Quantum tenant Coder commands.

The service accepts local Unix-socket requests from the unprivileged Bridge,
validates the server-derived tenant path, and runs the command in a disposable
networkless container with only that tenant workspace mounted writable.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import selectors
import shutil
import socket
import subprocess
import threading
import time
import uuid

SOCKET_PATH = Path("/run/quantum-tenant-coder/runner.sock")
SANDBOX_ROOT = Path("/opt/ai-lab-platform/data/hermes-sandboxes").resolve()
IMAGE = os.environ.get("QUANTUM_CODER_IMAGE", "ai-lab-platform-api:offline")
_NAMESPACE = re.compile(r"^[0-9a-f]{20}$")
_MAX_OUTPUT = 1_000_000


def validated_workspace(request: dict) -> Path:
    tenant = str(request.get("tenant_namespace") or "")
    user = str(request.get("user_namespace") or "")
    if not _NAMESPACE.fullmatch(tenant) or not _NAMESPACE.fullmatch(user):
        raise ValueError("invalid_tenant_namespace")
    expected = SANDBOX_ROOT / "tenants" / tenant / "users" / user / "workspace"
    supplied = Path(str(request.get("workspace") or ""))
    if not supplied.is_absolute() or supplied.is_symlink() or not supplied.is_dir():
        raise ValueError("invalid_tenant_workspace")
    resolved = supplied.resolve(strict=True)
    if resolved != expected or resolved.is_symlink():
        raise ValueError("tenant_workspace_escape_denied")
    check = SANDBOX_ROOT
    for part in expected.relative_to(SANDBOX_ROOT).parts:
        check = check / part
        if check.is_symlink():
            raise ValueError("tenant_workspace_symlink_forbidden")
    return resolved


def docker_command(request: dict, workspace: Path, name: str) -> list[str]:
    command = str(request.get("command") or "").strip()
    if not command or len(command.encode("utf-8")) > 32_000:
        raise ValueError("invalid_command")
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("docker_unavailable")
    owner = workspace.stat()
    if owner.st_uid == 0:
        raise ValueError("tenant_workspace_must_be_unprivileged")
    return [
        docker, "run", "--rm", "--name", name,
        "--network=none", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--pids-limit=256",
        "--memory=1g", "--cpus=1", "--user", f"{owner.st_uid}:{owner.st_gid}",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=268435456",
        "--tmpfs", "/home:rw,nosuid,nodev,size=67108864",
        "--tmpfs", "/app:rw,nosuid,nodev,noexec,size=16777216",
        "-e", "HOME=/home", "-e", "TMPDIR=/tmp",
        "-v", f"{workspace}:/workspace:rw",
        "-w", "/workspace", "--entrypoint", "/bin/sh", IMAGE, "-lc", command,
    ]


def execute(request: dict) -> dict:
    workspace = validated_workspace(request)
    timeout = max(1, min(int(request.get("timeout") or 180), 300))
    name = "quantum-coder-" + uuid.uuid4().hex[:16]
    command = docker_command(request, workspace, name)
    started = time.monotonic()
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )
    selector = selectors.DefaultSelector()
    assert process.stdout is not None
    selector.register(process.stdout, selectors.EVENT_READ)
    output = bytearray()
    timed_out = False
    truncated = False
    try:
        while process.poll() is None:
            if time.monotonic() - started > timeout:
                timed_out = True
                break
            for key, _ in selector.select(timeout=0.2):
                chunk = os.read(key.fd, 64 * 1024)
                if not chunk:
                    continue
                remaining = _MAX_OUTPUT - len(output)
                output.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    truncated = True
                    break
            if truncated:
                break
        if timed_out or truncated:
            subprocess.run(
                [command[0], "rm", "-f", name], capture_output=True,
                timeout=15, stdin=subprocess.DEVNULL,
            )
            process.kill()
        else:
            tail = process.stdout.read(_MAX_OUTPUT - len(output) + 1)
            if len(tail) > _MAX_OUTPUT - len(output):
                truncated = True
                tail = tail[: _MAX_OUTPUT - len(output)]
            output.extend(tail)
        return_code = process.wait(timeout=15)
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
    return {
        "success": return_code == 0 and not timed_out and not truncated,
        "exit_code": return_code,
        "output": output.decode("utf-8", errors="replace"),
        "timed_out": timed_out,
        "truncated": truncated,
        "isolation": "tenant_container_v1",
    }


def handle(connection: socket.socket) -> None:
    try:
        payload = bytearray()
        while b"\n" not in payload and len(payload) <= 65_536:
            chunk = connection.recv(8192)
            if not chunk:
                break
            payload.extend(chunk)
        if len(payload) > 65_536:
            raise ValueError("request_too_large")
        request = json.loads(bytes(payload).split(b"\n", 1)[0])
        if not isinstance(request, dict):
            raise ValueError("invalid_request")
        response = execute(request)
    except Exception as exc:
        response = {"success": False, "error": str(exc)[:500]}
    connection.sendall(json.dumps(response, ensure_ascii=False).encode("utf-8"))
    connection.close()


def serve() -> None:
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    SOCKET_PATH.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(SOCKET_PATH))
    os.chmod(SOCKET_PATH, 0o660)
    server.listen(16)
    try:
        while True:
            connection, _ = server.accept()
            threading.Thread(target=handle, args=(connection,), daemon=True).start()
    finally:
        server.close()
        SOCKET_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    serve()
