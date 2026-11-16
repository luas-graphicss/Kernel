from kernel_apps.shell.session import Session
from kernel_apps.shell.words import parse_number
from kernel_protocol.errors.codes import INVALID_ARGUMENT, TIMED_OUT, KernelError, error_name
from kernel_services.network.counters import NAMES as COUNTER_NAMES
from kernel_services.network.ipv4.address import format_address, parse_address

HEX_DIGITS = "0123456789abcdef"
OCTET_SEPARATOR = ":"
ECHO_TIMEOUT_NANOSECONDS = 2000000000
ECHO_BYTES = 32
DEFAULT_ECHOES = 3
MAX_ECHOES = 16
NANOSECONDS_PER_MICROSECOND = 1000
COUNTERS = "counters"
NEIGHBORS = "neighbors"
USAGE = "the command was not given its arguments"


def format_hardware(hardware: bytes) -> str:
    return OCTET_SEPARATOR.join(
        [HEX_DIGITS[octet >> 4] + HEX_DIGITS[octet & 0x0F] for octet in hardware]
    )


def describe(session: Session, arguments: list[str]) -> None:
    network = session.network()
    if arguments and arguments[0] == NEIGHBORS:
        neighbors = network.neighbors()
        for address, hardware in neighbors:
            session.write(
                f"net: neighbor={format_address(address)} hardware={format_hardware(hardware)}"
            )
        session.write(f"net: neighbors={len(neighbors)}")
        return
    status = network.status()
    if arguments and arguments[0] == COUNTERS:
        for index in range(len(status.counters)):
            if status.counters[index] != 0 and index < len(COUNTER_NAMES):
                session.write(f"net: counter={COUNTER_NAMES[index]} value={status.counters[index]}")
        return
    if arguments:
        raise KernelError(INVALID_ARGUMENT, USAGE)
    session.write(
        f"net: address={format_address(status.address)}/{status.prefix} "
        f"gateway={format_address(status.gateway)} mtu={status.mtu} "
        f"link={'up' if status.is_linked else 'down'} "
        f"hardware={format_hardware(status.hardware)}"
    )
    session.write(
        f"net: sockets={status.sockets} connections={status.connections} "
        f"buffered-bytes={status.buffered_bytes} device-resets={status.resets}"
    )


def ping(session: Session, arguments: list[str]) -> None:
    if not arguments:
        raise KernelError(INVALID_ARGUMENT, USAGE)
    address = parse_address(arguments[0])
    echoes = DEFAULT_ECHOES
    if len(arguments) > 1:
        echoes = parse_number(arguments[1], MAX_ECHOES)
    network = session.network()
    received = 0
    failure = TIMED_OUT
    for _ in range(echoes):
        try:
            elapsed = network.echo(address, ECHO_TIMEOUT_NANOSECONDS, ECHO_BYTES)
        except KernelError as error:
            failure = error.code
            session.write(f"ping: to={arguments[0]} error={error_name(error.code)}")
            session.failed(error)
            continue
        received += 1
        session.write(
            f"ping: from={arguments[0]} bytes={ECHO_BYTES} "
            f"time-us={elapsed // NANOSECONDS_PER_MICROSECOND}"
        )
    session.write(f"ping: sent={echoes} received={received}")
    if received == 0:
        raise KernelError(failure, "no echo reply arrived")
