from kernel_protocol.errors.codes import LIMIT_EXCEEDED, MESSAGE_TOO_LARGE, OK, UNREACHABLE
from kernel_services.network.arp.cache import NeighborCache
from kernel_services.network.arp.packet import (
    OPERATION_REPLY,
    OPERATION_REQUEST,
    ArpPacket,
    decode_packet,
    encode_packet,
)
from kernel_services.network.arp.resolution import PendingResolutions
from kernel_services.network.counters import (
    ARP_MALFORMED,
    ARP_QUEUE_REFUSED,
    ARP_REQUESTS_ANSWERED,
    ARP_UNRESOLVED,
    FRAMES_FOREIGN,
    FRAMES_MALFORMED,
    FRAMES_RECEIVED,
    FRAMES_SENT,
    FRAMES_UNSENT,
    FRAMES_UNSUPPORTED,
    IPV4_BAD_SOURCE,
    IPV4_FOREIGN,
    IPV4_TOO_LARGE,
    IPV4_UNROUTABLE,
    Counters,
)
from kernel_services.network.ethernet.frame import (
    BROADCAST,
    ETHERTYPE_ARP,
    ETHERTYPE_IPV4,
    UNSPECIFIED,
    decode_frame,
    encode_frame,
)
from kernel_services.network.ipv4.address import is_host, is_loopback
from kernel_services.network.ipv4.fragmentation import split
from kernel_services.network.ipv4.header import (
    DONT_FRAGMENT,
    HEADER_BYTES,
    MAXIMUM_DATAGRAM_BYTES,
    Datagram,
    decode_datagram,
    encode_datagram,
)
from kernel_services.network.ipv4.routing import NO_GATEWAY, Route
from kernel_services.network.limits import (
    LOCAL_DATAGRAMS,
    NEIGHBOR_LIFETIME_NANOSECONDS,
    NEIGHBORS,
    OUTBOX_FRAMES,
    RESOLUTION_ATTEMPTS,
    RESOLUTION_DATAGRAMS,
    RESOLUTION_RETRY_NANOSECONDS,
    RESOLUTION_TARGETS,
)

IDENTIFICATION_MASK = 0xFFFF
NOT_FRAGMENTED = 0


