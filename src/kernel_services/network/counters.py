FRAMES_RECEIVED = "frames-received"
FRAMES_SENT = "frames-sent"
FRAMES_MALFORMED = "frames-malformed"
FRAMES_FOREIGN = "frames-foreign"
FRAMES_UNSUPPORTED = "frames-unsupported"
FRAMES_UNSENT = "frames-unsent"
ARP_MALFORMED = "arp-malformed"
ARP_REQUESTS_ANSWERED = "arp-requests-answered"
ARP_UNRESOLVED = "arp-unresolved"
ARP_QUEUE_REFUSED = "arp-queue-refused"
IPV4_MALFORMED = "ipv4-malformed"
IPV4_BAD_CHECKSUM = "ipv4-bad-checksum"
IPV4_OPTIONS = "ipv4-options-refused"
IPV4_FOREIGN = "ipv4-foreign"
IPV4_BAD_SOURCE = "ipv4-bad-source"
IPV4_PROTOCOL = "ipv4-protocol-unsupported"
IPV4_UNROUTABLE = "ipv4-unroutable"
IPV4_TOO_LARGE = "ipv4-too-large"
FRAGMENTS_RECEIVED = "fragments-received"
FRAGMENTS_INVALID = "fragments-invalid"
FRAGMENTS_EXPIRED = "fragments-expired"
FRAGMENTS_EVICTED = "fragments-evicted"
DATAGRAMS_REASSEMBLED = "datagrams-reassembled"
ICMP_MALFORMED = "icmp-malformed"
ICMP_ECHO_ANSWERED = "icmp-echo-answered"
ICMP_LIMITED = "icmp-rate-limited"
ICMP_UNSUPPORTED = "icmp-unsupported"
UDP_MALFORMED = "udp-malformed"
UDP_BAD_CHECKSUM = "udp-bad-checksum"
UDP_NO_LISTENER = "udp-no-listener"
UDP_QUEUE_FULL = "udp-queue-full"
UDP_DELIVERED = "udp-delivered"
TCP_MALFORMED = "tcp-malformed"
TCP_BAD_CHECKSUM = "tcp-bad-checksum"
TCP_NO_SOCKET = "tcp-no-socket"
TCP_BACKLOG_FULL = "tcp-backlog-full"
TCP_RESETS_SENT = "tcp-resets-sent"
TCP_RESETS_RECEIVED = "tcp-resets-received"
TCP_RETRANSMITTED = "tcp-segments-retransmitted"
TCP_OUT_OF_ORDER = "tcp-out-of-order"
TCP_OUT_OF_ORDER_REFUSED = "tcp-out-of-order-refused"
TCP_UNACCEPTABLE = "tcp-unacceptable"
TCP_CONNECTIONS_OPENED = "tcp-connections-opened"
TCP_CONNECTIONS_FAILED = "tcp-connections-failed"

NAMES = (
    FRAMES_RECEIVED,
    FRAMES_SENT,
    FRAMES_MALFORMED,
    FRAMES_FOREIGN,
    FRAMES_UNSUPPORTED,
    FRAMES_UNSENT,
    ARP_MALFORMED,
    ARP_REQUESTS_ANSWERED,
    ARP_UNRESOLVED,
    ARP_QUEUE_REFUSED,
    IPV4_MALFORMED,
    IPV4_BAD_CHECKSUM,
    IPV4_OPTIONS,
    IPV4_FOREIGN,
    IPV4_BAD_SOURCE,
    IPV4_PROTOCOL,
    IPV4_UNROUTABLE,
    IPV4_TOO_LARGE,
    FRAGMENTS_RECEIVED,
    FRAGMENTS_INVALID,
    FRAGMENTS_EXPIRED,
    FRAGMENTS_EVICTED,
    DATAGRAMS_REASSEMBLED,
    ICMP_MALFORMED,
    ICMP_ECHO_ANSWERED,
    ICMP_LIMITED,
    ICMP_UNSUPPORTED,
    UDP_MALFORMED,
    UDP_BAD_CHECKSUM,
    UDP_NO_LISTENER,
    UDP_QUEUE_FULL,
    UDP_DELIVERED,
    TCP_MALFORMED,
    TCP_BAD_CHECKSUM,
    TCP_NO_SOCKET,
    TCP_BACKLOG_FULL,
    TCP_RESETS_SENT,
    TCP_RESETS_RECEIVED,
    TCP_RETRANSMITTED,
    TCP_OUT_OF_ORDER,
    TCP_OUT_OF_ORDER_REFUSED,
    TCP_UNACCEPTABLE,
    TCP_CONNECTIONS_OPENED,
    TCP_CONNECTIONS_FAILED,
)


class Counters:
    def __init__(self) -> None:
        self._values: dict[str, int] = {}
        for name in NAMES:
            self._values[name] = 0

    def count(self, name: str, amount: int = 1) -> None:
        self._values[name] += amount

    def value(self, name: str) -> int:
        return self._values[name]

    def values(self) -> list[int]:
        return [self._values[name] for name in NAMES]
