from kernel_services.network.budget import BufferBudget
from kernel_services.network.counters import (
    ICMP_ECHO_ANSWERED,
    ICMP_LIMITED,
    ICMP_MALFORMED,
    ICMP_UNSUPPORTED,
    IPV4_PROTOCOL,
    Counters,
)
from kernel_services.network.icmp.echo import EchoTracker
from kernel_services.network.icmp.limiter import RateLimiter
from kernel_services.network.icmp.message import (
    CODE_NONE,
    CODE_PORT_UNREACHABLE,
    CODE_PROTOCOL_UNREACHABLE,
    MAXIMUM_ECHO_BYTES,
    TYPE_ECHO_REPLY,
    TYPE_ECHO_REQUEST,
    TYPE_UNREACHABLE,
    decode_message,
    decode_quotation,
    encode_message,
    quote,
)
from kernel_services.network.interface import Interface
from kernel_services.network.ipv4.header import (
    HEADER_BYTES,
    PROTOCOL_ICMP,
    PROTOCOL_TCP,
    PROTOCOL_UDP,
    Datagram,
    decode_datagram,
)
from kernel_services.network.ipv4.reassembly import Reassembler
from kernel_services.network.ipv4.routing import Route
from kernel_services.network.limits import (
    ICMP_BURST,
    ICMP_INTERVAL_NANOSECONDS,
    REASSEMBLY_BYTES,
    REASSEMBLY_DATAGRAMS,
    REASSEMBLY_LIFETIME_NANOSECONDS,
    RESET_BURST,
    RESET_INTERVAL_NANOSECONDS,
    SOCKET_BUFFER_BYTES,
    SOCKETS_TOTAL,
    TCP_CONNECTIONS,
    TCP_HANDSHAKE_RETRANSMISSIONS,
    TCP_OUT_OF_ORDER_SEGMENTS,
    TCP_RECEIVE_BYTES,
    TCP_RETRANSMISSIONS,
    TCP_SEGMENT_LIFETIME_NANOSECONDS,
    TCP_SEND_BYTES,
    UDP_QUEUE_BYTES,
    UDP_QUEUE_DATAGRAMS,
)
from kernel_services.network.tcp.layer import TcpLayer
from kernel_services.network.tcp.settings import Settings
from kernel_services.network.udp.datagram import decode_datagram as decode_udp
from kernel_services.network.udp.ports import UdpLayer

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable

TRANSPORT_HEADERS_BYTES = 40
NO_REST = 0
IMMEDIATELY = 0


def connection_settings(mtu: int, budget: BufferBudget) -> Settings:
    return Settings(
        mtu - TRANSPORT_HEADERS_BYTES,
        TCP_SEND_BYTES,
        TCP_RECEIVE_BYTES,
        TCP_OUT_OF_ORDER_SEGMENTS,
        TCP_SEGMENT_LIFETIME_NANOSECONDS,
        TCP_RETRANSMISSIONS,
        TCP_HANDSHAKE_RETRANSMISSIONS,
        budget,
    )


