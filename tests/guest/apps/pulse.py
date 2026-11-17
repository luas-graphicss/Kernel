from kernel_client import processes

NANOSECONDS_PER_MICROSECOND = 1000


def main() -> bool:
    print(f"pulse: clock-us={processes.clock() // NANOSECONDS_PER_MICROSECOND}")
    return True
