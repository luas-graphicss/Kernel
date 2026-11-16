from kernel_client import capabilities
from kernel_protocol.errors.codes import INVALID_HANDLE, LIMIT_EXCEEDED, KernelError
from kernel_services.filesystem.namespace.resolver import Location

MAX_NAMESPACES = 16
MAX_SESSIONS = 16
MAX_FILES = 64
STALE = "the handle belongs to another instance of the service or to another process"


class Namespace:
    def __init__(self, identity: int, endpoint: int, root: Location, rights: int) -> None:
        self.identity = identity
        self.endpoint = endpoint
        self.root = root
        self.rights = rights
        self.parent: Namespace | None = None
        self.owner: Session | None = None


class Session:
    def __init__(self, token: int, sender: int, namespace: Namespace) -> None:
        self.token = token
        self.sender = sender
        self.namespace = namespace


class OpenFile:
    def __init__(self, handle: int, session: Session, location: Location, flags: int) -> None:
        self.handle = handle
        self.session = session
        self.location = location
        self.flags = flags


class Registry:
    def __init__(self, instance: int) -> None:
        self.instance = instance
        self.namespaces: dict[int, Namespace] = {}
        self.sessions: dict[int, Session] = {}
        self.files: dict[int, OpenFile] = {}
        self._serial = 0

    def add_namespace(self, endpoint: int, root: Location, rights: int) -> Namespace:
        if len(self.namespaces) == MAX_NAMESPACES:
            raise KernelError(LIMIT_EXCEEDED, "the service has no room for another namespace")
        namespace = Namespace(self._next(), endpoint, root, rights)
        self.namespaces[namespace.identity] = namespace
        return namespace

    def add_session(self, sender: int, namespace: Namespace) -> Session:
        if len(self.sessions) == MAX_SESSIONS:
            raise KernelError(LIMIT_EXCEEDED, "the service has no room for another session")
        session = Session(self._next(), sender, namespace)
        self.sessions[session.token] = session
        return session

    def add_file(self, session: Session, location: Location, flags: int) -> OpenFile:
        if len(self.files) == MAX_FILES:
            raise KernelError(LIMIT_EXCEEDED, "the service has no room for another open file")
        opened = OpenFile(self._next(), session, location, flags)
        location.retain()
        self.files[opened.handle] = opened
        return opened

    def session_of(self, instance: int, token: int, sender: int) -> Session:
        session = self.sessions.get(token)
        if instance != self.instance or session is None or session.sender != sender:
            raise KernelError(INVALID_HANDLE, STALE)
        return session

    def file_of(self, instance: int, handle: int, sender: int) -> OpenFile:
        opened = self.files.get(handle)
        if instance != self.instance or opened is None or opened.session.sender != sender:
            raise KernelError(INVALID_HANDLE, STALE)
        return opened

    def close_file(self, opened: OpenFile) -> None:
        del self.files[opened.handle]
        opened.location.release()

    def end_session(self, session: Session) -> None:
        for opened in [held for held in self.files.values() if held.session is session]:
            self.close_file(opened)
        for owned in [held for held in self.namespaces.values() if held.owner is session]:
            self.drop_namespace(owned)
        self.sessions.pop(session.token, None)

    def drop_namespace(self, namespace: Namespace) -> None:
        if namespace.identity not in self.namespaces:
            return
        del self.namespaces[namespace.identity]
        for child in [held for held in self.namespaces.values() if held.parent is namespace]:
            self.drop_namespace(child)
        for session in [held for held in self.sessions.values() if held.namespace is namespace]:
            self.end_session(session)
        namespace.root.release()
        capabilities.close(namespace.endpoint)

    def sessions_of(self, sender: int) -> list[Session]:
        return [held for held in self.sessions.values() if held.sender == sender]

    def _next(self) -> int:
        self._serial += 1
        return self._serial
