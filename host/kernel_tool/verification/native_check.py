import logging
import shutil
import subprocess
from pathlib import Path

from kernel_tool.outcome import CheckError, InfrastructureError
from kernel_tool.workspace import Workspace

HOSTED_SOURCES = (
    "native/supervisor/devices/device_tree/boot_description.c",
    "native/supervisor/devices/device_tree/container.c",
    "native/supervisor/devices/device_tree/tokens.c",
    "native/supervisor/memory/layout.c",
    "native/supervisor/memory/range.c",
    "native/supervisor/processes/syscall.c",
    "native/supervisor/processes/user_image.c",
)
INCLUDE_DIRECTORIES = ("native/include", "tests/native/support")
TEST_DIRECTORY = Path("tests") / "native"
SANITIZER_FLAGS = (
    "-fsanitize=address,undefined",
    "-fno-sanitize-recover=all",
    "-fno-omit-frame-pointer",
)
COMPILE_FLAGS = (
    "-std=c17",
    "-O1",
    "-g",
    "-Wall",
    "-Wextra",
    "-Wpedantic",
    "-Wconversion",
    "-Wshadow",
    "-Werror",
)
PROBE_SOURCE = "int main(void) { return 0; }\n"
COMPILE_TIMEOUT_SECONDS = 120
TEST_TIMEOUT_SECONDS = 300

logger = logging.getLogger(__name__)


def run_hosted_tests(workspace: Workspace) -> list[str]:
    compiler = shutil.which("cc")
    if compiler is None:
        raise InfrastructureError("required host tool 'cc' is not installed")

    output_dir = workspace.build_dir / "native-check"
    output_dir.mkdir(parents=True, exist_ok=True)
    _require_sanitizers(compiler, output_dir)

    tests = sorted((workspace.root / TEST_DIRECTORY).glob("*_test.c"))
    if not tests:
        raise CheckError(f"no hosted native tests found in {TEST_DIRECTORY}")
    support = sorted((workspace.root / TEST_DIRECTORY / "support").glob("*.c"))
    sources = [workspace.root / source for source in HOSTED_SOURCES]

    suites = []
    for test in tests:
        binary = output_dir / test.stem
        _compile(compiler, workspace.root, [*sources, *support, test], binary)
        _run(binary)
        suites.append(test.stem)
    return suites


def _require_sanitizers(compiler: str, output_dir: Path) -> None:
    probe = output_dir / "sanitizer_probe.c"
    probe.write_text(PROBE_SOURCE, encoding="ascii")
    completed = subprocess.run(
        [compiler, *SANITIZER_FLAGS, str(probe), "-o", str(output_dir / "sanitizer_probe")],
        capture_output=True,
        text=True,
        timeout=COMPILE_TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode != 0:
        raise InfrastructureError(
            "the host compiler cannot link AddressSanitizer and UndefinedBehaviorSanitizer:\n"
            f"{completed.stderr.strip()}"
        )


def _compile(compiler: str, root: Path, sources: list[Path], binary: Path) -> None:
    includes = [f"-I{root / directory}" for directory in INCLUDE_DIRECTORIES]
    command = [
        compiler,
        *COMPILE_FLAGS,
        *SANITIZER_FLAGS,
        *includes,
        *(str(source) for source in sources),
        "-o",
        str(binary),
    ]
    completed = subprocess.run(
        command, capture_output=True, text=True, timeout=COMPILE_TIMEOUT_SECONDS, check=False
    )
    if completed.returncode != 0:
        raise CheckError(f"{binary.name} does not compile:\n{completed.stderr.strip()}")


def _run(binary: Path) -> None:
    try:
        completed = subprocess.run(
            [str(binary)], capture_output=True, text=True, timeout=TEST_TIMEOUT_SECONDS, check=False
        )
    except subprocess.TimeoutExpired as expired:
        raise CheckError(f"{binary.name} exceeded {TEST_TIMEOUT_SECONDS} seconds") from expired
    if completed.returncode != 0:
        raise CheckError(
            f"{binary.name} failed with status {completed.returncode}:\n"
            f"{completed.stdout}{completed.stderr}".rstrip()
        )
    logger.info("%s", completed.stdout.strip())
