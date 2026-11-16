import _process
from kernel_client.calls import FAILURE, check, scalar
from kernel_protocol.errors.codes import KernelError
from kernel_protocol.syscalls.numbers import DEADLINE_NEVER, DEVICE_CLAIM, DEVICE_RESET


class Device:
    def __init__(self, slot: int, kind: int, model: int, state: int) -> None:
        self.slot = slot
        self.kind = kind
        self.model = model
        self.state = state


class Session:
    def __init__(self, features: int, generation: int, queue_size: int) -> None:
        self.features = features
        self.generation = generation
        self.queue_size = queue_size


def refusal(status: int) -> KernelError:
    return KernelError(-status, FAILURE)


def list_devices(system: int) -> tuple[Device, ...]:
    listed = _process.device_list(system)
    if isinstance(listed, int):
        raise refusal(listed)
    return tuple(Device(slot, kind, model, state) for slot, kind, model, state in listed)


def claim(system: int, slot: int) -> int:
    return scalar(DEVICE_CLAIM, system, slot)


def reset(device: int) -> None:
    scalar(DEVICE_RESET, device)


def open_session(device: int, features: int) -> Session:
    opened = _process.device_open(device, features)
    if isinstance(opened, int):
        raise refusal(opened)
    return Session(opened[0], opened[1], opened[2])


def read_config(device: int, offset: int, length: int) -> bytes:
    config = _process.device_config(device, offset, length)
    if isinstance(config, int):
        raise refusal(config)
    return config


def submit(device: int, segments: tuple[tuple[int, int, int, bool], ...]) -> int:
    return check(_process.device_submit(device, segments))


def wait(device: int, deadline: int = DEADLINE_NEVER) -> tuple[int, int]:
    completion = _process.device_wait(device, deadline)
    if isinstance(completion, int):
        raise refusal(completion)
    return completion


def serial_write(device: int, data: bytes) -> int:
    return check(_process.serial_write(device, data))


def serial_read(device: int, capacity: int, deadline: int = DEADLINE_NEVER) -> bytes:
    received = _process.serial_read(device, capacity, deadline)
    if isinstance(received, int):
        raise refusal(received)
    return received
