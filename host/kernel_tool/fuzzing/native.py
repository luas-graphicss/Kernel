import os
import re
import select
import shutil
import struct
import subprocess
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

from kernel_tool.fuzzing.model import Execution, Failure, FailureKind, InvariantError, NativeTarget
from kernel_tool.outcome import CheckError, InfrastructureError
from kernel_tool.verification.native_check import (
    COMPILE_FLAGS,
    COMPILE_TIMEOUT_SECONDS,
    HOSTED_SOURCES,
    INCLUDE_DIRECTORIES,
    SANITIZER_FLAGS,
    require_sanitizers,
)
from kernel_tool.workspace import Workspace

HARNESS_DIRECTORY = Path("tests") / "fuzz" / "native"
SUPPORT_DIRECTORY = Path("tests") / "native" / "support"
BUILD_DIRECTORY = Path("fuzz") / "native"
HARNESS_BINARY = "harness"
COVERAGE_FLAG = "-fsanitize-coverage=trace-pc"
FIXED_ADDRESS_FLAG = "-fno-pie"
FIXED_ADDRESS_LINK_FLAG = "-no-pie"
SANITIZER_ENVIRONMENT = {
    "ASAN_OPTIONS": "detect_leaks=0:abort_on_error=0",
    "UBSAN_OPTIONS": "print_stacktrace=1",
}
DEVICE_TREE_ENTRY = 0
USER_IMAGE_ENTRY = 1
IPC_MESSAGE_ENTRY = 2
SPAWN_REQUEST_ENTRY = 3
REQUEST = struct.Struct("<I")
RESPONSE = struct.Struct("<qH")
SLOT_BYTES = 4
MAX_DISTINCT_RESULTS = 256
READ_BYTES = 65536
SANITIZER_ERROR = re.compile(r"ERROR: (\w+Sanitizer: [\w-]+)")
FAULTING_FUNCTION = re.compile(r"#0 0x[0-9a-f]+ in (\w+)")
UNDEFINED_BEHAVIOR = re.compile(r"([\w.-]+):\d+:\d+: runtime error: ([^:\n]+)")
INVARIANT = re.compile(r"^invariant violated: (.+)$", re.MULTILINE)
TIME_LIMIT_SIGNATURE = "the input exceeded the time limit"


class HarnessStoppedError(Exception):
    def __init__(self, timed_out: bool) -> None:
        super().__init__("the harness stopped answering")
        self.timed_out = timed_out


def build_harness(workspace: Workspace) -> Path:
    compiler = shutil.which("cc")
    if compiler is None:
        raise InfrastructureError("required host tool 'cc' is not installed")
    directory = workspace.build_dir / BUILD_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    require_sanitizers(compiler, directory)

    root = workspace.root
    includes = [f"-I{root / path}" for path in (*INCLUDE_DIRECTORIES, HARNESS_DIRECTORY)]
    flags = [compiler, *COMPILE_FLAGS, *SANITIZER_FLAGS, FIXED_ADDRESS_FLAG, *includes]
    watched = [root / source for source in HOSTED_SOURCES]
    unwatched = [
        *sorted((root / SUPPORT_DIRECTORY).glob("*.c")),
        *sorted((root / HARNESS_DIRECTORY).glob("*.c")),
    ]
    objects = [_compile([*flags, COVERAGE_FLAG], root, source, directory) for source in watched]
    objects.extend(_compile(flags, root, source, directory) for source in unwatched)
    binary = directory / HARNESS_BINARY
    link = [compiler, *SANITIZER_FLAGS, FIXED_ADDRESS_LINK_FLAG, *map(str, objects)]
    _run_compiler([*link, "-o", str(binary)], HARNESS_BINARY)
    return binary


def _compile(flags: list[str], root: Path, source: Path, directory: Path) -> Path:
    name = "-".join(source.relative_to(root).with_suffix(".o").parts)
    compiled = directory / name
    _run_compiler([*flags, "-c", str(source), "-o", str(compiled)], name)
    return compiled


def _run_compiler(command: list[str], product: str) -> None:
    completed = subprocess.run(
        command, capture_output=True, text=True, timeout=COMPILE_TIMEOUT_SECONDS, check=False
    )
    if completed.returncode != 0:
        raise CheckError(f"{product} of the fuzzing harness does not build:\n{completed.stderr}")


