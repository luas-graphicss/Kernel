from suites.network import (
    authority_case,
    datagram_case,
    interface_case,
    listener_case,
    quota_case,
    stream_case,
    waiting_case,
)
from suites.network.platform import run_with_network

CASES = (
    ("interface-and-echo", interface_case.run),
    ("datagrams", datagram_case.run),
    ("streams", stream_case.run),
    ("listening", listener_case.run),
    ("deadlines-cancellation-and-backpressure", waiting_case.run),
    ("socket-quota", quota_case.run),
    ("access-rights", authority_case.run),
)


def main() -> bool:
    return run_with_network("network", CASES)
