from dataclasses import dataclass
from pathlib import Path

from kernel_tool.build.native import BuildOutputs
from kernel_tool.fuzzing.ledger import family_evidence
from kernel_tool.fuzzing.model import Family
from kernel_tool.qualification.evidence import (
    BOOTS,
    MEASUREMENTS,
    REPRODUCTION,
    SOAK,
    VERIFICATION,
    artifact_identity,
    evidence_file,
    read_evidence,
)
from kernel_tool.release.advisories import load_review, review_problems
from kernel_tool.release.interfaces import check_interfaces
from kernel_tool.release.licenses import incompatibilities, license_inventory
from kernel_tool.toolchain.lock import ToolchainLock

REQUIRED_BOOTS = 1000
REQUIRED_SOAK_HOURS = 24.0
REQUIRED_FUZZING_HOURS = 24.0
SECONDS_PER_HOUR = 3600
LIFECYCLE_CHECKS = ("suite-processes",)
ISOLATION_CHECKS = (
    "suite-memory",
    "suite-capabilities",
    "suite-ipc",
    "suite-devices",
    "faults-device-reset",
)
DURABILITY_CHECKS = ("suite-storage", "faults-storage-crash", "volume-corpus")
NETWORK_CHECKS = ("suite-network", "suite-network-interop", "faults-network-faults")
UPDATE_CHECKS = ("suite-release-journey", "suite-system-journey")
PASSED = "passed"


@dataclass(frozen=True, slots=True)
class Gate:
    name: str
    met: bool
    detail: str


@dataclass(frozen=True, slots=True)
class Qualification:
    root: Path
    outputs: BuildOutputs
    fuzzing_directory: Path
    lock: ToolchainLock


def evaluate(qualification: Qualification) -> list[Gate]:
    identity = artifact_identity(qualification.outputs)
    verification = _current(qualification, VERIFICATION, identity)
    return [
        correctness_gate(verification),
        boot_gate(_current(qualification, BOOTS, identity)),
        checks_gate("lifecycle", verification, LIFECYCLE_CHECKS),
        stability_gate(_current(qualification, SOAK, identity)),
        fuzzing_gate(qualification),
        checks_gate("isolation", verification, ISOLATION_CHECKS),
        checks_gate("durability", verification, DURABILITY_CHECKS),
        checks_gate("network", verification, NETWORK_CHECKS),
        dependencies_gate(qualification),
        distribution_gate(_current(qualification, REPRODUCTION, identity), verification),
        interfaces_gate(qualification.root),
        budgets_gate(_current(qualification, MEASUREMENTS, identity)),
    ]


def correctness_gate(verification: dict[str, object] | str) -> Gate:
    name = "correctness"
    if isinstance(verification, str):
        return Gate(name, False, verification)
    if verification.get("whole_matrix") is not True:
        return Gate(name, False, "the last verification covered only part of the matrix")
    if verification.get("complete") is not True:
        return Gate(name, False, "some checks of the matrix could not run")
    if verification.get(PASSED) is not True:
        return Gate(name, False, "the verification matrix has failed checks")
    return Gate(name, True, f"{len(_checks(verification))} checks of the whole matrix passed")


def boot_gate(boots: dict[str, object] | str) -> Gate:
    name = "boot"
    if isinstance(boots, str):
        return Gate(name, False, boots)
    completed, failed = boots.get("completed"), boots.get("failed")
    if not isinstance(completed, int) or completed < REQUIRED_BOOTS:
        return Gate(name, False, f"{completed} boots recorded; {REQUIRED_BOOTS} are required")
    if failed or boots.get(PASSED) is not True:
        return Gate(name, False, f"boots failed: {failed}")
    return Gate(name, True, f"{completed} boots reached the shell and stopped in order")


