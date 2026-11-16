import re
from pathlib import Path

import pytest

from kernel_tool.commands.test import SUITES
from kernel_tool.network.malformed import specimens
from kernel_tool.network.orders import Call, Darken, Inject
from kernel_tool.network.plan import CLEAN, stream_crc32, stream_sha256
from kernel_tool.scenarios.evaluation import check_transcript
from kernel_tool.scenarios.fault_suites import FAULT_SUITES
from kernel_tool.scenarios.model import Deadline, Devices, Scenario
from kernel_tool.scenarios.network_suites import (
    BLACKOUT_MILLISECONDS,
    CASES_INBOUND,
    CASES_UPLOAD,
    DATAGRAM_BYTES,
    DATAGRAM_ROUNDS,
    FAULT_CASES,
    FAULTS,
    FAULTS_SCENARIO,
    FLOOD_INBOUND,
    FLOOD_PORT,
    FLOOD_REQUESTS,
    INTEROP,
    INTEROP_CASES,
    INTEROP_CLEAN,
    INTEROP_DOWNLOAD,
    INTEROP_IMPAIRED,
    INTEROP_INBOUND,
    INTEROP_RELAY,
    INTEROP_SLOW,
    INTEROP_UPLOAD,
    INTRUDER,
    LISTEN_PORT,
    MALFORMED_FRAMES,
    NETWORK,
    NETWORK_CASES,
    NETWORK_FAULT_SUITES,
    NETWORK_SCENARIO,
    NETWORK_SUITES,
)
from kernel_tool.verification.transcript import read_transcript

REPOSITORY = Path(__file__).resolve().parents[2]
GUEST_SUITE = REPOSITORY / "tests" / "guest" / "programs" / "suites" / "network"
CLEAN_EXIT = (
    "policy: reaped=init reason=exit value=0 live=0 memory-in-use=0",
    "policy: resources=released",
    "kernel: status=ok",
)
SCENARIOS = (NETWORK_SCENARIO, INTEROP_IMPAIRED, INTEROP_CLEAN, FAULTS_SCENARIO)


def guest_constant(module: str, name: str) -> int:
    source = (GUEST_SUITE / f"{module}.py").read_text(encoding="utf-8")
    match = re.search(rf"^{name} = (\d+)$", source, re.MULTILINE)
    assert match is not None, f"{module}.py declares no {name}"
    return int(match.group(1))


def admitted(program: str) -> str:
    return f"policy: admitted=init program={program} handle=16777216 priority=1"


def case(suite: str, name: str) -> str:
    return f"test: suite={suite} case={name} checks=5 result=ok"


def interop_transcript(retransmitted: int) -> str:
    cases = [case(INTEROP, name) for name in INTEROP_CASES]
    lines = (
        "boot: hart=0",
        admitted("suites.network.interop"),
        f"network: transfer=upload bytes=131072 sha256={stream_sha256(17, 131072)}",
        cases[0],
        f"network: transfer=download bytes=131072 crc32={stream_crc32(23, 131072)}",
        cases[1],
        f"network: transfer=relay bytes=65536 sha256={stream_sha256(29, 65536)}",
        cases[2],
        "network: listening port=8080",
        "network: transfer=inbound bytes=65536",
        cases[3],
        "network: transfer=datagrams delivered=4 bytes=3072",
        cases[4],
        f"network: transfer=slow-reader bytes=32768 sha256={stream_sha256(31, 32768)}",
        cases[5],
        f"network: recovery retransmitted={retransmitted} out-of-order=3",
        cases[6],
        *CLEAN_EXIT,
    )
    return "\n".join(lines) + "\n"


def failures(scenario: Scenario, serial_output: str) -> list[str]:
    return check_transcript(scenario, read_transcript(serial_output))


def test_the_network_suites_are_registered_under_the_commands_that_run_them() -> None:
    assert set(NETWORK_SUITES) == {"network", "network-interop"}
    assert set(NETWORK_FAULT_SUITES) == {"network-faults"}
    assert SUITES[NETWORK] is NETWORK_SUITES[NETWORK]
    assert SUITES[INTEROP] == (INTEROP_IMPAIRED, INTEROP_CLEAN)
    assert FAULT_SUITES[FAULTS] == (FAULTS_SCENARIO,)
    assert len({scenario.name for scenario in SCENARIOS}) == len(SCENARIOS)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
def test_every_network_scenario_boots_the_tests_image_with_entropy_and_a_peer(
    scenario: Scenario,
) -> None:
    assert scenario.devices == Devices(entropy=True)
    assert scenario.network is not None
    assert scenario.deadline is Deadline.SESSION
    assert scenario.steps
    for pattern in (*scenario.expected_lines, *(step.awaited for step in scenario.steps)):
        re.compile(pattern)
    for step in scenario.steps:
        assert step.awaited in scenario.expected_lines
        assert step.orders


