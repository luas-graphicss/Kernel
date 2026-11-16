from kernel_protocol.errors.codes import (
    CONNECTION_REFUSED,
    CONNECTION_RESET,
    OK,
    TIMED_OUT,
    UNREACHABLE,
)
from kernel_services.network.counters import (
    TCP_OUT_OF_ORDER,
    TCP_OUT_OF_ORDER_REFUSED,
    TCP_RESETS_RECEIVED,
    TCP_RESETS_SENT,
    TCP_RETRANSMITTED,
    TCP_UNACCEPTABLE,
    Counters,
)
from kernel_services.network.tcp.buffers import ByteQueue, OutOfOrderQueue
from kernel_services.network.tcp.congestion import CongestionControl
from kernel_services.network.tcp.retransmission import RoundTripEstimator
from kernel_services.network.tcp.segment import (
    FLAG_ACK,
    FLAG_FIN,
    FLAG_PSH,
    FLAG_RST,
    FLAG_SYN,
    MAXIMUM_WINDOW,
    NO_SEGMENT_SIZE,
    Segment,
)
from kernel_services.network.tcp.sequence import (
    HALF,
    advance,
    distance,
    is_at_or_before,
    is_before,
)
from kernel_services.network.tcp.settings import Settings

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable

CLOSED = 0
SYN_SENT = 1
SYN_RECEIVED = 2
ESTABLISHED = 3
FIN_WAIT_1 = 4
FIN_WAIT_2 = 5
CLOSE_WAIT = 6
CLOSING = 7
LAST_ACK = 8
TIME_WAIT = 9
STATE_NAMES = (
    "closed",
    "syn-sent",
    "syn-received",
    "established",
    "fin-wait-1",
    "fin-wait-2",
    "close-wait",
    "closing",
    "last-ack",
    "time-wait",
)
NEVER = 1 << 62
NOT_TIMED = -1
NOT_SENT = -1
DEFAULT_PEER_SEGMENT_BYTES = 536
SMALLEST_SEGMENT_BYTES = 64
HEADERS_BYTES = 40
RECEIVING_STATES = (ESTABLISHED, FIN_WAIT_1, FIN_WAIT_2)
SENDING_STATES = (ESTABLISHED, CLOSE_WAIT, FIN_WAIT_1, CLOSING, LAST_ACK)
WRITABLE_STATES = (ESTABLISHED, CLOSE_WAIT)
RESET_REPORTING_STATES = (ESTABLISHED, FIN_WAIT_1, FIN_WAIT_2, CLOSE_WAIT)


