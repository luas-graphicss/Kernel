from kernel_client import capabilities
from kernel_protocol.errors.codes import INVALID_HANDLE, LIMIT_EXCEEDED, KernelError
from kernel_protocol.services.network import ANY_PORT
from kernel_services.network.limits import SOCKETS_PER_CLIENT, SOCKETS_TOTAL
from kernel_services.network.tcp.connection import Connection
from kernel_services.network.tcp.listener import Listener
from kernel_services.network.udp.ports import UdpPort

MAX_ACCESSES = 16
MAX_SESSIONS = 16
STALE = "the handle belongs to another instance of the service or to another process"


class Access:
    def __init__(self, identity: int, endpoint: int, rights: int) -> None:
        self.identity = identity
        self.endpoint = endpoint
        self.rights = rights
        self.parent: Access | None = None
        self.owner: Session | None = None


class Session:
    def __init__(self, token: int, sender: int, access: Access) -> None:
        self.token = token
        self.sender = sender
        self.access = access
        self.echoes = 0


class Socket:
    def __init__(self, handle: int, session: Session, kind: int) -> None:
        self.handle = handle
        self.session = session
        self.kind = kind
        self.bound_port = ANY_PORT
        self.connection: Connection | None = None
        self.listener: Listener | None = None
        self.port: UdpPort | None = None


class Registry:
    def __init__(self, instance: int) -> None:
        self.instance = instance
        self.accesses: dict[int, Access] = {}
        self.sessions: dict[int, Session] = {}
        self.sockets: dict[int, Socket] = {}
        self._serial = 0

    def add_access(self, endpoint: int, rights: int) -> Access:
        if len(self.accesses) == MAX_ACCESSES:
            raise KernelError(LIMIT_EXCEEDED, "the service has no room for another access")
        access = Access(self._next(), endpoint, rights)
        self.accesses[access.identity] = access
        return access

    def add_session(self, sender: int, access: Access) -> Session:
        if len(self.sessions) == MAX_SESSIONS:
            raise KernelError(LIMIT_EXCEEDED, "the service has no room for another session")
        session = Session(self._next(), sender, access)
        self.sessions[session.token] = session
        return session

    def add_socket(self, session: Session, kind: int) -> Socket:
        if len(self.sockets) == SOCKETS_TOTAL:
            raise KernelError(LIMIT_EXCEEDED, "the service has no room for another socket")
        if self.sockets_of_client(session.sender) == SOCKETS_PER_CLIENT:
            raise KernelError(LIMIT_EXCEEDED, "the process holds its limit of sockets")
        socket = Socket(self._next(), session, kind)
        self.sockets[socket.handle] = socket
        return socket

    def sockets_of_client(self, sender: int) -> int:
        held = 0
        for socket in self.sockets.values():
            if socket.session.sender == sender:
                held += 1
        return held

    def session_of(self, instance: int, token: int, sender: int) -> Session:
        session = self.sessions.get(token)
        if instance != self.instance or session is None or session.sender != sender:
            raise KernelError(INVALID_HANDLE, STALE)
        return session

    def socket_of(self, instance: int, handle: int, sender: int) -> Socket:
        socket = self.sockets.get(handle)
        if instance != self.instance or socket is None or socket.session.sender != sender:
            raise KernelError(INVALID_HANDLE, STALE)
        return socket

    def sockets_of(self, session: Session) -> list[Socket]:
        return [held for held in self.sockets.values() if held.session is session]

    def sessions_of_client(self, sender: int) -> list[Session]:
        return [held for held in self.sessions.values() if held.sender == sender]

    def sessions_through(self, access: Access) -> list[Session]:
        return [held for held in self.sessions.values() if held.access is access]

    def derived_from(self, access: Access) -> list[Access]:
        return [held for held in self.accesses.values() if held.parent is access]

    def created_by(self, session: Session) -> list[Access]:
        return [held for held in self.accesses.values() if held.owner is session]

    def remove_socket(self, socket: Socket) -> None:
        self.sockets.pop(socket.handle, None)

    def remove_session(self, session: Session) -> None:
        self.sessions.pop(session.token, None)

    def remove_access(self, access: Access) -> None:
        if self.accesses.pop(access.identity, None) is not None:
            capabilities.close(access.endpoint)

    def _next(self) -> int:
        self._serial += 1
        return self._serial
