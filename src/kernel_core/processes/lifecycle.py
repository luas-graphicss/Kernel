from kernel_protocol.errors.codes import BAD_STATE, KernelError

NEW = 0
READY = 1
RUNNING = 2
BLOCKED = 3
DYING = 4
REAPED = 5

STATE_NAMES = ("new", "ready", "running", "blocked", "dying", "reaped")

ALLOWED_TRANSITIONS = (
    (READY, DYING),
    (RUNNING, DYING),
    (READY, BLOCKED, DYING),
    (READY, DYING),
    (REAPED,),
    (),
)


def check_transition(current: int, target: int) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise KernelError(
            BAD_STATE,
            "process cannot go from " + STATE_NAMES[current] + " to " + STATE_NAMES[target],
        )
