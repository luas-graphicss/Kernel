from kernel_client import capabilities, ipc, processes, system
from kernel_protocol.errors.codes import LIMIT_EXCEEDED, TIMED_OUT
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.processes.status import COUNTER_MESSAGES
from runtime_selftest.checks import Checks
from suites.scheduling.protocol import OPERATION_REQUEST, plain
from suites.support import children
from suites.support.expectations import KILLED, error_code
from suites.support.reporting import Context

LINK = "suites.scheduling.link"
ACCEPTED_LINKS = 7
NO_TRANSFER = 0
WAIT_NANOSECONDS = 20000000


def call_error(endpoint: int) -> int:
    deadline = processes.clock() + WAIT_NANOSECONDS
    return error_code(ipc.call, endpoint, plain(OPERATION_REQUEST), NO_TRANSFER, deadline)


class Chain:
    def __init__(self, context: Context, reports: int) -> None:
        self._context = context
        self._reports = reports
        self._baseline = system.counters(context.system)[COUNTER_MESSAGES]
        self.links: list[int] = []
        self.head = self._start(((reports, RIGHT_SEND),))

    def extend(self) -> bool:
        blocked_calls = len(self.links)
        self.head = self._start(((self._reports, RIGHT_SEND), (self.head, RIGHT_SEND)))
        return self._context.wait_for(lambda: self._queued() == blocked_calls)

    def stop(self) -> bool:
        newest_first = range(len(self.links) - 1, -1, -1)
        return all(children.stop(self.links[position]) == KILLED for position in newest_first)

    def _start(self, grants: tuple[tuple[int, int], ...]) -> int:
        self.links.append(children.start(self._context.system, LINK, grants=grants))
        return ipc.receive(self._reports).transferred

    def _queued(self) -> int:
        return system.counters(self._context.system)[COUNTER_MESSAGES] - self._baseline


def run(context: Context, checks: Checks) -> None:
    reports = ipc.create_endpoint()
    chain = Chain(context, reports)
    endpoints = [chain.head]
    for _ in range(ACCEPTED_LINKS):
        checks.require(chain.extend(), "a link blocks in a call to the link before it")
        endpoints.append(chain.head)
    checks.require(
        call_error(chain.head) == TIMED_OUT, "a call into a chain within the limit is accepted"
    )
    checks.require(chain.extend(), "one more link still blocks")
    endpoints.append(chain.head)
    checks.require(
        call_error(chain.head) == LIMIT_EXCEEDED, "a call into a longer chain is refused"
    )
    checks.require(chain.stop(), "every link is stopped")
    for endpoint in endpoints:
        capabilities.close(endpoint)
    capabilities.close(reports)
