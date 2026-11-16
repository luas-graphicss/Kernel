import sys

from kernel_client.blocks import BlockDevice
from kernel_protocol.errors.codes import KernelError, error_name
from kernel_services.filesystem.backends.base import Backend
from kernel_services.filesystem.backends.boot import BootBackend
from kernel_services.filesystem.backends.persistent import VolumeBackend
from kernel_services.filesystem.backends.stores import DeviceStore, MemoryStore
from kernel_services.filesystem.creation import create_volume
from kernel_services.filesystem.format.layout import BLOCK_BYTES
from kernel_services.filesystem.mounts import MountTable

BOOT = b"boot"
TEMPORARY = b"tmp"
ROLE_SEPARATOR = b","
TEMPORARY_BLOCKS = 64
TEMPORARY_VOLUME = 0x706D74
BLOCK_TIMEOUT_NANOSECONDS = 20000000000


def runtime_tag() -> bytes:
    version = sys.implementation.version
    return bytes(f"{sys.implementation.name}-{version[0]}.{version[1]}", "utf-8")


def temporary_backend() -> Backend:
    store = MemoryStore(TEMPORARY_BLOCKS)
    create_volume(store, TEMPORARY_VOLUME)
    return VolumeBackend(store)


def device_backend(name: bytes, endpoint: int) -> Backend:
    store = DeviceStore(BlockDevice(endpoint, BLOCK_BYTES, BLOCK_TIMEOUT_NANOSECONDS))
    try:
        if name == BOOT:
            return BootBackend(store, runtime_tag())
        return VolumeBackend(store)
    except KernelError:
        store.close()
        raise


def mount_device(mounts: MountTable, name: bytes, endpoint: int) -> None:
    label = str(name, "utf-8")
    try:
        mounts.add(name, device_backend(name, endpoint))
    except KernelError as error:
        mounts.fail(name, error.code)
        print(f"filesystem: mount={label} unavailable error={error_name(error.code)}")


def build_mounts(role: bytes, endpoints: tuple[int, ...]) -> MountTable:
    mounts = MountTable()
    mounts.add(TEMPORARY, temporary_backend())
    names = [name for name in role.split(ROLE_SEPARATOR) if name]
    for index in range(len(names)):
        mount_device(mounts, names[index], endpoints[index])
    return mounts
