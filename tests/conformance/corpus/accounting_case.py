from corpus.digest import Digest
from corpus.failure import require
from corpus.prng import Generator
from kernel_core.processes.accounting import RESOURCE_KINDS, ResourceLedger
from kernel_protocol.errors.codes import OK, KernelError

MAX_ACCOUNTS = 6
GLOBAL_LIMITS = (4096, 96, 2048)
OWNER_LIMIT_BOUNDS = (1500, 40, 900)
AMOUNT_BOUNDS = (400, 12, 300)
OWNER_SPACE = 9


def random_amounts(generator: Generator, bounds: tuple[int, ...]) -> tuple[int, ...]:
    return tuple([generator.below(bound + 1) for bound in bounds])


def check_invariants(ledger: ResourceLedger) -> None:
    owners = ledger.owners()
    require(len(owners) <= MAX_ACCOUNTS, "account capacity is respected")
    for kind in range(RESOURCE_KINDS):
        total = 0
        for owner in owners:
            account = ledger.account(owner)
            require(account.usage[kind] >= 0, "usage is never negative")
            require(account.usage[kind] <= account.limits[kind], "usage respects the owner quota")
            total += account.usage[kind]
        require(total == ledger.global_usage[kind], "accounts add up to the global usage")
        require(total <= ledger.global_limits[kind], "global usage respects the budget")


def usage_snapshot(ledger: ResourceLedger) -> list[int]:
    snapshot = list(ledger.global_usage)
    for owner in ledger.owners():
        snapshot.extend(ledger.account(owner).usage)
    return snapshot


def run(seed: int, transitions: int) -> str:
    generator = Generator(seed)
    digest = Digest()
    ledger = ResourceLedger(GLOBAL_LIMITS, MAX_ACCOUNTS)

    for _ in range(transitions):
        choice = generator.below(100)
        owner = 1 + generator.below(OWNER_SPACE)
        before = usage_snapshot(ledger)
        owners_before = ledger.owners()
        try:
            if choice < 15:
                ledger.open_account(owner, random_amounts(generator, OWNER_LIMIT_BOUNDS))
            elif choice < 60:
                ledger.charge(owner, random_amounts(generator, AMOUNT_BOUNDS))
            elif choice < 90:
                ledger.refund(owner, random_amounts(generator, AMOUNT_BOUNDS))
            else:
                ledger.close_account(owner)
        except KernelError as error:
            digest.add(error.code)
            require(ledger.owners() == owners_before, "a failed operation keeps the accounts")
            require(usage_snapshot(ledger) == before, "a failed operation changes no usage")
        else:
            digest.add(OK)
        for amount in ledger.global_usage:
            digest.add(amount)
        check_invariants(ledger)

    digest.add(len(ledger.owners()))
    return digest.hexdigest()
