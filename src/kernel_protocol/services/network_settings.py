from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_protocol.wire.message import pack_unsigned, unpack_unsigned

SETTINGS_BYTES = 11


class InterfaceSettings:
    def __init__(self, address: int, prefix: int, gateway: int, mtu: int) -> None:
        self.address = address
        self.prefix = prefix
        self.gateway = gateway
        self.mtu = mtu


def encode_settings(settings: InterfaceSettings) -> bytes:
    return (
        pack_unsigned(settings.address, 4)
        + pack_unsigned(settings.gateway, 4)
        + pack_unsigned(settings.mtu, 2)
        + pack_unsigned(settings.prefix, 1)
    )


def decode_settings(role: bytes) -> InterfaceSettings:
    if len(role) != SETTINGS_BYTES:
        raise KernelError(INVALID_ARGUMENT, "network service started without its interface")
    return InterfaceSettings(
        address=unpack_unsigned(role, 0, 4),
        prefix=role[10],
        gateway=unpack_unsigned(role, 4, 8),
        mtu=unpack_unsigned(role, 8, 10),
    )
