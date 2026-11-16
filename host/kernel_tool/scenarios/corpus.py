import os
import subprocess
import sys
from pathlib import Path

from kernel_tool.outcome import CheckError, InfrastructureError

CORPUS_MODULE = "corpus"
CORPUS_PATHS = (Path("src"), Path("tests") / "conformance")
REFERENCE_TIMEOUT_SECONDS = 300


def reference_corpus(root: Path) -> tuple[str, ...]:
    environment = {
        "PYTHONPATH": os.pathsep.join(str(root / path) for path in CORPUS_PATHS),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    try:
        completed = subprocess.run(
            [sys.executable, "-m", CORPUS_MODULE],
            cwd=root,
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=REFERENCE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise InfrastructureError(f"cannot run the reference corpus on CPython: {error}") from error
    if completed.returncode != 0:
        raise CheckError(f"the reference corpus failed on CPython:\n{completed.stderr.strip()}")
    return tuple(completed.stdout.splitlines())
