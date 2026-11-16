from kernel_client import services
from kernel_client.processes import Startup
from kernel_protocol.errors.codes import ACCESS_DENIED
from kernel_protocol.services.block import OPERATION_EVICT as BLOCK_EVICT
from kernel_protocol.services.block import encode_client
from kernel_protocol.services.files import OPERATION_EVICT as FILES_EVICT
from kernel_protocol.services.files import OPERATION_ROOT, encode_size
from kernel_protocol.services.lifecycle import OPERATION_STOP
from suites.support.expectations import error_code

BLOCK = 2
FILESYSTEM = 3


def main() -> bool:
    startup = Startup()
    handles = startup.handles
    refused = all(
        error_code(services.call, endpoint, OPERATION_STOP) == ACCESS_DENIED for endpoint in handles
    )
    return (
        refused
        and error_code(services.call, handles[BLOCK], BLOCK_EVICT, encode_client(startup.identity))
        == ACCESS_DENIED
        and error_code(services.call, handles[FILESYSTEM], OPERATION_ROOT) == ACCESS_DENIED
        and error_code(
            services.call, handles[FILESYSTEM], FILES_EVICT, encode_size(startup.identity)
        )
        == ACCESS_DENIED
    )
