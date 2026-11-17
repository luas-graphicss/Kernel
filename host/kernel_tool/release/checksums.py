from pathlib import Path, PurePosixPath

from kernel_tool.outcome import CheckError
from kernel_tool.toolchain.fetch import sha256_file

CHECKSUMS_FILE = "SHA256SUMS"
SIGNATURE_FILE = "SHA256SUMS.sig"
UNLISTED = (CHECKSUMS_FILE, SIGNATURE_FILE)
SEPARATOR = "  "
ENCODING = "utf-8"


def bundle_files(directory: Path) -> list[Path]:
    return sorted(
        file
        for file in directory.rglob("*")
        if file.is_file() and file.relative_to(directory).as_posix() not in UNLISTED
    )


def write_checksums(directory: Path) -> Path:
    lines = [
        f"{sha256_file(file)}{SEPARATOR}{file.relative_to(directory).as_posix()}\n"
        for file in bundle_files(directory)
    ]
    path = directory / CHECKSUMS_FILE
    path.write_text("".join(lines), encoding=ENCODING)
    return path


def read_checksums(directory: Path) -> dict[str, str]:
    path = directory / CHECKSUMS_FILE
    try:
        lines = path.read_text(encoding=ENCODING).splitlines()
    except OSError as error:
        raise CheckError(f"{path}: cannot read the checksums: {error}") from error
    listed = {}
    for number, line in enumerate(lines, start=1):
        digest, separator, name = line.partition(SEPARATOR)
        relative = PurePosixPath(name)
        if not separator or not name or relative.is_absolute() or ".." in relative.parts:
            raise CheckError(f"{path}:{number}: the entry is malformed")
        listed[name] = digest
    return listed


def checksum_problems(directory: Path) -> list[str]:
    listed = read_checksums(directory)
    present = {file.relative_to(directory).as_posix(): file for file in bundle_files(directory)}
    problems = [f"{name}: listed but missing" for name in sorted(set(listed) - set(present))]
    problems.extend(
        f"{name}: present but not listed" for name in sorted(set(present) - set(listed))
    )
    problems.extend(
        f"{name}: the content does not match its checksum"
        for name in sorted(set(listed) & set(present))
        if sha256_file(present[name]) != listed[name]
    )
    return problems


def require_intact(directory: Path) -> None:
    problems = checksum_problems(directory)
    if problems:
        raise CheckError(f"{directory} is not intact:\n" + "\n".join(problems))
