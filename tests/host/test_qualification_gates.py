from pathlib import Path

import pytest

from kernel_tool.build.native import BuildOutputs
from kernel_tool.commands.matrix import verification_matrix
from kernel_tool.fuzzing.ledger import record_runs
from kernel_tool.fuzzing.model import Family, TargetRun
from kernel_tool.fuzzing.registry import targets_of
from kernel_tool.qualification.evidence import (
    BOOTS,
    MEASUREMENTS,
    REPRODUCTION,
    SOAK,
    VERIFICATION,
    artifact_identity,
    evidence_file,
    write_evidence,
)
from kernel_tool.qualification.gates import (
    DURABILITY_CHECKS,
    ISOLATION_CHECKS,
    LIFECYCLE_CHECKS,
    NETWORK_CHECKS,
    REQUIRED_BOOTS,
    UPDATE_CHECKS,
    Gate,
    Qualification,
    boot_gate,
    checks_gate,
    correctness_gate,
    evaluate,
    stability_gate,
)
from kernel_tool.toolchain.lock import load_lock

REPOSITORY = Path(__file__).resolve().parents[2]
DAY_SECONDS = 24 * 3600


def outputs_in(directory: Path) -> BuildOutputs:
    outputs = BuildOutputs(
        directory=directory,
        kernel=directory / "kernel.elf",
        selftest_kernel=directory / "kernel-selftest.elf",
        init_program=directory / "user" / "init.elf",
        init_image=directory / "init.img",
        fault_image=directory / "fault.img",
        tests_program=directory / "user" / "tests.elf",
        tests_image=directory / "tests.img",
        boot_image=directory / "boot.img",
    )
    for artifact in (outputs.kernel, outputs.init_image, outputs.boot_image):
        artifact.write_bytes(artifact.name.encode("ascii"))
    return outputs


def qualification(tmp_path: Path) -> Qualification:
    lock = load_lock(REPOSITORY / "toolchain.lock.toml")
    return Qualification(REPOSITORY, outputs_in(tmp_path), tmp_path / "fuzz", lock)


def gates_by_name(subject: Qualification) -> dict[str, Gate]:
    return {gate.name: gate for gate in evaluate(subject)}


def whole_verification(artifacts: dict[str, str]) -> dict[str, object]:
    return {
        "artifacts": artifacts,
        "whole_matrix": True,
        "complete": True,
        "passed": True,
        "checks": [{"name": check.name, "status": "passed"} for check in verification_matrix()],
    }


def test_without_evidence_only_what_the_repository_proves_is_met(tmp_path: Path) -> None:
    gates = gates_by_name(qualification(tmp_path))

    assert {name for name, gate in gates.items() if gate.met} == {"dependencies", "interfaces"}
    assert "no evidence" in gates["correctness"].detail
    assert "0.00 of 24 hours" in gates["fuzzing"].detail


def test_evidence_of_other_images_is_not_accepted(tmp_path: Path) -> None:
    subject = qualification(tmp_path)
    stale = whole_verification({"kernel.elf": "0" * 64})
    write_evidence(evidence_file(subject.outputs, VERIFICATION), stale)

    gate = gates_by_name(subject)["correctness"]

    assert not gate.met
    assert "other images" in gate.detail


def test_every_gate_is_met_with_complete_evidence_of_the_current_images(tmp_path: Path) -> None:
    subject = qualification(tmp_path)
    identity = artifact_identity(subject.outputs)
    passed: dict[str, object] = {"artifacts": identity, "passed": True}
    boots = passed | {"completed": REQUIRED_BOOTS, "failed": []}
    soak = passed | {"seconds": DAY_SECONDS, "network": True, "failures": []}
    write_evidence(evidence_file(subject.outputs, VERIFICATION), whole_verification(identity))
    write_evidence(evidence_file(subject.outputs, BOOTS), boots)
    write_evidence(evidence_file(subject.outputs, SOAK), soak)
    write_evidence(evidence_file(subject.outputs, MEASUREMENTS), passed)
    write_evidence(evidence_file(subject.outputs, REPRODUCTION), passed)
    for family in Family:
        target = targets_of(family)[0]
        run = TargetRun(family, target.name, 1, DAY_SECONDS, 1, (), ())
        record_runs(subject.fuzzing_directory, REPOSITORY, [(target, run)])

    unmet = [gate for gate in evaluate(subject) if not gate.met]

    assert unmet == []


def test_a_partial_incomplete_or_failed_matrix_does_not_prove_correctness() -> None:
    whole = whole_verification({})

    assert correctness_gate(whole).met
    assert not correctness_gate(whole | {"whole_matrix": False}).met
    assert not correctness_gate(whole | {"complete": False}).met
    assert not correctness_gate(whole | {"passed": False}).met


def test_the_boot_gate_needs_a_thousand_boots_without_a_failure() -> None:
    assert boot_gate({"completed": REQUIRED_BOOTS, "failed": [], "passed": True}).met
    assert not boot_gate({"completed": REQUIRED_BOOTS - 1, "failed": [], "passed": False}).met
    assert not boot_gate({"completed": REQUIRED_BOOTS, "failed": [7], "passed": False}).met


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"seconds": DAY_SECONDS - 1}, "24.00 hours in one boot; 24 are required"),
        ({"network": False}, "without the network"),
        ({"passed": False, "failures": ["round 3"]}, "round 3"),
    ],
)
def test_a_short_partial_or_failed_soak_does_not_prove_stability(
    change: dict[str, object], reason: str
) -> None:
    soak: dict[str, object] = {"seconds": DAY_SECONDS, "network": True, "passed": True}

    gate = stability_gate(soak | change)

    assert stability_gate(soak).met
    assert not gate.met
    assert reason in gate.detail


def test_a_gate_names_the_checks_that_did_not_pass() -> None:
    verification: dict[str, object] = {
        "checks": [
            {"name": "suite-memory", "status": "passed"},
            {"name": "suite-ipc", "status": "incomplete"},
        ]
    }

    gate = checks_gate("isolation", verification, ("suite-memory", "suite-ipc", "suite-devices"))

    assert not gate.met
    assert gate.detail.endswith("suite-ipc, suite-devices")


def test_every_check_a_release_gate_relies_on_exists_in_the_matrix() -> None:
    names = {check.name for check in verification_matrix()}
    relied_on = (
        *LIFECYCLE_CHECKS,
        *ISOLATION_CHECKS,
        *DURABILITY_CHECKS,
        *NETWORK_CHECKS,
        *UPDATE_CHECKS,
    )

    assert set(relied_on) <= names
