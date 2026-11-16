from kernel_client import capabilities, ipc, processes
from kernel_protocol.processes.status import WAIT_REASON_EXIT
from kernel_protocol.wire.message import Message
from kernel_services.echo.protocol import OPERATION_ECHO, OPERATION_REGISTER, OPERATION_STOP
from kernel_services.init.manifest import KNOWN_GRANTS, REGISTRATION, SERVICES, Service

NO_FLAGS = 0
PROBE_PAYLOAD = b"kernel"
PROBE_CORRELATION = 0x4B524E4C


class Running:
    def __init__(self, service: Service, process: int, endpoint: int) -> None:
        self.service = service
        self.process = process
        self.endpoint = endpoint


def start(system: int, registration: int, service: Service) -> Running:
    available = {REGISTRATION: registration}
    grants = tuple((available[name], KNOWN_GRANTS[name]) for name in service.grants)
    process = processes.spawn(
        system,
        service.program,
        priority=service.priority,
        heap_bytes=service.heap_bytes,
        grants=grants,
    )
    announced = ipc.receive(registration)
    if announced.message.operation != OPERATION_REGISTER or announced.transferred == 0:
        return Running(service, process, 0)
    print(f"init: service={service.program} ready")
    return Running(service, process, announced.transferred)


def probe(running: Running) -> bool:
    if running.endpoint == 0:
        return False
    request = Message(OPERATION_ECHO, NO_FLAGS, PROBE_CORRELATION, PROBE_PAYLOAD)
    response, _received = ipc.call(running.endpoint, request)
    return response.payload == PROBE_PAYLOAD and response.correlation == PROBE_CORRELATION


def stop(running: Running) -> bool:
    if running.endpoint != 0:
        ipc.call(running.endpoint, Message(OPERATION_STOP, NO_FLAGS, PROBE_CORRELATION, b""))
        capabilities.close(running.endpoint)
    reason, value = processes.wait(running.process)
    capabilities.close(running.process)
    print(f"init: service={running.service.program} exit={value}")
    return reason == WAIT_REASON_EXIT and value == 0


def run(system: int, registration: int) -> bool:
    succeeded = True
    for service in SERVICES:
        running = start(system, registration, service)
        answered = probe(running)
        verdict = "ok" if answered else "failed"
        print(f"init: service={service.program} echo={verdict}")
        succeeded = stop(running) and answered and succeeded
    return succeeded
