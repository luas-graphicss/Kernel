from kernel_protocol.errors.codes import (
    BAD_STATE,
    INVALID_ARGUMENT,
    INVALID_HANDLE,
    LIMIT_EXCEEDED,
    KernelError,
)

MEMORY_BYTES = 0
CAPABILITIES = 1
IPC_PENDING_BYTES = 2
RESOURCE_KINDS = 3


def check_amounts(amounts: tuple[int, ...]) -> None:
    if len(amounts) != RESOURCE_KINDS:
        raise KernelError(INVALID_ARGUMENT, "one amount per resource kind is required")
    for amount in amounts:
        if amount < 0:
            raise KernelError(INVALID_ARGUMENT, "resource amounts cannot be negative")


class Account:
    def __init__(self, limits: tuple[int, ...]) -> None:
        self.limits = limits
        self.usage = [0] * RESOURCE_KINDS


class ResourceLedger:
    def __init__(self, global_limits: tuple[int, ...], max_accounts: int) -> None:
        check_amounts(global_limits)
        if max_accounts < 1:
            raise KernelError(INVALID_ARGUMENT, "at least one account is required")
        self.global_limits = global_limits
        self.global_usage = [0] * RESOURCE_KINDS
        self.max_accounts = max_accounts
        self._accounts: dict[int, Account] = {}

    def owners(self) -> list[int]:
        return sorted(self._accounts)

    def account(self, owner: int) -> Account:
        if owner not in self._accounts:
            raise KernelError(INVALID_HANDLE, "owner has no resource account")
        return self._accounts[owner]

    def open_account(self, owner: int, limits: tuple[int, ...]) -> None:
        check_amounts(limits)
        if owner in self._accounts:
            raise KernelError(BAD_STATE, "owner already has a resource account")
        if len(self._accounts) >= self.max_accounts:
            raise KernelError(LIMIT_EXCEEDED, "account capacity reached")
        self._accounts[owner] = Account(limits)

    def charge(self, owner: int, amounts: tuple[int, ...]) -> None:
        account = self.account(owner)
        check_amounts(amounts)
        for kind in range(RESOURCE_KINDS):
            if account.usage[kind] + amounts[kind] > account.limits[kind]:
                raise KernelError(LIMIT_EXCEEDED, "owner quota exceeded")
            if self.global_usage[kind] + amounts[kind] > self.global_limits[kind]:
                raise KernelError(LIMIT_EXCEEDED, "global budget exceeded")
        for kind in range(RESOURCE_KINDS):
            account.usage[kind] += amounts[kind]
            self.global_usage[kind] += amounts[kind]

    def refund(self, owner: int, amounts: tuple[int, ...]) -> None:
        account = self.account(owner)
        check_amounts(amounts)
        for kind in range(RESOURCE_KINDS):
            if amounts[kind] > account.usage[kind]:
                raise KernelError(INVALID_ARGUMENT, "refund exceeds what the owner holds")
        for kind in range(RESOURCE_KINDS):
            account.usage[kind] -= amounts[kind]
            self.global_usage[kind] -= amounts[kind]

    def close_account(self, owner: int) -> None:
        account = self.account(owner)
        for kind in range(RESOURCE_KINDS):
            self.global_usage[kind] -= account.usage[kind]
        del self._accounts[owner]
