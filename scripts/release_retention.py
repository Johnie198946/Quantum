"""Retire old immutable source releases into recoverable private archives.

Never follows shared-data links, removes archives, or prunes Docker images.
Deployment holds the existing update lock while applying this policy.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile
import time


def retirement_candidates(root: Path, protected: set[Path], *, now: float) -> list[Path]:
    releases = []
    for path in root.iterdir():
        match = re.fullmatch(r"ai-lab-platform-([0-9a-f]{12})\.[A-Za-z0-9]+", path.name)
        marker = path / ".deployed-sha"
        if not match or path.is_symlink() or not path.is_dir() or not marker.is_file() or marker.is_symlink():
            continue
        sha = marker.read_text().strip()
        if re.fullmatch(r"[0-9a-f]{40}", sha) and sha.startswith(match[1]):
            releases.append(path)
    releases.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    protected = {p.resolve() for p in protected} | set(releases[:7])
    return [p for p in releases if p not in protected and now - p.stat().st_mtime >= 14 * 86400]


def active_paths() -> set[Path]:
    protected = set()
    for process in Path("/proc").glob("[0-9]*"):
        for link in [process / "cwd", process / "exe", * (process / "fd").glob("*")]:
            try:
                target = Path(os.readlink(link))
                protected.update([target, *target.parents])
            except OSError:
                pass
    ids = subprocess.check_output(["docker", "ps", "-q"], text=True).split()
    if ids:
        for container in json.loads(subprocess.check_output(["docker", "inspect", *ids], text=True)):
            for mount in container["Mounts"]:
                target = Path(mount["Source"]).resolve()
                protected.update([target, *target.parents])
    return protected


def retirement_headroom(path: Path) -> int:
    """Reserve for an incompressible tar plus verification without following links.

    Retirement must be able to recover below the deployment's 5 GiB gate.
    Keep 2 GiB for the running service and conservatively budget twice apparent
    file bytes plus 64 KiB per member (headers, gzip/PAX overhead and metadata).
    """
    file_bytes = 0
    members = 1
    for directory, children, files in os.walk(path, followlinks=False):
        members += len(children) + len(files)
        for name in files:
            info = (Path(directory) / name).lstat()
            if stat.S_ISREG(info.st_mode):
                file_bytes += info.st_size
    archive_budget = max(256 * 1024**2, file_bytes * 2 + members * 64 * 1024)
    return 2 * 1024**3 + archive_budget


def archive_release(path: Path, destination: Path) -> Path:
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    archive = destination / (path.name + ".tar.gz")
    temporary = destination / (path.name + f".{os.getpid()}.tmp")
    # Exclusive creation prevents overwriting a previous recovery archive.
    if archive.exists():
        raise FileExistsError(archive)
    try:
        with temporary.open("xb") as output:
            os.chmod(temporary, 0o600)
            with tarfile.open(fileobj=output, mode="w:gz", dereference=False) as tar:
                tar.add(path, arcname=path.name)
            output.flush()
            os.fsync(output.fileno())
        # Read every compressed member before removing the original source.
        with tarfile.open(temporary, "r:gz") as tar:
            for member in tar:
                if member.isfile():
                    with tar.extractfile(member) as source:
                        while source.read(1024 * 1024):
                            pass
        os.link(temporary, archive)
        fd = os.open(destination, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        shutil.rmtree(path)
        return archive
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--archive-dir", type=Path, required=True)
    parser.add_argument("--protect", type=Path, action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.root.is_symlink() or args.root.resolve() != args.root:
        parser.error("release root must be a physical absolute directory")
    if args.apply:
        # Only the updater may mutate release directories under its shared lock.
        import fcntl
        fd = 9
        if os.readlink(f"/proc/self/fd/{fd}") != "/run/lock/ai-lab-platform-update.lock":
            parser.error("apply requires the inherited deployment lock")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    candidates = retirement_candidates(args.root, set(args.protect) | active_paths(), now=time.time())
    print(json.dumps({"retention_candidates": [p.name for p in candidates], "apply": args.apply}))
    if args.apply:
        for path in candidates:
            if shutil.disk_usage(args.archive_dir.parent).free < retirement_headroom(path):
                raise RuntimeError("insufficient headroom for recoverable retirement")
            print(json.dumps({"retired": path.name, "archive": str(archive_release(path, args.archive_dir))}))


if __name__ == "__main__":
    main()
