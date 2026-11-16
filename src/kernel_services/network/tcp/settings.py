from kernel_services.network.budget import BufferBudget


class Settings:
    def __init__(
        self,
        segment_bytes: int,
        send_bytes: int,
        receive_bytes: int,
        out_of_order_segments: int,
        segment_lifetime_nanoseconds: int,
        retransmissions: int,
        handshake_retransmissions: int,
        budget: BufferBudget,
    ) -> None:
        self.segment_bytes = segment_bytes
        self.send_bytes = send_bytes
        self.receive_bytes = receive_bytes
        self.out_of_order_segments = out_of_order_segments
        self.segment_lifetime_nanoseconds = segment_lifetime_nanoseconds
        self.retransmissions = retransmissions
        self.handshake_retransmissions = handshake_retransmissions
        self.budget = budget
