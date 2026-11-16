import _probe

from kernel_client.processes import Startup

REGISTER_ROUNDS = 3000000
FLOAT_ROUNDS = 1500000


def main() -> bool:
    seed = int(str(Startup().argument, "ascii"))
    if not _probe.floats_are_clear():
        print("holder: floating-point registers were not clear at start")
        return False
    return _probe.hold_registers(seed, REGISTER_ROUNDS) and _probe.hold_floats(seed, FLOAT_ROUNDS)
