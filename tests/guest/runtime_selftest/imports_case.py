import builtins
import sys

from runtime_selftest.checks import Checks

FROZEN_PATH = ".frozen"
ABSENT_BUILTINS = ("eval", "exec", "compile", "open", "input")


def run(checks: Checks) -> None:
    import kernel_core.scheduling.selection as first
    import kernel_core.scheduling.selection as second

    checks.require(first is second, "a frozen module is imported once")
    checks.require("kernel_core.scheduling.selection" in sys.modules, "imports are registered")
    checks.require(first.PRIORITY_LEVELS == 4, "frozen module globals are initialized")
    checks.require(sys.path == [FROZEN_PATH], "only frozen modules are on the import path")

    missing = False
    try:
        __import__("module_that_is_not_frozen")
    except ImportError:
        missing = True
    checks.require(missing, "a module outside the image cannot be imported")

    for name in ABSENT_BUILTINS:
        checks.require(not hasattr(builtins, name), "the runtime cannot load external code")
