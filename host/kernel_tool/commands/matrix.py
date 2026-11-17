import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

from kernel_tool.commands import artifacts, build, fault_test, fuzz, storage, test
from kernel_tool.commands.options import Command
from kernel_tool.fuzzing.model import Family
from kernel_tool.outcome import CheckError, InfrastructureError
from kernel_tool.qualification.checks import Area, Check
from kernel_tool.release.interfaces import check_interfaces
from kernel_tool.scenarios.fault_suites import FAULT_SUITES
from kernel_tool.scenarios.network_suites import FAULTS
from kernel_tool.workspace import Workspace

STORAGE_CORPUS = Path("tests") / "faults" / "storage"
SUITE_AREAS = {
    "bootstrap": Area.RUNTIME,
    "network": Area.INTEROPERABILITY,
    "network-interop": Area.INTEROPERABILITY,
    "storage": Area.RECOVERY,
    "system-journey": Area.RECOVERY,
    "release-journey": Area.RECOVERY,
}
FAULT_SUITE_AREAS = {FAULTS: Area.INTEROPERABILITY}


def host_program(name: str, module: str, *arguments: str) -> Check:
    def run(workspace: Workspace, _profile: str) -> None:
        if importlib.util.find_spec(module) is None:
            raise InfrastructureError(f"the host tool {module} is not installed")
        completed = subprocess.run(
            [sys.executable, "-m", module, *arguments],
            cwd=workspace.root,
            stdin=subprocess.DEVNULL,
            stdout=sys.stderr,
            check=False,
        )
        if completed.returncode != 0:
            raise CheckError(f"{module} exited with status {completed.returncode}")

    return Check(name, Area.HOST, run)


def tool_command(name: str, area: Area, handler: Command, **options: object) -> Check:
    def run(workspace: Workspace, profile: str) -> None:
        handler(workspace, argparse.Namespace(profile=profile, **options))

    return Check(name, area, run)


def frozen_interfaces() -> Check:
    def run(workspace: Workspace, _profile: str) -> None:
        problems = check_interfaces(workspace.root)
        if problems:
            raise CheckError("\n".join(problems))

    return Check("frozen-interfaces", Area.HOST, run)


def fuzzing_corpus() -> Check:
    def run(workspace: Workspace, _profile: str) -> None:
        failures = fuzz.replay_families(workspace, tuple(Family))
        if failures:
            raise CheckError("known fuzzing inputs fail:\n" + "\n".join(failures))

    return Check("fuzzing-corpus", Area.NATIVE, run)


def volume_corpus() -> Check:
    def run(workspace: Workspace, _profile: str) -> None:
        storage.verify_corpus(workspace.root / STORAGE_CORPUS)

    return Check("volume-corpus", Area.RECOVERY, run)


def suite_checks() -> tuple[Check, ...]:
    return tuple(
        tool_command(
            f"suite-{suite}",
            SUITE_AREAS.get(suite, Area.EMULATION),
            test.run_suite,
            suite=suite,
            scenario=None,
        )
        for suite in sorted(test.SUITES)
    )


def fault_checks() -> tuple[Check, ...]:
    return tuple(
        tool_command(
            f"faults-{suite}",
            FAULT_SUITE_AREAS.get(suite, Area.RECOVERY),
            fault_test.run_fault_suite,
            suite=suite,
            sequences=fault_test.DEFAULT_SEQUENCES,
            seed=fault_test.DEFAULT_SEED,
        )
        for suite in sorted(FAULT_SUITES)
    )


def verification_matrix() -> tuple[Check, ...]:
    return (
        host_program("format", "ruff", "format", "--check", "."),
        host_program("lint", "ruff", "check", "."),
        host_program("types", "mypy", "--strict", "host", "src"),
        host_program("host-tests", "pytest", "tests/host", "tests/conformance"),
        frozen_interfaces(),
        tool_command(
            "native-check", Area.NATIVE, build.run_native_check, sanitizers=False, analyzer=False
        ),
        fuzzing_corpus(),
        tool_command("build", Area.NATIVE, build.run_build),
        tool_command("artifacts", Area.NATIVE, artifacts.run_verify, reproduce=False),
        *suite_checks(),
        *fault_checks(),
        volume_corpus(),
    )
