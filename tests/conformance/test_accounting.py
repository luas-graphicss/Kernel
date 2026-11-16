import pytest

from kernel_core.processes.accounting import (
    CAPABILITIES,
    IPC_PENDING_BYTES,
    MEMORY_BYTES,
    ResourceLedger,
)
from kernel_protocol.errors.codes import (
    BAD_STATE,
    INVALID_ARGUMENT,
    INVALID_HANDLE,
    LIMIT_EXCEEDED,
    KernelError,
)

GLOBAL_LIMITS = (1000, 10, 100)
OWNER_LIMITS = (600, 8, 60)


def error_code(operation, *arguments: object) -> int:
    with pytest.raises(KernelError) as raised:
        operation(*arguments)
    return raised.value.code


def ledger_with_owners(*owners: int) -> ResourceLedger:
    ledger = ResourceLedger(GLOBAL_LIMITS, max_accounts=2)
    for owner in owners:
        ledger.open_account(owner, OWNER_LIMITS)
    return ledger


def test_charge_updates_the_owner_and_the_global_usage() -> None:
    ledger = ledger_with_owners(1)

    ledger.charge(1, (300, 2, 10))

    assert ledger.account(1).usage == [300, 2, 10]
    assert ledger.global_usage == [300, 2, 10]


def test_charge_over_one_quota_changes_nothing() -> None:
    ledger = ledger_with_owners(1)
    ledger.charge(1, (300, 2, 10))

    assert error_code(ledger.charge, 1, (100, 7, 5)) == LIMIT_EXCEEDED

    assert ledger.account(1).usage == [300, 2, 10]
    assert ledger.global_usage == [300, 2, 10]


def test_global_budget_applies_across_owners() -> None:
    ledger = ledger_with_owners(1, 2)
    ledger.charge(1, (600, 0, 0))

    assert error_code(ledger.charge, 2, (500, 0, 0)) == LIMIT_EXCEEDED

    ledger.charge(2, (400, 0, 0))
    assert ledger.global_usage[MEMORY_BYTES] == 1000


def test_refund_cannot_exceed_what_the_owner_holds() -> None:
    ledger = ledger_with_owners(1)
    ledger.charge(1, (300, 2, 10))

    assert error_code(ledger.refund, 1, (0, 3, 0)) == INVALID_ARGUMENT

    ledger.refund(1, (100, 2, 10))
    assert ledger.account(1).usage[CAPABILITIES] == 0
    assert ledger.global_usage[IPC_PENDING_BYTES] == 0


def test_closing_an_account_returns_everything_to_the_budget() -> None:
    ledger = ledger_with_owners(1, 2)
    ledger.charge(1, (300, 2, 10))
    ledger.charge(2, (100, 1, 0))

    ledger.close_account(1)

    assert ledger.owners() == [2]
    assert ledger.global_usage == [100, 1, 0]


def test_invalid_requests_report_the_documented_codes() -> None:
    ledger = ledger_with_owners(1, 2)

    assert error_code(ledger.open_account, 1, OWNER_LIMITS) == BAD_STATE
    assert error_code(ledger.open_account, 3, OWNER_LIMITS) == LIMIT_EXCEEDED
    assert error_code(ledger.charge, 9, (1, 0, 0)) == INVALID_HANDLE
    assert error_code(ledger.charge, 1, (1, 0)) == INVALID_ARGUMENT
    assert error_code(ledger.charge, 1, (-1, 0, 0)) == INVALID_ARGUMENT
