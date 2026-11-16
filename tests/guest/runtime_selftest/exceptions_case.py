from runtime_selftest.checks import Checks

USABLE_DEPTH = 40
EXCESSIVE_DEPTH = 1000000


class CaseError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


def fail(code: int) -> None:
    raise CaseError(code)


def descend(depth: int) -> int:
    if depth == 0:
        return 0
    return 1 + descend(depth - 1)


def raises(trigger, expected) -> bool:
    try:
        trigger()
    except expected:
        return True
    return False


def run(checks: Checks) -> None:
    order = []
    try:
        try:
            fail(7)
        finally:
            order.append("finally")
    except CaseError as error:
        order.append("handler")
        checks.require(error.code == 7 and error.args == (7,), "exception carries its arguments")
    else:
        order.append("else")
    checks.require(order == ["finally", "handler"], "finally runs before the outer handler")
    checks.require(isinstance(CaseError(1), Exception), "user exceptions derive from Exception")

    checks.require(raises(lambda: [][1], IndexError), "index out of range raises IndexError")
    checks.require(raises(lambda: {}["missing"], KeyError), "missing key raises KeyError")
    checks.require(raises(lambda: 1 // 0, ZeroDivisionError), "division by zero raises")
    checks.require(raises(lambda: int("x"), ValueError), "bad integer text raises ValueError")
    checks.require(raises(lambda: None.missing, AttributeError), "missing attribute raises")
    checks.require(raises(lambda: 1 + "a", TypeError), "mixed operands raise TypeError")
    checks.require(raises(lambda: fail(3), CaseError), "exceptions cross native frames")

    checks.require(raises(lambda: descend(EXCESSIVE_DEPTH), RuntimeError), "deep recursion stops")
    checks.require(descend(USABLE_DEPTH) == USABLE_DEPTH, "the stack is usable after the overflow")