class NativeExecutor:
    def __init__(
        self,
        binary: Path,
        target: NativeTarget,
        time_limit_seconds: float,
        messages: IO[bytes],
    ) -> None:
        self._command = [str(binary), str(target.entry)]
        self._target = target
        self._time_limit_seconds = time_limit_seconds
        self._seen: set[int] = set()
        self._results: set[int] = set()
        self._messages = messages
        self._process = self._start()

    def stop(self) -> None:
        self._process.kill()
        self._process.wait()

    def execute(self, data: bytes) -> Execution:
        try:
            result, slots = self._exchange(data)
        except HarnessStoppedError as stopped:
            failure = self._failure(stopped.timed_out)
            self._process = self._start()
            return Execution(failure, False)
        reached_code = not self._seen.issuperset(slots)
        self._seen.update(slots)
        answered_differently = self._is_new_result(result)
        return Execution(self._judgement(data, result), reached_code or answered_differently)

    def _is_new_result(self, result: int) -> bool:
        if result in self._results or len(self._results) >= MAX_DISTINCT_RESULTS:
            return False
        self._results.add(result)
        return True

    def _start(self) -> subprocess.Popen[bytes]:
        try:
            return subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._messages,
                env=os.environ | SANITIZER_ENVIRONMENT,
                bufsize=0,
            )
        except OSError as error:
            raise InfrastructureError(f"cannot start the fuzzing harness: {error}") from error

    def _exchange(self, data: bytes) -> tuple[int, tuple[int, ...]]:
        deadline = time.monotonic() + self._time_limit_seconds
        self._send(REQUEST.pack(len(data)) + data)
        result, count = RESPONSE.unpack(self._receive(RESPONSE.size, deadline))
        slots = self._receive(count * SLOT_BYTES, deadline)
        return result, struct.unpack(f"<{count}I", slots)

    def _send(self, request: bytes) -> None:
        pipe = self._process.stdin
        if pipe is None:
            raise HarnessStoppedError(timed_out=False)
        sent = 0
        try:
            while sent < len(request):
                sent += os.write(pipe.fileno(), request[sent:])
        except OSError as error:
            raise HarnessStoppedError(timed_out=False) from error

    def _receive(self, count: int, deadline: float) -> bytes:
        pipe = self._process.stdout
        if pipe is None:
            raise HarnessStoppedError(timed_out=False)
        received = bytearray()
        while len(received) < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([pipe], [], [], remaining)[0]:
                raise HarnessStoppedError(timed_out=True)
            chunk = os.read(pipe.fileno(), min(count - len(received), READ_BYTES))
            if not chunk:
                raise HarnessStoppedError(timed_out=False)
            received.extend(chunk)
        return bytes(received)

    def _failure(self, timed_out: bool) -> Failure:
        self._process.kill()
        status = self._process.wait()
        self._messages.seek(0)
        detail = self._messages.read().decode("utf-8", errors="replace")
        self._messages.seek(0)
        self._messages.truncate()
        if timed_out:
            limit = f"no result within {self._time_limit_seconds:g} seconds"
            return Failure(FailureKind.HANG, TIME_LIMIT_SIGNATURE, limit)
        violated = INVARIANT.search(detail)
        if violated is not None:
            return Failure(FailureKind.VIOLATION, violated.group(1), detail)
        return Failure(FailureKind.CRASH, _crash_signature(detail, status), detail)

    def _judgement(self, data: bytes, result: int) -> Failure | None:
        if self._target.judge is None:
            return None
        try:
            self._target.judge(data, result)
        except InvariantError as violation:
            return Failure(FailureKind.VIOLATION, str(violation), str(violation))
        return None


@contextmanager
def native_executor(
    binary: Path, target: NativeTarget, time_limit_seconds: float
) -> Iterator[NativeExecutor]:
    with tempfile.TemporaryFile() as messages:
        executor = NativeExecutor(binary, target, time_limit_seconds, messages)
        try:
            yield executor
        finally:
            executor.stop()


def _crash_signature(detail: str, status: int) -> str:
    function = FAULTING_FUNCTION.search(detail)
    where = f" in {function.group(1)}" if function is not None else ""
    sanitizer = SANITIZER_ERROR.search(detail)
    if sanitizer is not None:
        return sanitizer.group(1) + where
    undefined = UNDEFINED_BEHAVIOR.search(detail)
    if undefined is not None:
        return f"undefined behavior in {undefined.group(1)}: {undefined.group(2)}"
    return f"the harness ended with status {status}"
