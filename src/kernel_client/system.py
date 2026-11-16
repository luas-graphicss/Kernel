import _process
from kernel_client.calls import check


def counters(system: int) -> tuple[int, ...]:
    result = _process.counters(system)
    if isinstance(result, int):
        check(result)
        return ()
    return result
