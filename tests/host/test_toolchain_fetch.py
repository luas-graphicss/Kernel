import io
import tarfile
import urllib.error
from pathlib import Path

import pytest
from kernel_tool.outcome import CheckError, InfrastructureError
from kernel_tool.toolchain import fetch
from kernel_tool.toolchain.fetch import COMPLETE_MARKER, ensure_artifact, sha256_file
from kernel_tool.toolchain.lock import Artifact

ARCHIVE_NAME = "bundle-1.0.tar.gz"


def build_archive(path: Path, members: dict[str, bytes]) -> str:
    with tarfile.open(path, "w:gz") as bundle:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            bundle.addfile(info, io.BytesIO(content))
    return sha256_file(path)


def make_artifact(sha256: str, include: tuple[str, ...] = ()) -> Artifact:
    return Artifact(
        name="bundle",
        version="1.0",
        url=f"https://example.org/{ARCHIVE_NAME}",
        sha256=sha256,
        size=0,
        root="bundle-1.0",
        license="MIT",
        include=include,
    )


def cached_archive(cache_dir: Path) -> Path:
    archives = cache_dir / "archives"
    archives.mkdir(parents=True)
    return archives / ARCHIVE_NAME


def test_ensure_artifact_unpacks_only_included_paths(tmp_path: Path) -> None:
    sha256 = build_archive(
        cached_archive(tmp_path),
        {
            "bundle-1.0/py/core.c": b"core",
            "bundle-1.0/pyproject.toml": b"unrelated",
            "bundle-1.0/docs/index.md": b"docs",
        },
    )

    root = ensure_artifact(make_artifact(sha256, include=("py",)), tmp_path)

    assert (root / "py" / "core.c").read_bytes() == b"core"
    assert not (root / "pyproject.toml").exists()
    assert not (root / "docs").exists()
    assert (root / COMPLETE_MARKER).read_text(encoding="ascii").strip() == sha256


def test_ensure_artifact_reuses_a_complete_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha256 = build_archive(cached_archive(tmp_path), {"bundle-1.0/tool": b"tool"})
    artifact = make_artifact(sha256)
    ensure_artifact(artifact, tmp_path)
    cached_archive_path = tmp_path / "archives" / ARCHIVE_NAME
    cached_archive_path.unlink()

    def fail_download(*_arguments: object, **_options: object) -> None:
        raise AssertionError("a complete extraction must not download again")

    monkeypatch.setattr(fetch.urllib.request, "urlopen", fail_download)

    assert ensure_artifact(artifact, tmp_path) == tmp_path / "tools" / "bundle-1.0"


def test_archive_with_wrong_hash_is_downloaded_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_archive(cached_archive(tmp_path), {"bundle-1.0/tool": b"tampered"})
    requested: list[str] = []

    def unreachable(url: str, **_options: object) -> None:
        requested.append(url)
        raise urllib.error.URLError("network is unreachable")

    monkeypatch.setattr(fetch.urllib.request, "urlopen", unreachable)

    with pytest.raises(InfrastructureError, match="network is unreachable"):
        ensure_artifact(make_artifact("0" * 64), tmp_path)

    assert requested == [f"https://example.org/{ARCHIVE_NAME}"]
    assert not (tmp_path / "archives" / ARCHIVE_NAME).exists()


def test_downloaded_archive_must_match_the_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def serve_unexpected_content(_url: str, **_options: object) -> io.BytesIO:
        return io.BytesIO(b"not the pinned archive")

    monkeypatch.setattr(fetch.urllib.request, "urlopen", serve_unexpected_content)

    with pytest.raises(CheckError, match="does not match the lock"):
        ensure_artifact(make_artifact("0" * 64), tmp_path)

    assert list((tmp_path / "archives").iterdir()) == []


def test_archive_escaping_the_destination_is_rejected(tmp_path: Path) -> None:
    sha256 = build_archive(cached_archive(tmp_path), {"../escaped.txt": b"outside"})

    with pytest.raises(CheckError, match="unsafe or corrupt archive"):
        ensure_artifact(make_artifact(sha256), tmp_path)

    assert not (tmp_path / "escaped.txt").exists()
    assert not (tmp_path / "tools" / "escaped.txt").exists()