class Stack:
    def __init__(
        self, hardware: bytes, route: Route, mtu: int, entropy: "Callable[[int], bytes]"
    ) -> None:
        self.counters = Counters()
        self.budget = BufferBudget(SOCKET_BUFFER_BYTES)
        self.interface = Interface(hardware, route, mtu, self.counters)
        self.echoes = EchoTracker(SOCKETS_TOTAL)
        self.udp = UdpLayer(
            route.address,
            self.interface.send,
            entropy,
            self.counters,
            self.budget,
            UDP_QUEUE_DATAGRAMS,
            UDP_QUEUE_BYTES,
        )
        self.tcp = TcpLayer(
            route.address,
            self.interface.send,
            connection_settings(mtu, self.budget),
            entropy,
            self.counters,
            TCP_CONNECTIONS,
            RateLimiter(RESET_BURST, RESET_INTERVAL_NANOSECONDS),
        )
        self._reassembler = Reassembler(
            REASSEMBLY_DATAGRAMS, REASSEMBLY_BYTES, REASSEMBLY_LIFETIME_NANOSECONDS, self.counters
        )
        self._errors = RateLimiter(ICMP_BURST, ICMP_INTERVAL_NANOSECONDS)
        self.now = 0

    def advance(self, now: int) -> None:
        self.now = now
        self.interface.now = now

    def frame_arrives(self, frame: bytes, now: int) -> None:
        self.advance(now)
        datagram = self.interface.frame_arrives(frame)
        if datagram is not None:
            self._datagram_arrives(datagram, now)

    def run(self, now: int) -> None:
        self.advance(now)
        for encoded in self.interface.take_local():
            datagram = decode_datagram(encoded, self.counters)
            if datagram is not None:
                self._datagram_arrives(datagram, now)
        for hop in self.interface.timers_expire():
            self.tcp.hop_unreachable(self.interface.next_hop, hop)
            self.echoes.hop_unreachable(self.interface.next_hop, hop)
        self._reassembler.expire(now)
        self.tcp.timers_expire(now)

    def next_deadline(self, none: int) -> int:
        if self.interface.has_local():
            return IMMEDIATELY
        deadline = self.interface.next_deadline(none)
        deadline = self._reassembler.next_deadline(deadline)
        return self.tcp.next_deadline(deadline)

    def take_frames(self) -> list[bytes]:
        return self.interface.take_frames()

    def send_echo(self, destination: int, identity: int, data: bytes) -> int:
        request = encode_message(TYPE_ECHO_REQUEST, CODE_NONE, identity, data)
        return self.interface.send(destination, PROTOCOL_ICMP, request)

    def reassembling(self) -> int:
        return self._reassembler.pending()

    def _datagram_arrives(self, datagram: Datagram, now: int) -> None:
        if datagram.is_fragment():
            payload = self._reassembler.add(datagram, now)
            if payload is None:
                return
            datagram = Datagram(
                datagram.source,
                datagram.destination,
                datagram.protocol,
                datagram.identification,
                0,
                payload,
                datagram.header,
            )
        is_for_this_station = datagram.destination == self.interface.route.address
        if datagram.protocol == PROTOCOL_ICMP:
            self._control_arrives(datagram, now)
        elif datagram.protocol == PROTOCOL_UDP:
            self._user_datagram_arrives(datagram, is_for_this_station, now)
        elif datagram.protocol == PROTOCOL_TCP:
            if is_for_this_station:
                self.tcp.segment_arrives(datagram.source, datagram.payload, now)
        else:
            self.counters.count(IPV4_PROTOCOL)
            if is_for_this_station:
                self._report(datagram, CODE_PROTOCOL_UNREACHABLE, now)

    def _user_datagram_arrives(
        self, datagram: Datagram, is_for_this_station: bool, now: int
    ) -> None:
        received = decode_udp(
            datagram.payload, datagram.source, datagram.destination, self.counters
        )
        if received is None:
            return
        if not self.udp.datagram_arrives(datagram.source, received) and is_for_this_station:
            self._report(datagram, CODE_PORT_UNREACHABLE, now)

    def _control_arrives(self, datagram: Datagram, now: int) -> None:
        message = decode_message(datagram.payload)
        if message is None:
            self.counters.count(ICMP_MALFORMED)
            return
        if message.kind == TYPE_ECHO_REQUEST:
            self._answer_echo(datagram, message.rest, message.body, now)
        elif message.kind == TYPE_ECHO_REPLY:
            self.echoes.reply_arrives(datagram.source, message, now)
        elif message.kind == TYPE_UNREACHABLE:
            self._path_reports(message.code, message.next_hop_mtu(), message.body, now)
        else:
            self.counters.count(ICMP_UNSUPPORTED)

    def _answer_echo(self, datagram: Datagram, rest: int, body: bytes, now: int) -> None:
        is_for_this_station = datagram.destination == self.interface.route.address
        if not is_for_this_station or len(body) > MAXIMUM_ECHO_BYTES:
            self.counters.count(ICMP_UNSUPPORTED)
            return
        if not self._errors.allow(now):
            self.counters.count(ICMP_LIMITED)
            return
        reply = encode_message(TYPE_ECHO_REPLY, CODE_NONE, rest, body)
        self.interface.send(datagram.source, PROTOCOL_ICMP, reply)
        self.counters.count(ICMP_ECHO_ANSWERED)

    def _path_reports(self, code: int, next_hop_bytes: int, body: bytes, now: int) -> None:
        quotation = decode_quotation(body)
        if quotation is None or quotation.source != self.interface.route.address:
            self.counters.count(ICMP_MALFORMED)
            return
        if quotation.protocol == PROTOCOL_TCP:
            self.tcp.path_reports(
                quotation.destination, quotation.transport, code, next_hop_bytes, now
            )
        elif quotation.protocol == PROTOCOL_UDP:
            self.udp.path_reports(quotation.transport, code)
        elif quotation.protocol == PROTOCOL_ICMP:
            self.echoes.path_reports(quotation.destination, quotation.transport)

    def _report(self, datagram: Datagram, code: int, now: int) -> None:
        if not self._errors.allow(now):
            self.counters.count(ICMP_LIMITED)
            return
        quoted = quote(datagram.header, datagram.payload)
        if len(quoted) < HEADER_BYTES:
            return
        report = encode_message(TYPE_UNREACHABLE, code, NO_REST, quoted)
        self.interface.send(datagram.source, PROTOCOL_ICMP, report)