def checks_gate(
    name: str, verification: dict[str, object] | str, required: tuple[str, ...]
) -> Gate:
    if isinstance(verification, str):
        return Gate(name, False, verification)
    statuses = {str(check.get("name")): check.get("status") for check in _checks(verification)}
    missing = [check for check in required if statuses.get(check) != PASSED]
    if missing:
        return Gate(name, False, f"checks without a passing result: {', '.join(missing)}")
    return Gate(name, True, f"passed: {', '.join(required)}")


def stability_gate(soak: dict[str, object] | str) -> Gate:
    name = "stability"
    if isinstance(soak, str):
        return Gate(name, False, soak)
    seconds = soak.get("seconds")
    hours = seconds / SECONDS_PER_HOUR if isinstance(seconds, int | float) else 0.0
    if soak.get(PASSED) is not True:
        return Gate(name, False, f"the soak failed: {soak.get('failures')}")
    if soak.get("network") is not True:
        return Gate(name, False, "the soak ran without the network")
    if hours < REQUIRED_SOAK_HOURS:
        return Gate(
            name,
            False,
            f"the soak ran {hours:.2f} hours in one boot; {REQUIRED_SOAK_HOURS:g} are required",
        )
    return Gate(name, True, f"{hours:.2f} hours in one boot without failure or growth")


def fuzzing_gate(qualification: Qualification) -> Gate:
    shortfalls = []
    accumulated = []
    for family in Family:
        evidence = family_evidence(qualification.fuzzing_directory, qualification.root, family)
        accumulated.append(f"{family.value}={evidence.hours:.2f}h")
        if evidence.open_findings:
            shortfalls.append(f"{family.value} has {evidence.open_findings} open findings")
        elif evidence.hours < REQUIRED_FUZZING_HOURS:
            shortfalls.append(
                f"{family.value} accumulated {evidence.hours:.2f} "
                f"of {REQUIRED_FUZZING_HOURS:g} hours"
            )
    if shortfalls:
        return Gate("fuzzing", False, "; ".join(shortfalls))
    return Gate("fuzzing", True, "no open finding; " + " ".join(accumulated))


def dependencies_gate(qualification: Qualification) -> Gate:
    problems = review_problems(qualification.lock, load_review(qualification.root))
    problems.extend(incompatibilities(license_inventory(qualification.root, qualification.lock)))
    if problems:
        return Gate("dependencies", False, "; ".join(problems))
    return Gate("dependencies", True, "every pinned component is reviewed and its license accepted")


def distribution_gate(
    reproduction: dict[str, object] | str, verification: dict[str, object] | str
) -> Gate:
    name = "distribution"
    if isinstance(reproduction, str):
        return Gate(name, False, reproduction)
    if reproduction.get(PASSED) is not True:
        return Gate(name, False, "clean builds do not reproduce the current images")
    journey = checks_gate(name, verification, UPDATE_CHECKS)
    if not journey.met:
        return journey
    return Gate(name, True, "clean builds reproduce the images; update and recovery passed")


def interfaces_gate(root: Path) -> Gate:
    problems = check_interfaces(root)
    if problems:
        return Gate("interfaces", False, "; ".join(problems))
    return Gate("interfaces", True, "the frozen interfaces match their recorded digests")


def budgets_gate(measurements: dict[str, object] | str) -> Gate:
    name = "budgets"
    if isinstance(measurements, str):
        return Gate(name, False, measurements)
    if measurements.get(PASSED) is not True:
        return Gate(name, False, "a measured budget is missed or unmeasured")
    return Gate(name, True, "every budget is met on the recorded machine")


def _current(
    qualification: Qualification, name: str, identity: dict[str, str]
) -> dict[str, object] | str:
    path = evidence_file(qualification.outputs, name)
    document = read_evidence(path)
    if document is None:
        return f"no evidence: {path.name} was never written for this build directory"
    if document.get("artifacts") != identity:
        return f"{path.name} was produced for other images; run it again for the current build"
    return document


def _checks(verification: dict[str, object]) -> list[dict[str, object]]:
    checks = verification.get("checks")
    if not isinstance(checks, list):
        return []
    return [check for check in checks if isinstance(check, dict)]
