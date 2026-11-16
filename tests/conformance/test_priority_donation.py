import pytest

from kernel_core.scheduling.selection import (
    AGING_THRESHOLD,
    DONATION_DEPTH,
    HIGHEST_PRIORITY,
    LOWEST_PRIORITY,
    NO_PROCESS,
    Scheduler,
)
from kernel_protocol.errors.codes import BAD_STATE, INVALID_HANDLE, KernelError

URGENT = HIGHEST_PRIORITY
NORMAL = 1
BACKGROUND = LOWEST_PRIORITY


def admitted(priorities: dict[int, int]) -> Scheduler:
    scheduler = Scheduler()
    for handle, priority in priorities.items():
        scheduler.admit(handle, priority)
    return scheduler


def wait_on(scheduler: Scheduler, waiter: int, target: int) -> None:
    scheduler.make_ready(waiter)
    assert scheduler.select() == waiter
    scheduler.block(waiter)
    scheduler.donate(waiter, target)


def error_code(operation, *arguments: int) -> int:
    with pytest.raises(KernelError) as raised:
        operation(*arguments)
    return raised.value.code


def test_blocked_caller_lends_its_priority_to_a_ready_server() -> None:
    scheduler = admitted({11: URGENT, 12: BACKGROUND, 13: NORMAL})
    scheduler.make_ready(12)
    scheduler.make_ready(13)

    wait_on(scheduler, 11, 12)

    server = scheduler.process(12)
    assert (server.base_priority, server.entitled_priority) == (BACKGROUND, URGENT)
    assert scheduler.queued(URGENT) == [12]
    assert scheduler.select() == 12


def test_donation_ends_when_the_caller_stops_waiting() -> None:
    scheduler = admitted({21: URGENT, 22: BACKGROUND, 23: NORMAL})
    scheduler.make_ready(22)
    scheduler.make_ready(23)
    wait_on(scheduler, 21, 22)
    assert scheduler.select() == 22

    scheduler.make_ready(21)

    server = scheduler.process(22)
    assert (server.entitled_priority, server.effective_priority) == (BACKGROUND, BACKGROUND)
    assert server.donors == []
    assert scheduler.select() == 21
    scheduler.block(21)
    assert scheduler.select() == 23


def test_donation_follows_a_chain_of_waiters() -> None:
    scheduler = admitted({31: URGENT, 32: NORMAL, 33: BACKGROUND})
    scheduler.make_ready(33)
    wait_on(scheduler, 32, 33)

    wait_on(scheduler, 31, 32)

    assert scheduler.process(32).entitled_priority == URGENT
    assert scheduler.process(33).effective_priority == URGENT
    assert scheduler.select() == 33


def test_donation_stops_after_the_depth_limit() -> None:
    chain = list(range(41, 43 + DONATION_DEPTH))
    scheduler = admitted({chain[0]: URGENT} | dict.fromkeys(chain[1:], BACKGROUND))
    for position in range(1, len(chain) - 1):
        wait_on(scheduler, chain[position], chain[position + 1])

    wait_on(scheduler, chain[0], chain[1])

    reached = chain[1 : DONATION_DEPTH + 1]
    assert [scheduler.process(handle).entitled_priority for handle in reached] == (
        [URGENT] * DONATION_DEPTH
    )
    assert scheduler.process(chain[DONATION_DEPTH + 1]).entitled_priority == BACKGROUND


def test_waiters_in_a_cycle_keep_bounded_priorities() -> None:
    scheduler = admitted({51: URGENT, 52: BACKGROUND})
    wait_on(scheduler, 52, 51)

    wait_on(scheduler, 51, 52)

    assert scheduler.process(51).entitled_priority == URGENT
    assert scheduler.process(52).entitled_priority == URGENT
    scheduler.exit(51)
    assert scheduler.process(52).entitled_priority == BACKGROUND
    assert scheduler.process(52).waiting_on == NO_PROCESS


def test_best_of_several_donors_counts_and_each_takes_its_share_back() -> None:
    scheduler = admitted({61: URGENT, 62: NORMAL, 63: BACKGROUND})
    wait_on(scheduler, 62, 63)
    wait_on(scheduler, 61, 63)
    assert scheduler.process(63).entitled_priority == URGENT

    scheduler.make_ready(61)
    assert scheduler.process(63).entitled_priority == NORMAL

    scheduler.exit(62)
    assert scheduler.process(63).entitled_priority == BACKGROUND
    assert scheduler.process(63).donors == []


def test_withdrawn_donation_does_not_restart_the_aging_of_its_target() -> None:
    caller, first, second, server = 71, 72, 73, 74
    scheduler = admitted({caller: URGENT, first: URGENT, second: URGENT, server: BACKGROUND})
    for handle in (caller, first, second, server):
        scheduler.make_ready(handle)
    selections = []

    for _ in range(LOWEST_PRIORITY * AGING_THRESHOLD):
        selections.append(scheduler.select())
        if selections[-1] == caller:
            scheduler.block(caller)
            scheduler.donate(caller, server)
            scheduler.make_ready(caller)

    assert server in selections


def test_boost_left_by_a_withdrawn_donation_is_spent_by_one_selection() -> None:
    scheduler = admitted({81: URGENT, 82: BACKGROUND})
    scheduler.make_ready(82)
    wait_on(scheduler, 81, 82)

    scheduler.make_ready(81)

    assert scheduler.queued(URGENT) == [82, 81]
    assert scheduler.process(82).entitled_priority == BACKGROUND
    assert scheduler.select() == 82
    assert scheduler.select() == 81
    assert scheduler.queued(BACKGROUND) == [82]


def test_donor_that_dies_takes_its_donation_back() -> None:
    scheduler = admitted({91: URGENT, 92: BACKGROUND})
    wait_on(scheduler, 91, 92)

    scheduler.exit(91)

    assert scheduler.process(92).entitled_priority == BACKGROUND
    assert scheduler.process(92).donors == []


def test_target_that_dies_releases_its_donors() -> None:
    scheduler = admitted({101: URGENT, 102: BACKGROUND, 103: BACKGROUND})
    wait_on(scheduler, 101, 102)

    scheduler.exit(102)

    assert scheduler.process(101).waiting_on == NO_PROCESS
    scheduler.donate(101, 103)
    assert scheduler.process(103).entitled_priority == URGENT


def test_invalid_donations_report_the_documented_codes() -> None:
    scheduler = admitted({111: URGENT, 112: NORMAL, 113: BACKGROUND, 114: BACKGROUND})
    scheduler.exit(114)

    assert error_code(scheduler.donate, 111, 113) == BAD_STATE
    wait_on(scheduler, 111, 113)
    assert error_code(scheduler.donate, 111, 112) == BAD_STATE
    scheduler.make_ready(112)
    assert scheduler.select() == 112
    scheduler.block(112)
    assert error_code(scheduler.donate, 112, 112) == INVALID_HANDLE
    assert error_code(scheduler.donate, 112, 999) == INVALID_HANDLE
    assert error_code(scheduler.donate, 112, 114) == INVALID_HANDLE
    assert error_code(scheduler.donate, 999, 113) == INVALID_HANDLE
    assert scheduler.process(112).waiting_on == NO_PROCESS
