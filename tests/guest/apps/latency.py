from kernel_client import ipc, processes
from kernel_protocol.errors.codes import TIMED_OUT, KernelError

SAMPLES = 400
INTERVAL_NANOSECONDS = 5000000
NANOSECONDS_PER_MICROSECOND = 1000
PERCENT = 100
MEDIAN = 50
TAIL = 99


def percentile(ordered: list[int], percent: int) -> int:
    position = (len(ordered) * percent + PERCENT - 1) // PERCENT
    if position < 1:
        position = 1
    return ordered[position - 1]


def sleep_until(silent: int, deadline: int) -> None:
    try:
        ipc.receive(silent, deadline)
    except KernelError as error:
        if error.code != TIMED_OUT:
            raise


def main() -> bool:
    silent = ipc.create_endpoint()
    delays = []
    for _ in range(SAMPLES):
        deadline = processes.clock() + INTERVAL_NANOSECONDS
        sleep_until(silent, deadline)
        delays.append(processes.clock() - deadline)
    ordered = sorted(delays)
    print(
        f"measure: name=ready-task-response samples={len(ordered)} "
        f"p50-us={percentile(ordered, MEDIAN) // NANOSECONDS_PER_MICROSECOND} "
        f"p99-us={percentile(ordered, TAIL) // NANOSECONDS_PER_MICROSECOND} "
        f"max-us={ordered[-1] // NANOSECONDS_PER_MICROSECOND}"
    )
    return True
