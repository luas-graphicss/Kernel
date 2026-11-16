import _probe

from kernel_client.processes import Startup
from suites.support.layout import NULL_PAGE


def load_null() -> bool:
    _probe.load(NULL_PAGE)
    return True


def succeed() -> bool:
    return True


def fail() -> bool:
    return False


ENDINGS = {b"succeed": succeed, b"fail": fail, b"fault": load_null}


def main() -> bool:
    return ENDINGS[Startup().argument]()
