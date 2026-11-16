import re
from pathlib import Path

HEADERS = Path(__file__).resolve().parents[2] / "native" / "include" / "kernel" / "abi"
DEFINITION = re.compile(r"^#define (\w+) (0[xX][0-9a-fA-F]+|\d+)(?:ull|ul|u)?$")


def definitions(header: str) -> dict[str, int]:
    found = {}
    for line in (HEADERS / header).read_text(encoding="utf-8").splitlines():
        match = DEFINITION.match(line)
        if match:
            found[match.group(1)] = int(match.group(2), 0)
    return found
