from dataclasses import dataclass, replace

from kernel_tool.network import crafting
from kernel_tool.network.malformed import Stations, connection_requests, specimens
from kernel_tool.network.orders import Call, Darken, Inject
from kernel_tool.network.plan import (
    GUEST_ADDRESS,
    GUEST_HARDWARE,
    INTRUDER_ADDRESS,
    INTRUDER_HARDWARE,
    LinkPolicy,
    NetworkPlan,
    stream_crc32,
    stream_sha256,
)
from kernel_tool.scenarios.guest_program import case_lines, tests_image_scenario
from kernel_tool.scenarios.model import Deadline, Devices, Network, Reported, Scenario, Step

NETWORK = "network"
INTEROP = "network-interop"
FAULTS = "network-faults"
NETWORK_DEVICES = Devices(entropy=True)
LISTEN_PORT = 8080
FLOOD_PORT = 8082
FLOOD_REQUESTS = 32
BLACKOUT_MILLISECONDS = 1500
DATAGRAM_BYTES = 3072
DATAGRAM_ROUNDS = 4
IMPAIRED_SEED = 7
NETWORK_CASES = (
    "interface-and-echo",
    "datagrams",
    "streams",
    "listening",
    "deadlines-cancellation-and-backpressure",
    "socket-quota",
    "access-rights",
)
INTEROP_CASES = (
    "upload-verified-by-the-peer",
    "download-verified-by-checksum",
    "relay-through-the-guest",
    "inbound-connection",
    "fragmented-datagrams",
    "slow-reader",
    "buffers-returned",
)
FAULT_CASES = (
    "malformed-traffic",
    "connection-flood",
    "link-blackout",
    "device-reset",
    "service-restart-with-a-waiting-client",
)


@dataclass(frozen=True, slots=True)
class Transfer:
    seed: int
    length: int

    @property
    def sha256(self) -> str:
        return stream_sha256(self.seed, self.length)

    @property
    def crc32(self) -> str:
        return stream_crc32(self.seed, self.length)


CASES_UPLOAD = Transfer(3, 20480)
CASES_INBOUND = Transfer(5, 16384)
INTEROP_UPLOAD = Transfer(17, 131072)
INTEROP_DOWNLOAD = Transfer(23, 131072)
INTEROP_RELAY = Transfer(29, 65536)
INTEROP_SLOW = Transfer(31, 32768)
INTEROP_INBOUND = Transfer(37, 65536)
FLOOD_INBOUND = Transfer(41, 8192)
IMPAIRED = LinkPolicy(loss=0.03, duplicate=0.02, reorder=0.1, reorder_milliseconds=20)
INTRUDER = Stations(
    guest_hardware=crafting.hardware(GUEST_HARDWARE),
    guest=crafting.address(GUEST_ADDRESS),
    sender_hardware=crafting.hardware(INTRUDER_HARDWARE),
    sender=crafting.address(INTRUDER_ADDRESS),
)
MALFORMED_FRAMES = tuple(frame for specimen in specimens(INTRUDER) for frame in specimen.frames)
MALFORMED_READY = r"^network: fault=malformed-traffic state=ready$"
FLOOD_READY = rf"^network: fault=connection-flood state=ready port={FLOOD_PORT}$"
FLOOD_OVER = rf"^network: fault=connection-flood state=over port={FLOOD_PORT}$"
BLACKOUT_READY = r"^network: fault=link-blackout state=ready$"


def listening(port: int) -> str:
    return rf"^network: listening port={port}$"


def digest_line(name: str, transfer: Transfer) -> str:
    return rf"^network: transfer={name} bytes={transfer.length} sha256={transfer.sha256}$"


def inbound_line(transfer: Transfer) -> str:
    return rf"^network: transfer=inbound bytes={transfer.length}$"


def call(port: int, transfer: Transfer) -> Call:
    return Call(port, transfer.seed, transfer.length)


def called(port: int, transfer: Transfer) -> Reported:
    return Reported(
        "call",
        (
            ("port", port),
            ("bytes", transfer.length),
            ("returned", transfer.length),
            ("matches", True),
        ),
    )


def digested(event: str, transfer: Transfer) -> Reported:
    return Reported(event, (("bytes", transfer.length), ("sha256", transfer.sha256)))


