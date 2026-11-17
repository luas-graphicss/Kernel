import shutil
import subprocess
from pathlib import Path

from kernel_tool.outcome import CheckError, InfrastructureError
from kernel_tool.release.checksums import CHECKSUMS_FILE, SIGNATURE_FILE, require_intact

SIGNER = "ssh-keygen"
NAMESPACE = "kernel-release"
SIGNING_TIMEOUT_SECONDS = 120


def sign_bundle(bundle: Path, key: Path, repository: Path) -> Path:
    key = key.resolve()
    if not key.is_file():
        raise CheckError(f"the signing key {key} does not exist")
    if key.is_relative_to(repository.resolve()):
        raise CheckError("the signing key is inside the repository; keep release keys outside it")
    require_intact(bundle)
    signature = bundle / SIGNATURE_FILE
    signature.unlink(missing_ok=True)
    _run(
        [_signer(), "-Y", "sign", "-f", str(key), "-n", NAMESPACE, str(bundle / CHECKSUMS_FILE)],
        None,
        "sign",
    )
    if not signature.is_file():
        raise CheckError(f"{SIGNER} wrote no signature to {signature}")
    return signature


def verify_bundle(bundle: Path, allowed_signers: Path, identity: str) -> None:
    signature = bundle / SIGNATURE_FILE
    if not signature.is_file():
        raise CheckError(f"{bundle} is not signed: {SIGNATURE_FILE} is missing")
    if not allowed_signers.is_file():
        raise CheckError(f"the allowed signers file {allowed_signers} does not exist")
    command = [
        _signer(),
        "-Y",
        "verify",
        "-f",
        str(allowed_signers),
        "-I",
        identity,
        "-n",
        NAMESPACE,
        "-s",
        str(signature),
    ]
    _run(command, (bundle / CHECKSUMS_FILE).read_bytes(), "verify")
    require_intact(bundle)


def _signer() -> str:
    signer = shutil.which(SIGNER)
    if signer is None:
        raise InfrastructureError(f"required host tool {SIGNER!r} is not installed")
    return signer


def _run(command: list[str], signed: bytes | None, action: str) -> None:
    try:
        completed = subprocess.run(
            command,
            input=signed,
            stdin=subprocess.DEVNULL if signed is None else None,
            capture_output=True,
            timeout=SIGNING_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise InfrastructureError(f"cannot run {SIGNER}: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise CheckError(f"{SIGNER} could not {action} the checksums: {detail}")