class Interface:
    def __init__(self, hardware: bytes, route: Route, mtu: int, counters: Counters) -> None:
        self.hardware = hardware
        self.route = route
        self.mtu = mtu
        self.now = 0
        self.is_linked = True
        self.neighbors = NeighborCache(NEIGHBORS, NEIGHBOR_LIFETIME_NANOSECONDS)
        self._counters = counters
        self._resolutions = PendingResolutions(
            RESOLUTION_TARGETS,
            RESOLUTION_DATAGRAMS,
            RESOLUTION_ATTEMPTS,
            RESOLUTION_RETRY_NANOSECONDS,
        )
        self._frames: list[bytes] = []
        self._local: list[bytes] = []
        self._identification = 0

    def take_frames(self) -> list[bytes]:
        frames = self._frames
        self._frames = []
        return frames

    def take_local(self) -> list[bytes]:
        local = self._local
        self._local = []
        return local

    def has_local(self) -> bool:
        return len(self._local) != 0

    def link_changed(self, is_linked: bool) -> None:
        self.is_linked = is_linked
        if not is_linked:
            self.neighbors.clear()
            self._resolutions.clear()
            self._frames = []

    def next_hop(self, destination: int) -> int:
        return self.route.next_hop(destination)

    def frame_arrives(self, data: bytes) -> Datagram | None:
        self._counters.count(FRAMES_RECEIVED)
        frame = decode_frame(data)
        if frame is None:
            self._counters.count(FRAMES_MALFORMED)
            return None
        if frame.destination != self.hardware and frame.destination != BROADCAST:
            self._counters.count(FRAMES_FOREIGN)
            return None
        if frame.ethertype == ETHERTYPE_ARP:
            self._resolution_arrives(frame.source, frame.payload)
            return None
        if frame.ethertype != ETHERTYPE_IPV4:
            self._counters.count(FRAMES_UNSUPPORTED)
            return None
        datagram = decode_datagram(frame.payload, self._counters)
        if datagram is None:
            return None
        if datagram.source == self.route.address:
            self._counters.count(IPV4_BAD_SOURCE)
            return None
        if datagram.destination != self.route.address and not self.route.is_broadcast(
            datagram.destination
        ):
            self._counters.count(IPV4_FOREIGN)
            return None
        return datagram

    def send(
        self, destination: int, protocol: int, payload: bytes, dont_fragment: bool = False
    ) -> int:
        if HEADER_BYTES + len(payload) > MAXIMUM_DATAGRAM_BYTES:
            self._counters.count(IPV4_TOO_LARGE)
            return MESSAGE_TOO_LARGE
        if destination == self.route.address or is_loopback(destination):
            return self._send_local(destination, protocol, payload)
        is_broadcast = self.route.is_broadcast(destination)
        hop = destination if is_broadcast else self._hop_towards(destination)
        if hop == NO_GATEWAY or not self.is_linked:
            self._counters.count(IPV4_UNROUTABLE)
            return UNREACHABLE
        if HEADER_BYTES + len(payload) <= self.mtu:
            pieces = [(DONT_FRAGMENT if dont_fragment else NOT_FRAGMENTED, payload)]
        elif dont_fragment:
            self._counters.count(IPV4_TOO_LARGE)
            return MESSAGE_TOO_LARGE
        else:
            pieces = split(payload, self.mtu)
        self._identification = (self._identification + 1) & IDENTIFICATION_MASK
        datagrams = [
            encode_datagram(
                self.route.address,
                destination,
                protocol,
                self._identification,
                fragmentation,
                piece,
            )
            for fragmentation, piece in pieces
        ]
        if is_broadcast:
            return self._transmit(BROADCAST, datagrams)
        hardware = self.neighbors.lookup(hop, self.now)
        if hardware is not None:
            return self._transmit(hardware, datagrams)
        return self._hold(hop, datagrams)

    def timers_expire(self) -> list[int]:
        retried, abandoned = self._resolutions.due(self.now)
        for target in retried:
            self._ask(target)
        for _target in abandoned:
            self._counters.count(ARP_UNRESOLVED)
        self.neighbors.expire(self.now)
        return abandoned

    def next_deadline(self, none: int) -> int:
        return self._resolutions.next_deadline(none)

    def _hop_towards(self, destination: int) -> int:
        if not is_host(destination):
            return NO_GATEWAY
        return self.route.next_hop(destination)

    def _send_local(self, destination: int, protocol: int, payload: bytes) -> int:
        if len(self._local) == LOCAL_DATAGRAMS:
            return LIMIT_EXCEEDED
        self._identification = (self._identification + 1) & IDENTIFICATION_MASK
        self._local.append(
            encode_datagram(
                self.route.address,
                destination,
                protocol,
                self._identification,
                NOT_FRAGMENTED,
                payload,
            )
        )
        return OK

    def _transmit(self, hardware: bytes, datagrams: list[bytes]) -> int:
        for datagram in datagrams:
            self._queue(encode_frame(hardware, self.hardware, ETHERTYPE_IPV4, datagram))
        return OK

    def _hold(self, hop: int, datagrams: list[bytes]) -> int:
        for datagram in datagrams:
            if not self._resolutions.has_room(hop):
                self._counters.count(ARP_QUEUE_REFUSED)
                return LIMIT_EXCEEDED
            if self._resolutions.hold(hop, datagram, self.now):
                self._ask(hop)
        return OK

    def _queue(self, frame: bytes) -> None:
        if len(self._frames) == OUTBOX_FRAMES or not self.is_linked:
            self._counters.count(FRAMES_UNSENT)
            return
        self._frames.append(frame)
        self._counters.count(FRAMES_SENT)

    def _ask(self, target: int) -> None:
        request = ArpPacket(
            OPERATION_REQUEST, self.hardware, self.route.address, UNSPECIFIED, target
        )
        self._queue(encode_frame(BROADCAST, self.hardware, ETHERTYPE_ARP, encode_packet(request)))

    def _resolution_arrives(self, source: bytes, payload: bytes) -> None:
        packet = decode_packet(payload)
        if packet is None or packet.sender_hardware != source:
            self._counters.count(ARP_MALFORMED)
            return
        sender = packet.sender_address
        route = self.route
        if sender == route.address or not route.is_on_link(sender):
            self._counters.count(ARP_MALFORMED)
            return
        if not route.names_a_station(sender):
            self._counters.count(ARP_MALFORMED)
            return
        is_known = self.neighbors.lookup(sender, self.now) is not None
        if packet.target_address != route.address and not is_known:
            return
        self.neighbors.learn(sender, source, self.now)
        self._transmit(source, self._resolutions.release(sender))
        if packet.operation == OPERATION_REQUEST and packet.target_address == route.address:
            reply = ArpPacket(OPERATION_REPLY, self.hardware, route.address, source, sender)
            self._queue(encode_frame(source, self.hardware, ETHERTYPE_ARP, encode_packet(reply)))
            self._counters.count(ARP_REQUESTS_ANSWERED)