NETWORK_SCENARIO = replace(
    tests_image_scenario(
        "network-cases",
        "suites.network.main",
        (
            *case_lines(NETWORK, NETWORK_CASES[:2]),
            digest_line("upload", CASES_UPLOAD),
            *case_lines(NETWORK, NETWORK_CASES[2:3]),
            listening(LISTEN_PORT),
            inbound_line(CASES_INBOUND),
            *case_lines(NETWORK, NETWORK_CASES[3:]),
        ),
        Deadline.SESSION,
    ),
    devices=NETWORK_DEVICES,
    steps=(Step(listening(LISTEN_PORT), orders=(call(LISTEN_PORT, CASES_INBOUND),)),),
    network=Network(
        NetworkPlan(), (digested("sink", CASES_UPLOAD), called(LISTEN_PORT, CASES_INBOUND))
    ),
)


def interop_scenario(name: str, plan: NetworkPlan, retransmitted: str) -> Scenario:
    return replace(
        tests_image_scenario(
            name,
            "suites.network.interop",
            (
                digest_line("upload", INTEROP_UPLOAD),
                *case_lines(INTEROP, INTEROP_CASES[:1]),
                rf"^network: transfer=download bytes={INTEROP_DOWNLOAD.length} "
                rf"crc32={INTEROP_DOWNLOAD.crc32}$",
                *case_lines(INTEROP, INTEROP_CASES[1:2]),
                digest_line("relay", INTEROP_RELAY),
                *case_lines(INTEROP, INTEROP_CASES[2:3]),
                listening(LISTEN_PORT),
                inbound_line(INTEROP_INBOUND),
                *case_lines(INTEROP, INTEROP_CASES[3:4]),
                rf"^network: transfer=datagrams delivered={DATAGRAM_ROUNDS} "
                rf"bytes={DATAGRAM_BYTES}$",
                *case_lines(INTEROP, INTEROP_CASES[4:5]),
                digest_line("slow-reader", INTEROP_SLOW),
                *case_lines(INTEROP, INTEROP_CASES[5:6]),
                rf"^network: recovery retransmitted={retransmitted} out-of-order=\d+$",
                *case_lines(INTEROP, INTEROP_CASES[6:]),
            ),
            Deadline.SESSION,
        ),
        devices=NETWORK_DEVICES,
        steps=(Step(listening(LISTEN_PORT), orders=(call(LISTEN_PORT, INTEROP_INBOUND),)),),
        network=Network(
            plan,
            (
                digested("sink", INTEROP_UPLOAD),
                digested("sink", INTEROP_RELAY),
                digested("slow-sink", INTEROP_SLOW),
                called(LISTEN_PORT, INTEROP_INBOUND),
            ),
        ),
    )


INTEROP_IMPAIRED = interop_scenario(
    "interop-impaired-link", NetworkPlan(IMPAIRED, IMPAIRED, IMPAIRED_SEED), r"[1-9]\d*"
)
INTEROP_CLEAN = interop_scenario("interop-clean-link", NetworkPlan(), r"\d+")

FAULTS_SCENARIO = replace(
    tests_image_scenario(
        "network-faults",
        "suites.network.faults",
        (
            MALFORMED_READY,
            *case_lines(FAULTS, FAULT_CASES[:1]),
            FLOOD_READY,
            FLOOD_OVER,
            *case_lines(FAULTS, FAULT_CASES[1:2]),
            BLACKOUT_READY,
            *case_lines(FAULTS, FAULT_CASES[2:]),
        ),
        Deadline.SESSION,
    ),
    devices=NETWORK_DEVICES,
    steps=(
        Step(MALFORMED_READY, orders=(Inject(MALFORMED_FRAMES),)),
        Step(
            FLOOD_READY,
            orders=(Inject(connection_requests(INTRUDER, FLOOD_PORT, FLOOD_REQUESTS)),),
        ),
        Step(FLOOD_OVER, orders=(call(FLOOD_PORT, FLOOD_INBOUND),)),
        Step(BLACKOUT_READY, orders=(Darken(BLACKOUT_MILLISECONDS),)),
    ),
    network=Network(
        NetworkPlan(),
        (
            called(FLOOD_PORT, FLOOD_INBOUND),
            Reported("stopped", (("injected", len(MALFORMED_FRAMES) + FLOOD_REQUESTS),)),
        ),
    ),
)

NETWORK_SUITES: dict[str, tuple[Scenario, ...]] = {
    NETWORK: (NETWORK_SCENARIO,),
    INTEROP: (INTEROP_IMPAIRED, INTEROP_CLEAN),
}
NETWORK_FAULT_SUITES: dict[str, tuple[Scenario, ...]] = {FAULTS: (FAULTS_SCENARIO,)}
