from kernel_protocol.errors.codes import READ_ONLY, UNSUPPORTED, KernelError

ABSTRACT = "the backend does not implement the operation"
IMMUTABLE = "the mount is read-only"


class Description:
    def __init__(
        self, mode: int, reason: str, generation: int, free_blocks: int, total_blocks: int
    ) -> None:
        self.mode = mode
        self.reason = reason
        self.generation = generation
        self.free_blocks = free_blocks
        self.total_blocks = total_blocks


class Backend:
    def root(self) -> object:
        raise KernelError(UNSUPPORTED, ABSTRACT)

    def lookup(self, directory: object, name: bytes) -> object:
        raise KernelError(UNSUPPORTED, ABSTRACT)

    def kind(self, node: object) -> int:
        raise KernelError(UNSUPPORTED, ABSTRACT)

    def size(self, node: object) -> int:
        raise KernelError(UNSUPPORTED, ABSTRACT)

    def listing(self, directory: object) -> list[tuple[bytes, int, int]]:
        raise KernelError(UNSUPPORTED, ABSTRACT)

    def read(self, file: object, offset: int, count: int) -> bytes:
        raise KernelError(UNSUPPORTED, ABSTRACT)

    def describe(self) -> Description:
        raise KernelError(UNSUPPORTED, ABSTRACT)

    def create(self, directory: object, name: bytes, kind: int) -> object:
        raise KernelError(READ_ONLY, IMMUTABLE)

    def remove(self, directory: object, name: bytes) -> None:
        raise KernelError(READ_ONLY, IMMUTABLE)

    def rename(
        self, source: object, source_name: bytes, target: object, target_name: bytes
    ) -> None:
        raise KernelError(READ_ONLY, IMMUTABLE)

    def write(self, file: object, offset: int, data: bytes) -> int:
        raise KernelError(READ_ONLY, IMMUTABLE)

    def truncate(self, file: object, size: int) -> None:
        raise KernelError(READ_ONLY, IMMUTABLE)

    def sync(self) -> None:
        return

    def retain(self, node: object) -> None:
        return

    def release(self, node: object) -> None:
        return

    def close(self) -> None:
        return
