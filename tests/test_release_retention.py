import os
from pathlib import Path
import tarfile

from scripts.release_retention import retirement_candidates, archive_release


def test_retention_protects_latest_active_and_unrecognized(tmp_path):
    releases = []
    for i in range(12):
        sha = f"{i:040x}"
        path = tmp_path / f"ai-lab-platform-{sha[:12]}.r{i}"
        path.mkdir()
        (path / ".deployed-sha").write_text(sha)
        os.utime(path, (i, i))
        releases.append(path)
    unknown = tmp_path / "user-data"
    unknown.mkdir()
    linked = tmp_path / "ai-lab-platform-ffffffffffff.link"
    linked.symlink_to(unknown)
    result = retirement_candidates(tmp_path, {releases[0]}, now=20 * 86400)
    assert result == list(reversed(releases[1:5]))
    assert not retirement_candidates(tmp_path, set(), now=86400)


def test_archive_preserves_shared_links_and_is_recoverable(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "user-data").write_text("must remain")
    (release / "data").symlink_to(shared)
    (release / "code.py").write_text("source")
    archive = archive_release(release, tmp_path / "archives")
    assert not release.exists()
    assert (shared / "user-data").read_text() == "must remain"
    with tarfile.open(archive) as tar:
        assert tar.getmember("release/data").issym()
        assert not any("user-data" in member.name for member in tar)
        assert tar.extractfile("release/code.py").read() == b"source"
    assert archive.stat().st_mode & 0o777 == 0o600
