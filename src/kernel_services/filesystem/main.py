from kernel_client import ipc, services
from kernel_client.processes import Startup
from kernel_protocol.services.lifecycle import decode_supervisor
from kernel_services.filesystem.service import FileService
from kernel_services.filesystem.startup import build_mounts

REGISTRATION = 0
FIRST_BLOCK_SERVICE = 1


def main() -> bool:
    startup = Startup()
    supervisor, role = decode_supervisor(startup.argument)
    mounts = build_mounts(role, startup.handles[FIRST_BLOCK_SERVICE:])
    endpoint = ipc.create_endpoint()
    service = FileService(mounts, startup.identity, supervisor)
    services.register(startup.handles[REGISTRATION], endpoint)
    return services.serve(endpoint, service, supervisor)
