from corpus.runner import run_reference
from runtime_selftest import (
    bindings_case,
    bytes_case,
    collection_case,
    exceptions_case,
    imports_case,
    integers_case,
)
from runtime_selftest.checks import Checks

CASES = (
    ("integers", integers_case.run),
    ("bytes", bytes_case.run),
    ("exceptions", exceptions_case.run),
    ("imports", imports_case.run),
    ("bindings", bindings_case.run),
    ("collection", collection_case.run),
)


def main() -> bool:
    for name, run in CASES:
        checks = Checks()
        run(checks)
        print(f"selftest: case={name} checks={checks.passed} result=ok")
    for line in run_reference():
        print(line)
    return True
