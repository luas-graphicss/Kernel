import shutil
import subprocess
from pathlib import Path

import pytest

from kernel_tool.outcome import CheckError
from kernel_tool.release.checksums import (
    CHECKSUMS_FILE,
    SIGNATURE_FILE,
    checksum_problems,
    read_checksums,
    write_checksums,
)
from kernel_tool.release.signing import NAMESPACE, sign_bundle, verify_bundle

IDENTITY = "release@example.org"
needs_signer = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="needs ssh-keygen")


def bundle_in(directory: Path) -> Path:
    bundle = directory / "bundle"
    (bundle / "licenses").mkdir(parents=True)
    (bundle / "kernel.elf").write_bytes(b"kernel")
    (bundle / "licenses" / "kernel.txt").write_bytes(b"license")
    write_checksums(bundle)
    return bundle


def signing_key(directory: Path) -> tuple[Path, Path]:
    key = directory / "keys" / "release"
    key.parent.mkdir()
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", IDENTITY, "-f", str(key)], check=True
    )
    public = key.with_suffix(".pub").read_text(encoding="ascii").split()
    signers = directory / "keys" / "allowed_signers"
    signers.write_text(
        f'{IDENTITY} namespaces="{NAMESPACE}" {public[0]} {public[1]}\n', encoding="ascii"
    )
    return key, signers


def test_the_checksums_list_every_file_but_themselves_and_the_signature(tmp_path: Path) -> None:
    bundle = bundle_in(tmp_path)
    (bundle / SIGNATURE_FILE).write_bytes(b"signature")

    assert sorted(read_checksums(bundle)) == ["kernel.elf", "licenses/kernel.txt"]
    assert checksum_problems(bundle) == []


def test_changed_missing_and_added_files_are_reported(tmp_path: Path) -> None:
    bundle = bundle_in(tmp_path)
    (bundle / "kernel.elf").write_bytes(b"another kernel")
    (bundle / "licenses" / "kernel.txt").unlink()
    (bundle / "extra").write_bytes(b"extra")

    assert checksum_problems(bundle) == [
        "licenses/kernel.txt: listed but missing",
        "extra: present but not listed",
        "kernel.elf: the content does not match its checksum",
    ]


def test_a_checksum_entry_that_leaves_the_bundle_is_refused(tmp_path: Path) -> None:
    bundle = bundle_in(tmp_path)
    (bundle / CHECKSUMS_FILE).write_text(f"{'0' * 64}  ../outside\n", encoding="utf-8")

    with pytest.raises(CheckError, match="malformed"):
        read_checksums(bundle)


@needs_signer
def test_a_signed_bundle_verifies_only_intact_and_for_its_signer(tmp_path: Path) -> None:
    bundle = bundle_in(tmp_path)
    key, signers = signing_key(tmp_path)

    sign_bundle(bundle, key, tmp_path / "repository")
    verify_bundle(bundle, signers, IDENTITY)

    with pytest.raises(CheckError, match=r"could not verify the checksums: \S"):
        verify_bundle(bundle, signers, "someone@example.org")
    (bundle / "kernel.elf").write_bytes(b"another kernel")
    with pytest.raises(CheckError, match="does not match its checksum"):
        verify_bundle(bundle, signers, IDENTITY)


@needs_signer
def test_changed_checksums_do_not_verify_against_the_signature(tmp_path: Path) -> None:
    bundle = bundle_in(tmp_path)
    key, signers = signing_key(tmp_path)
    sign_bundle(bundle, key, tmp_path / "repository")
    (bundle / "kernel.elf").write_bytes(b"another kernel")
    write_checksums(bundle)

    with pytest.raises(CheckError, match=r"could not verify the checksums: \S"):
        verify_bundle(bundle, signers, IDENTITY)


@needs_signer
def test_a_key_kept_inside_the_repository_is_not_used(tmp_path: Path) -> None:
    bundle = bundle_in(tmp_path)
    key, _signers = signing_key(tmp_path)

    with pytest.raises(CheckError, match="inside the repository"):
        sign_bundle(bundle, key, tmp_path)

    assert not (bundle / SIGNATURE_FILE).exists()


def test_an_unsigned_bundle_does_not_verify(tmp_path: Path) -> None:
    bundle = bundle_in(tmp_path)

    with pytest.raises(CheckError, match="is not signed"):
        verify_bundle(bundle, tmp_path / "allowed_signers", IDENTITY)
