from kernel_client import capabilities, ipc, processes
from kernel_protocol.identity.rights import RIGHT_SEND
from suites.scheduling.protocol import OPERATION_WINDOW, plain
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY
from suites.support.raw import word
from suites.support.reporting import Context

TICKER = "suites.scheduling.ticker"
LEAD_NANOSECONDS = 20000000


def open_window(reports: int, tickers: int, window_nanoseconds: int) -> None:
    gates = [ipc.receive(reports).transferred for _ in range(tickers)]
    start = processes.clock() + LEAD_NANOSECONDS
    window = word(start) + word(start + window_nanoseconds)
    for gate in gates:
        ipc.send(gate, plain(OPERATION_WINDOW, 0, window))
        capabilities.close(gate)


def start_ticker(context: Context, reports: int, position: int, priority: int) -> int:
    argument = bytes(str(position), "ascii")
    return children.start(
        context.system, TICKER, argument, priority, grants=((reports, RIGHT_SEND),)
    )


def count_turns(
    context: Context, reports: int, priorities: tuple[int, ...], window_nanoseconds: int
) -> tuple[int, ...]:
    tickers = [
        start_ticker(context, reports, position, priorities[position])
        for position in range(len(priorities))
    ]
    open_window(reports, len(tickers), window_nanoseconds)
    turns = [0] * len(tickers)
    for _ in tickers:
        report = ipc.receive(reports).message
        turns[int(str(report.payload, "ascii"))] = report.correlation
    if any(children.finish(ticker) != EXITED_CLEANLY for ticker in tickers):
        return ()
    return tuple(turns)
