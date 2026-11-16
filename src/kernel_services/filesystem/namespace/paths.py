from kernel_protocol.errors.codes import ACCESS_DENIED, LIMIT_EXCEEDED, KernelError
from kernel_protocol.services.files import MAX_PATH_BYTES, MAX_PATH_COMPONENTS
from kernel_services.filesystem.format.names import CURRENT, PARENT, SEPARATOR, check_name


def split(path: bytes) -> list[bytes]:
    if len(path) > MAX_PATH_BYTES:
        raise KernelError(LIMIT_EXCEEDED, "path is longer than the service accepts")
    components: list[bytes] = []
    for part in path.split(SEPARATOR):
        if part == b"" or part == CURRENT:
            continue
        if part == PARENT:
            if not components:
                raise KernelError(ACCESS_DENIED, "path climbs above the root of its namespace")
            components.pop()
            continue
        check_name(part)
        if len(components) == MAX_PATH_COMPONENTS:
            raise KernelError(LIMIT_EXCEEDED, "path has more components than the service accepts")
        components.append(part)
    return components
