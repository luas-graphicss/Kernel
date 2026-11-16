from kernel_client import capabilities, ipc, services
from kernel_client.services import Reply, Service
from kernel_protocol.errors.codes import (
    ACCESS_DENIED,
    INVALID_ARGUMENT,
    NOT_A_DIRECTORY,
    NOT_FOUND,
    TIMED_OUT,
    UNSUPPORTED,
    KernelError,
    error_name,
)
from kernel_protocol.services.files import (
    KIND_DIRECTORY,
    NAMESPACE_ALL,
    NAMESPACE_DELEGATE,
    OPERATION_CLOSE,
    OPERATION_DROP,
    OPERATION_ENTER,
    OPERATION_EVICT,
    OPERATION_LEAVE,
    OPERATION_LIST,
    OPERATION_MAKE_DIRECTORY,
    OPERATION_OPEN,
    OPERATION_READ,
    OPERATION_REMOVE,
    OPERATION_RENAME,
    OPERATION_ROOT,
    OPERATION_STAT,
    OPERATION_STATUS,
    OPERATION_SUBSPACE,
    OPERATION_SYNC,
    OPERATION_TRUNCATE,
    OPERATION_WRITE,
    decode_count,
    decode_request,
    decode_size,
    decode_tagged_path,
    encode_count,
    encode_mount,
    encode_session,
)
from kernel_services.filesystem.mounts import MountTable
from kernel_services.filesystem.namespace.paths import split
from kernel_services.filesystem.namespace.resolver import Resolver
from kernel_services.filesystem.namespace.table import Namespace, Registry, Session
from kernel_services.filesystem.operations import FileOperations

POLL = 0
MAX_PENDING_ENTRIES = 16
SUPERVISOR_ONLY = "only the supervisor of the service asks for this"


class FileService(Service):
    def __init__(self, mounts: MountTable, instance: int, supervisor: int) -> None:
        self._mounts = mounts
        self._supervisor = supervisor
        self._registry = Registry(instance)
        self._resolver = Resolver(mounts)
        self._entering: dict[int, Namespace] = {}
        self._top = self._registry.add_namespace(
            ipc.create_endpoint(), self._resolver.top(), NAMESPACE_ALL
        )
        files = FileOperations(self._registry, self._resolver)
        self._by_session = {
            OPERATION_LEAVE: self._leave,
            OPERATION_SUBSPACE: self._subspace,
            OPERATION_DROP: self._drop,
            OPERATION_STATUS: self._status,
            OPERATION_OPEN: files.open,
            OPERATION_STAT: files.stat,
            OPERATION_MAKE_DIRECTORY: files.make_directory,
            OPERATION_REMOVE: files.remove,
            OPERATION_RENAME: files.rename,
        }
        self._by_file = {
            OPERATION_CLOSE: files.close,
            OPERATION_READ: files.read,
            OPERATION_WRITE: files.write,
            OPERATION_TRUNCATE: files.truncate,
            OPERATION_SYNC: files.sync,
            OPERATION_LIST: files.list_directory,
        }

    def handle(self, request: ipc.Received) -> Reply:
        operation = request.message.operation
        if operation == OPERATION_ENTER:
            return self._enter(request.sender)
        if operation in (OPERATION_ROOT, OPERATION_EVICT):
            return self._supervise(request)
        instance, subject, body = decode_request(request.message.payload)
        by_session = self._by_session.get(operation)
        if by_session is not None:
            return by_session(self._registry.session_of(instance, subject, request.sender), body)
        by_file = self._by_file.get(operation)
        if by_file is None:
            raise KernelError(UNSUPPORTED, "operation is not part of the file service")
        return by_file(self._registry.file_of(instance, subject, request.sender), body)

    def stop(self) -> None:
        try:
            self._mounts.sync()
        except KernelError as error:
            print(f"filesystem: stop=unsynced error={error_name(error.code)}")
        self._registry.drop_namespace(self._top)
        self._mounts.close()

    def _supervise(self, request: ipc.Received) -> Reply:
        if request.sender != self._supervisor:
            raise KernelError(ACCESS_DENIED, SUPERVISOR_ONLY)
        if request.message.operation == OPERATION_ROOT:
            return Reply(b"", self._top.endpoint)
        client = decode_size(request.message.payload)
        if client in self._entering:
            del self._entering[client]
        for session in self._registry.sessions_of(client):
            self._registry.end_session(session)
        return Reply()

    def _enter(self, sender: int) -> Reply:
        for namespace in list(self._registry.namespaces.values()):
            self._collect(namespace)
        entered = self._entering.get(sender)
        if entered is None or entered.identity not in self._registry.namespaces:
            raise KernelError(ACCESS_DENIED, "no namespace capability was presented")
        del self._entering[sender]
        session = self._registry.add_session(sender, entered)
        return Reply(encode_session(self._registry.instance, session.token, entered.rights))

    def _collect(self, namespace: Namespace) -> None:
        while True:
            try:
                note = ipc.receive(namespace.endpoint, POLL)
            except KernelError as error:
                if error.code != TIMED_OUT:
                    raise
                return
            services.discard_transfer(note)
            if note.reply != 0:
                services.refuse(note, UNSUPPORTED)
            elif note.message.operation == OPERATION_ENTER:
                self._admit(note.sender, namespace)

    def _admit(self, sender: int, namespace: Namespace) -> None:
        if sender in self._entering or len(self._entering) < MAX_PENDING_ENTRIES:
            self._entering[sender] = namespace

    def _leave(self, session: Session, body: bytes) -> Reply:
        self._registry.end_session(session)
        return Reply()

    def _subspace(self, session: Session, body: bytes) -> Reply:
        rights, path = decode_tagged_path(body)
        granted = session.namespace.rights
        if granted & NAMESPACE_DELEGATE == 0:
            raise KernelError(ACCESS_DENIED, "the namespace does not grant delegation")
        if rights == 0 or rights & ~NAMESPACE_ALL:
            raise KernelError(INVALID_ARGUMENT, "subspace asks for no right or for unknown rights")
        if rights & ~granted:
            raise KernelError(ACCESS_DENIED, "a subspace holds no more rights than its origin")
        location = self._resolver.walk(session.namespace.root, split(path))
        if self._resolver.kind(location) != KIND_DIRECTORY:
            raise KernelError(NOT_A_DIRECTORY, "a namespace is rooted at a directory")
        endpoint = ipc.create_endpoint()
        try:
            namespace = self._registry.add_namespace(endpoint, location, rights)
        except KernelError:
            capabilities.close(endpoint)
            raise
        namespace.parent = session.namespace
        namespace.owner = session
        location.retain()
        return Reply(encode_count(namespace.identity), endpoint)

    def _drop(self, session: Session, body: bytes) -> Reply:
        namespace = self._registry.namespaces.get(decode_count(body))
        if namespace is None or namespace.owner is not session:
            raise KernelError(NOT_FOUND, "the session created no such namespace")
        self._registry.drop_namespace(namespace)
        return Reply()

    def _status(self, session: Session, body: bytes) -> Reply:
        return Reply(b"".join([encode_mount(report) for report in self._mounts.reports()]))
