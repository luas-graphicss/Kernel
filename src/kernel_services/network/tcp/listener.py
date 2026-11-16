from kernel_services.network.tcp.connection import CLOSED, ESTABLISHED, SYN_RECEIVED, Connection


class Listener:
    def __init__(self, port: int, backlog: int) -> None:
        self.port = port
        self.backlog = backlog
        self.pending: list[Connection] = []
        self.ready: list[Connection] = []

    def has_room(self) -> bool:
        return len(self.pending) + len(self.ready) < self.backlog

    def settle(self, connection: Connection) -> None:
        if connection in self.pending and connection.state != SYN_RECEIVED:
            self.pending.remove(connection)
            if connection.state == ESTABLISHED:
                self.ready.append(connection)
        elif (
            connection in self.ready
            and connection.state == CLOSED
            and connection.is_at_end_of_input()
        ):
            self.ready.remove(connection)

    def accept(self) -> Connection | None:
        if not self.ready:
            return None
        return self.ready.pop(0)