def test_the_host_expects_the_cases_the_guest_programs_declare() -> None:
    declared = {
        "main": NETWORK_CASES,
        "interop": INTEROP_CASES,
        "faults": FAULT_CASES,
    }
    for module, cases in declared.items():
        source = (GUEST_SUITE / f"{module}.py").read_text(encoding="utf-8")
        assert tuple(re.findall(r'^    \("([a-z-]+)", ', source, re.MULTILINE)) == cases


def test_the_host_knows_the_transfers_the_guest_programs_make() -> None:
    assert (CASES_UPLOAD.seed, CASES_UPLOAD.length) == (
        guest_constant("stream_case", "UPLOAD_SEED"),
        guest_constant("stream_case", "UPLOAD_BYTES"),
    )
    for transfer, name in (
        (INTEROP_UPLOAD, "UPLOAD"),
        (INTEROP_DOWNLOAD, "DOWNLOAD"),
        (INTEROP_RELAY, "RELAY"),
        (INTEROP_SLOW, "SLOW"),
    ):
        assert transfer.seed == guest_constant("interop", f"{name}_SEED")
        assert transfer.length == guest_constant("interop", f"{name}_BYTES")
    assert guest_constant("interop", "DATAGRAM_BLOCKS") * 256 == DATAGRAM_BYTES
    assert guest_constant("interop", "DATAGRAM_ROUNDS") == DATAGRAM_ROUNDS
    assert guest_constant("peer", "LISTEN_PORT") == LISTEN_PORT
    assert guest_constant("faults", "FLOOD_PORT") == FLOOD_PORT
    assert guest_constant("faults", "FLOOD_BACKLOG") < FLOOD_REQUESTS


def test_the_listening_guest_is_called_with_the_bytes_it_must_echo() -> None:
    (step,) = NETWORK_SCENARIO.steps

    assert step.awaited == r"^network: listening port=8080$"
    assert step.orders == (Call(LISTEN_PORT, CASES_INBOUND.seed, CASES_INBOUND.length),)
    assert INTEROP_IMPAIRED.steps == INTEROP_CLEAN.steps
    assert INTEROP_IMPAIRED.steps[0].orders == (
        Call(LISTEN_PORT, INTEROP_INBOUND.seed, INTEROP_INBOUND.length),
    )


def test_interoperability_runs_on_an_impaired_link_and_on_a_clean_one() -> None:
    assert INTEROP_IMPAIRED.network is not None
    assert INTEROP_CLEAN.network is not None
    impaired = INTEROP_IMPAIRED.network.plan
    clean = INTEROP_CLEAN.network.plan

    assert impaired.uplink.loss > 0 and impaired.downlink.loss > 0
    assert impaired.uplink.duplicate > 0 and impaired.uplink.reorder > 0
    assert clean.uplink == CLEAN and clean.downlink == CLEAN
    assert INTEROP_IMPAIRED.network.reported == INTEROP_CLEAN.network.reported
    assert len(INTEROP_IMPAIRED.network.reported) == 4


def test_a_transcript_with_the_expected_digests_passes_interoperability() -> None:
    assert failures(INTEROP_IMPAIRED, interop_transcript(12)) == []
    assert failures(INTEROP_CLEAN, interop_transcript(0)) == []


def test_an_impaired_run_without_retransmissions_proves_nothing() -> None:
    assert len(failures(INTEROP_IMPAIRED, interop_transcript(0))) > 0


def test_a_transfer_that_arrived_altered_fails_interoperability() -> None:
    altered = interop_transcript(12).replace(stream_sha256(29, 65536), "0" * 64)

    assert any("transfer=relay" in failure for failure in failures(INTEROP_CLEAN, altered))


def test_every_malformed_specimen_is_injected_when_the_guest_is_ready() -> None:
    malformed, flood, over, blackout = FAULTS_SCENARIO.steps
    expected = tuple(frame for specimen in specimens(INTRUDER) for frame in specimen.frames)

    assert expected == MALFORMED_FRAMES
    assert malformed.orders == (Inject(expected),)
    (requests,) = flood.orders
    assert isinstance(requests, Inject)
    assert len(requests.frames) == FLOOD_REQUESTS
    assert over.orders == (Call(FLOOD_PORT, FLOOD_INBOUND.seed, FLOOD_INBOUND.length),)
    assert blackout.orders == (Darken(BLACKOUT_MILLISECONDS),)


def test_the_fault_scenario_accounts_for_every_injected_frame() -> None:
    assert FAULTS_SCENARIO.network is not None
    reported = {
        expected.event: dict(expected.fields) for expected in FAULTS_SCENARIO.network.reported
    }

    assert reported["stopped"] == {"injected": len(MALFORMED_FRAMES) + FLOOD_REQUESTS}
    assert reported["call"]["matches"] is True
    assert reported["call"]["port"] == FLOOD_PORT