class Connection:
    def __init__(
        self,
        local_port: int,
        remote_address: int,
        remote_port: int,
        initial_sequence: int,
        settings: Settings,
        emit: "Callable[[Connection, Segment], None]",
        counters: Counters,
    ) -> None:
        self.local_port = local_port
        self.remote_address = remote_address
        self.remote_port = remote_port
        self.state = CLOSED
        self.error = OK
        self.is_passive = False
        self._settings = settings
        self._emit = emit
        self._counters = counters
        self._initial_sequence = initial_sequence
        self._unacknowledged = initial_sequence
        self._next = initial_sequence
        self._highest = initial_sequence
        self._peer_window = 0
        self._window_sequence = 0
        self._window_acknowledgment = initial_sequence
        self._expected = 0
        self._advertised_window = 0
        self._segment_bytes = settings.segment_bytes
        self._outgoing = ByteQueue()
        self._incoming = ByteQueue()
        self._out_of_order = OutOfOrderQueue(settings.out_of_order_segments)
        self._reserved_bytes = 0
        self._congestion = CongestionControl(self._segment_bytes)
        self._round_trip = RoundTripEstimator()
        self._retransmit_at = NEVER
        self._persist_at = NEVER
        self._linger_until = NEVER
        self._retransmissions = 0
        self._timed_sequence = NOT_TIMED
        self._timed_at = 0
        self._soft_error = OK
        self._is_start_acknowledged = False
        self._is_finishing = False
        self._finish_sequence = NOT_SENT
        self._is_finish_in_flight = False
        self._is_finish_acknowledged = False
        self._has_peer_finished = False

    def open_active(self, now: int) -> None:
        self.state = SYN_SENT
        self._next = advance(self._initial_sequence, 1)
        self._highest = self._next
        self._send_start(FLAG_SYN)
        self._timed_sequence = self._initial_sequence
        self._timed_at = now
        self._retransmit_at = now + self._round_trip.timeout

    def open_passive(self, request: Segment, now: int) -> None:
        self.is_passive = True
        self.state = SYN_RECEIVED
        self._accept_peer_start(request)
        self._next = advance(self._initial_sequence, 1)
        self._highest = self._next
        self._send_start(FLAG_SYN | FLAG_ACK)
        self._retransmit_at = now + self._round_trip.timeout

    def is_writable(self) -> bool:
        return self.state in WRITABLE_STATES and not self._is_finishing

    def writable_bytes(self) -> int:
        return self._settings.send_bytes - self._outgoing.size

    def readable_bytes(self) -> int:
        return self._incoming.size

    def is_at_end_of_input(self) -> bool:
        return self._incoming.size == 0 and (self._has_peer_finished or self.state == CLOSED)

    def unacknowledged_bytes(self) -> int:
        return self._outgoing.size

    def write(self, data: bytes, now: int) -> int:
        accepted = self.writable_bytes()
        if not self.is_writable() or accepted <= 0:
            return 0
        if accepted > len(data):
            accepted = len(data)
        accepted = self._settings.budget.reserve_up_to(accepted)
        if accepted == 0:
            return 0
        self._reserved_bytes += accepted
        self._outgoing.append(data if accepted == len(data) else data[:accepted])
        self._transmit(now)
        return accepted

    def peek(self, limit: int) -> bytes:
        return self._incoming.peek(0, limit)

    def read(self, limit: int) -> bytes:
        data = self._incoming.take(limit)
        self._release(len(data))
        if data and self.state in RECEIVING_STATES and self._has_window_reopened():
            self._acknowledge()
        return data

    def finish(self, now: int) -> None:
        if self.state == SYN_SENT:
            self._terminate(OK)
        elif self.state == SYN_RECEIVED:
            self.abort()
        elif self.state == ESTABLISHED:
            self._is_finishing = True
            self.state = FIN_WAIT_1
            self._transmit(now)
        elif self.state == CLOSE_WAIT:
            self._is_finishing = True
            self.state = LAST_ACK
            self._transmit(now)

    def abort(self) -> None:
        if self.state not in (CLOSED, SYN_SENT, TIME_WAIT):
            self._send_reset(self._next)
        self._terminate(OK)

    def discard_input(self) -> None:
        self._release(self._incoming.size)
        self._incoming.clear()

    def note_unreachable(self) -> None:
        self._soft_error = UNREACHABLE

    def hop_unresolved(self) -> None:
        if self.state == SYN_SENT:
            self._terminate(UNREACHABLE)
        else:
            self._soft_error = UNREACHABLE

    def refused_by_path(self) -> None:
        if self.state in (SYN_SENT, SYN_RECEIVED):
            self._terminate(UNREACHABLE)
        else:
            self._soft_error = UNREACHABLE

    def path_narrowed(self, next_hop_bytes: int, now: int) -> None:
        segment_bytes = next_hop_bytes - HEADERS_BYTES
        if segment_bytes < SMALLEST_SEGMENT_BYTES:
            segment_bytes = SMALLEST_SEGMENT_BYTES
        if segment_bytes >= self._segment_bytes or self.state not in SENDING_STATES:
            return
        self._segment_bytes = segment_bytes
        self._congestion.segment_bytes = segment_bytes
        self._rewind()
        self._transmit(now)

    def next_deadline(self) -> int:
        deadline = self._retransmit_at
        if self._persist_at < deadline:
            deadline = self._persist_at
        if self._linger_until < deadline:
            deadline = self._linger_until
        return deadline

    def timers_expire(self, now: int) -> None:
        if self._retransmit_at <= now:
            self._retransmission_expires(now)
        if self._persist_at <= now and self.state != CLOSED:
            self._persist_expires(now)
        if self._linger_until <= now and self.state == TIME_WAIT:
            self._terminate(OK)

    def segment_arrives(self, segment: Segment, now: int) -> None:
        if self.state == CLOSED:
            return
        if self.state == SYN_SENT:
            self._arrives_while_connecting(segment, now)
            return
        if not self._accepts(segment):
            self._counters.count(TCP_UNACCEPTABLE)
            if self.state == SYN_RECEIVED and segment.has(FLAG_SYN):
                self._send_start(FLAG_SYN | FLAG_ACK)
            elif not segment.has(FLAG_RST):
                self._acknowledge()
            return
        if segment.has(FLAG_RST):
            self._reset_arrives(segment)
            return
        if segment.has(FLAG_SYN):
            self._acknowledge()
            return
        if not segment.has(FLAG_ACK) or not self._acknowledgment_arrives(segment, now):
            return
        if self.state != CLOSED:
            self._payload_arrives(segment, now)

    def _arrives_while_connecting(self, segment: Segment, now: int) -> None:
        answers_start = False
        if segment.has(FLAG_ACK):
            answers_start = is_before(
                self._initial_sequence, segment.acknowledgment
            ) and is_at_or_before(segment.acknowledgment, self._next)
            if not answers_start:
                if not segment.has(FLAG_RST):
                    self._send_reset(segment.acknowledgment)
                return
        if segment.has(FLAG_RST):
            if answers_start:
                self._counters.count(TCP_RESETS_RECEIVED)
                self._terminate(CONNECTION_REFUSED)
            return
        if not segment.has(FLAG_SYN):
            return
        self._accept_peer_start(segment)
        if not answers_start:
            self.state = SYN_RECEIVED
            self._send_start(FLAG_SYN | FLAG_ACK)
            self._retransmit_at = now + self._round_trip.timeout
            return
        self._start_acknowledged(segment.acknowledgment, now)
        self._window_acknowledgment = segment.acknowledgment
        self._retransmit_at = NEVER
        self.state = ESTABLISHED
        self._acknowledge()

    def _accept_peer_start(self, segment: Segment) -> None:
        self._expected = advance(segment.sequence, 1)
        self._peer_window = segment.window
        self._window_sequence = segment.sequence
        announced = segment.segment_size
        if announced == NO_SEGMENT_SIZE:
            announced = DEFAULT_PEER_SEGMENT_BYTES
        if announced < SMALLEST_SEGMENT_BYTES:
            announced = SMALLEST_SEGMENT_BYTES
        if announced < self._segment_bytes:
            self._segment_bytes = announced
        self._congestion.use_segment_bytes(self._segment_bytes)

    def _start_acknowledged(self, acknowledgment: int, now: int) -> None:
        self._is_start_acknowledged = True
        self._unacknowledged = acknowledgment
        self._retransmissions = 0
        self._sample_round_trip(acknowledgment, now)

    def _accepts(self, segment: Segment) -> bool:
        length = segment.length()
        window = self._window()
        offset = distance(segment.sequence, self._expected)
        if length == 0 or window == 0:
            return offset == 0 or (length == 0 and offset < window)
        last = distance(advance(segment.sequence, length - 1), self._expected)
        return offset < window or last < window

    def _reset_arrives(self, segment: Segment) -> None:
        if segment.sequence != self._expected:
            self._acknowledge()
            return
        self._counters.count(TCP_RESETS_RECEIVED)
        if self.state in RESET_REPORTING_STATES:
            self._terminate(CONNECTION_RESET)
        elif self.state == SYN_RECEIVED and not self.is_passive:
            self._terminate(CONNECTION_REFUSED)
        else:
            self._terminate(OK)

    def _acknowledgment_arrives(self, segment: Segment, now: int) -> bool:
        acknowledgment = segment.acknowledgment
        if self.state == SYN_RECEIVED:
            if not is_before(self._unacknowledged, acknowledgment) or is_before(
                self._next, acknowledgment
            ):
                self._send_reset(acknowledgment)
                return False
            self.state = ESTABLISHED
        if is_before(self._highest, acknowledgment):
            self._acknowledge()
            return False
        if is_before(self._unacknowledged, acknowledgment):
            self._advance(acknowledgment, now)
        elif acknowledgment == self._unacknowledged:
            self._duplicate_arrives(segment, now)
        self._learn_peer_window(segment)
        self._finish_progresses(now)
        if self.state != CLOSED:
            self._transmit(now)
        return True

    def _advance(self, acknowledgment: int, now: int) -> None:
        data_bytes = distance(acknowledgment, self._unacknowledged)
        if not self._is_start_acknowledged:
            self._is_start_acknowledged = True
            data_bytes -= 1
        if self._finish_sequence != NOT_SENT and acknowledgment == advance(
            self._finish_sequence, 1
        ):
            self._is_finish_acknowledged = True
            self._is_finish_in_flight = False
            data_bytes -= 1
        self._outgoing.discard(data_bytes)
        self._release(data_bytes)
        self._sample_round_trip(acknowledgment, now)
        self._unacknowledged = acknowledgment
        if is_before(self._next, acknowledgment):
            self._next = acknowledgment
        self._retransmissions = 0
        if not self._congestion.is_recovering:
            self._congestion.acknowledged(data_bytes)
        elif is_at_or_before(self._congestion.recovery_point, acknowledgment):
            self._congestion.leave_recovery()
        else:
            self._congestion.partially_acknowledged(data_bytes)
            self._retransmit_first()
        if self._unacknowledged == self._next:
            self._retransmit_at = NEVER
        else:
            self._retransmit_at = now + self._round_trip.timeout

    def _duplicate_arrives(self, segment: Segment, now: int) -> None:
        if segment.data or segment.has(FLAG_FIN) or segment.window != self._peer_window:
            return
        if self._unacknowledged == self._next:
            return
        if self._congestion.duplicate_acknowledgment():
            self._congestion.enter_recovery(self._flight_bytes(), self._highest)
            self._retransmit_first()
            self._retransmit_at = now + self._round_trip.timeout

    def _learn_peer_window(self, segment: Segment) -> None:
        is_newer = is_before(self._window_sequence, segment.sequence) or (
            self._window_sequence == segment.sequence
            and is_at_or_before(self._window_acknowledgment, segment.acknowledgment)
        )
        if not is_newer:
            return
        self._peer_window = segment.window
        self._window_sequence = segment.sequence
        self._window_acknowledgment = segment.acknowledgment
        if self._peer_window != 0:
            self._persist_at = NEVER

    def _finish_progresses(self, now: int) -> None:
        if not self._is_finish_acknowledged:
            return
        if self.state == FIN_WAIT_1:
            self.state = FIN_WAIT_2
        elif self.state == CLOSING:
            self._linger(now)
        elif self.state == LAST_ACK:
            self._terminate(OK)

    def _payload_arrives(self, segment: Segment, now: int) -> None:
        finishes = segment.has(FLAG_FIN)
        if self.state == TIME_WAIT:
            if finishes:
                self._acknowledge()
                self._linger(now)
            return
        if not segment.data and not finishes:
            return
        if self.state not in RECEIVING_STATES:
            if finishes:
                self._acknowledge()
            return
        data = segment.data
        offset = distance(segment.sequence, self._expected)
        if offset >= HALF:
            data = data[distance(self._expected, segment.sequence) :]
            offset = 0
        window = self._window()
        if offset + len(data) > window:
            data = data[: window - offset] if window > offset else b""
            finishes = False
        if offset != 0:
            self._hold_out_of_order(advance(self._expected, offset), data)
        elif self._take_in_order(data) and finishes:
            self._peer_finishes(now)
        self._acknowledge()

    def _take_in_order(self, data: bytes) -> bool:
        if data and not self._reserve(len(data)):
            return False
        while data:
            self._incoming.append(data)
            self._expected = advance(self._expected, len(data))
            held_bytes = self._out_of_order.held_bytes
            data = self._out_of_order.take_ready(self._expected)
            self._release(held_bytes - self._out_of_order.held_bytes - len(data))
        return self._out_of_order.count() == 0

    def _hold_out_of_order(self, sequence: int, data: bytes) -> None:
        if not data:
            return
        self._counters.count(TCP_OUT_OF_ORDER)
        held_before = self._out_of_order.held_bytes
        if not self._reserve(len(data)):
            self._counters.count(TCP_OUT_OF_ORDER_REFUSED)
            return
        if not self._out_of_order.insert(self._expected, sequence, data):
            self._counters.count(TCP_OUT_OF_ORDER_REFUSED)
        self._release(len(data) - (self._out_of_order.held_bytes - held_before))

    def _peer_finishes(self, now: int) -> None:
        self._expected = advance(self._expected, 1)
        self._has_peer_finished = True
        if self.state == ESTABLISHED:
            self.state = CLOSE_WAIT
        elif self.state == FIN_WAIT_1:
            self.state = CLOSING
        elif self.state == FIN_WAIT_2:
            self._linger(now)

    def _transmit(self, now: int) -> None:
        if self.state not in SENDING_STATES or not self._is_start_acknowledged:
            return
        while self._transmit_one(now):
            continue
        is_probing = self._persist_at != NEVER
        if self._unacknowledged != self._next and self._retransmit_at == NEVER and not is_probing:
            self._retransmit_at = now + self._round_trip.timeout
        if (
            self._peer_window == 0
            and self._unacknowledged == self._next
            and self._outgoing.size != 0
            and self._persist_at == NEVER
        ):
            self._persist_at = now + self._round_trip.timeout

    def _transmit_one(self, now: int) -> bool:
        in_flight = distance(self._next, self._unacknowledged)
        sent_bytes = in_flight - 1 if self._is_finish_in_flight else in_flight
        unsent = self._outgoing.size - sent_bytes
        usable = self._congestion.window
        if usable > self._peer_window:
            usable = self._peer_window
        usable -= in_flight
        can_finish = self._is_finishing and not self._is_finish_in_flight
        can_finish = can_finish and not self._is_finish_acknowledged
        if unsent == 0 or usable <= 0:
            if unsent == 0 and can_finish:
                self._send(self._next, FLAG_FIN | FLAG_ACK, b"")
                self._sent(now, 0, True)
            return False
        length = unsent
        if length > usable:
            length = usable
        if length > self._segment_bytes:
            length = self._segment_bytes
        flags = FLAG_ACK
        finishes = length == unsent and can_finish
        if length == unsent:
            flags |= FLAG_PSH
        if finishes:
            flags |= FLAG_FIN
        self._send(self._next, flags, self._outgoing.peek(sent_bytes, length))
        self._sent(now, length, finishes)
        return not finishes

    def _sent(self, now: int, data_bytes: int, finishes: bool) -> None:
        is_first_transmission = not is_before(self._next, self._highest)
        if is_first_transmission and self._timed_sequence == NOT_TIMED:
            self._timed_sequence = self._next
            self._timed_at = now
        if not is_first_transmission:
            self._counters.count(TCP_RETRANSMITTED)
        self._next = advance(self._next, data_bytes)
        if finishes:
            self._finish_sequence = self._next
            self._is_finish_in_flight = True
            self._next = advance(self._next, 1)
        if is_before(self._highest, self._next):
            self._highest = self._next
        if self._retransmit_at == NEVER:
            self._retransmit_at = now + self._round_trip.timeout

    def _retransmit_first(self) -> None:
        self._counters.count(TCP_RETRANSMITTED)
        self._timed_sequence = NOT_TIMED
        length = self._outgoing.size
        if length > self._segment_bytes:
            length = self._segment_bytes
        sent_bytes = distance(self._highest, self._unacknowledged)
        if self._finish_sequence != NOT_SENT:
            sent_bytes -= 1
        if length > sent_bytes:
            length = sent_bytes
        if length == 0:
            self._send(self._unacknowledged, FLAG_FIN | FLAG_ACK, b"")
            return
        self._send(self._unacknowledged, FLAG_ACK, self._outgoing.peek(0, length))

    def _retransmission_expires(self, now: int) -> None:
        limit = self._settings.retransmissions
        if self.state in (SYN_SENT, SYN_RECEIVED):
            limit = self._settings.handshake_retransmissions
        if self._retransmissions == limit:
            self._give_up()
            return
        self._retransmissions += 1
        self._round_trip.back_off()
        self._timed_sequence = NOT_TIMED
        if self.state in (SYN_SENT, SYN_RECEIVED):
            self._counters.count(TCP_RETRANSMITTED)
            self._send_start(FLAG_SYN if self.state == SYN_SENT else FLAG_SYN | FLAG_ACK)
            self._retransmit_at = now + self._round_trip.timeout
            return
        self._congestion.timed_out(self._flight_bytes())
        self._rewind()
        self._retransmit_at = NEVER
        self._transmit(now)

    def _persist_expires(self, now: int) -> None:
        if self._peer_window != 0 or self._outgoing.size == 0:
            self._persist_at = NEVER
            return
        self._rewind()
        self._send(self._next, FLAG_ACK, self._outgoing.peek(0, 1))
        self._next = advance(self._next, 1)
        if is_before(self._highest, self._next):
            self._highest = self._next
        self._round_trip.back_off()
        self._persist_at = now + self._round_trip.timeout

    def _rewind(self) -> None:
        self._next = self._unacknowledged
        self._is_finish_in_flight = False

    def _give_up(self) -> None:
        if self.state not in (SYN_SENT, SYN_RECEIVED):
            self._send_reset(self._next)
        self._terminate(self._soft_error if self._soft_error != OK else TIMED_OUT)

    def _linger(self, now: int) -> None:
        self.state = TIME_WAIT
        self._retransmit_at = NEVER
        self._persist_at = NEVER
        self._linger_until = now + 2 * self._settings.segment_lifetime_nanoseconds

    def _terminate(self, error: int) -> None:
        self.state = CLOSED
        self._retransmit_at = NEVER
        self._persist_at = NEVER
        self._linger_until = NEVER
        self._release(self._outgoing.size + self._out_of_order.held_bytes)
        self._outgoing.clear()
        self._out_of_order.clear()
        if error != OK:
            self.error = error
            self.discard_input()

    def _sample_round_trip(self, acknowledgment: int, now: int) -> None:
        if self._timed_sequence != NOT_TIMED and is_before(self._timed_sequence, acknowledgment):
            self._round_trip.sample(now - self._timed_at)
            self._timed_sequence = NOT_TIMED

    def _flight_bytes(self) -> int:
        return distance(self._next, self._unacknowledged)

    def _window(self) -> int:
        window = self._settings.receive_bytes - self._incoming.size
        if window < 0:
            return 0
        if window > MAXIMUM_WINDOW:
            return MAXIMUM_WINDOW
        return window

    def _has_window_reopened(self) -> bool:
        gained = self._window() - self._advertised_window
        return gained >= self._segment_bytes or (self._advertised_window == 0 and gained > 0)

    def _reserve(self, amount: int) -> bool:
        if not self._settings.budget.reserve(amount):
            return False
        self._reserved_bytes += amount
        return True

    def _release(self, amount: int) -> None:
        self._reserved_bytes -= amount
        self._settings.budget.release(amount)

    def _acknowledge(self) -> None:
        self._send(self._next, FLAG_ACK, b"")

    def _send_start(self, flags: int) -> None:
        self._send(self._initial_sequence, flags, b"", self._settings.segment_bytes)

    def _send_reset(self, sequence: int) -> None:
        self._counters.count(TCP_RESETS_SENT)
        self._emit(
            self,
            Segment(
                self.local_port, self.remote_port, sequence, 0, FLAG_RST, 0, NO_SEGMENT_SIZE, b""
            ),
        )

    def _send(
        self, sequence: int, flags: int, data: bytes, segment_size: int = NO_SEGMENT_SIZE
    ) -> None:
        self._advertised_window = self._window()
        acknowledgment = self._expected if flags & FLAG_ACK else 0
        self._emit(
            self,
            Segment(
                self.local_port,
                self.remote_port,
                sequence,
                acknowledgment,
                flags,
                self._advertised_window,
                segment_size,
                data,
            ),
        )
