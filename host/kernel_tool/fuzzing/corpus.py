from collections.abc import Iterable
from pathlib import Path

from kernel_tool.fuzzing.model import Target
from kernel_tool.outcome import CheckError

CORPUS_DIRECTORY = Path("tests") / "fuzz" / "corpus"
REGRESSION_DIRECTORY = Path("tests") / "fuzz" / "regressions"
ENTRY_SUFFIX = ".hex"
ENCODING = "ascii"


def entries_file(directory: Path, target: Target) -> Path:
    return directory / target.family.value / f"{target.name}{ENTRY_SUFFIX}"


def read_entries(path: Path) -> tuple[bytes, ...]:
    if not path.is_file():
        return ()
    entries = []
    for number, line in enumerate(path.read_text(encoding=ENCODING).splitlines(), start=1):
        try:
            entries.append(bytes.fromhex(line))
        except ValueError as error:
            raise CheckError(f"{path}:{number}: the entry is not hexadecimal") from error
    return tuple(entries)


def write_entries(path: Path, entries: Iterable[bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [entry.hex() + "\n" for entry in sorted(set(entries))]
    path.write_text("".join(lines), encoding=ENCODING)
