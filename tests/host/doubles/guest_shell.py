import sys

FRAMES = 6000
FRAME_BYTES = 4096
TICK_MICROSECONDS = 1000
FINAL_LINES = (
    "system: shutdown=complete clean=1",
    "policy: reaped=init reason=exit value=0 live=0 memory-in-use=0",
    "policy: collector=measured collections=2 pause-total-us=40 "
    "pause-p99-us=30 pause-longest-us=30",
    "policy: resources=released",
    "kernel: status=ok",
)


def say(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def main() -> None:
    leaking = "--leak" in sys.argv
    outcomes: dict[str, str] = {}
    free = FRAMES - 1000
    clock = 0
    say("boot: hart=0")
    say("shell: ready")
    for line in sys.stdin:
        words = line.split()
        if not words:
            continue
        name = words[0]
        status = "ok"
        if name == "silence":
            continue
        if name == "run":
            application = str(len(outcomes) + 1)
            outcomes[application] = "exit 1" if words[1].endswith("hog.py") else "exit 0"
            if words[1].endswith("pulse.py"):
                clock += TICK_MICROSECONDS
                say(f"kernel> pulse: clock-us={clock}")
            say(f"run: application={application} program={words[1]}")
        elif name == "kill":
            outcomes[words[1]] = "killed 0"
            say(f"kill: application={words[1]}")
        elif name == "wait":
            reason, value = outcomes[words[1]].split()
            say(f"wait: application={words[1]} reason={reason} value={value}")
        elif name == "mem":
            free -= 1 if leaking else 0
            say(
                f"kernel> mem: frames-usable={FRAMES} frames-free={free} "
                f"frames-reserved=512 bytes-free={free * FRAME_BYTES}"
            )
            say("mem: processes=8 objects=40 capabilities=60 endpoints=20 buffers=4 ipc-bytes=0")
        elif name == "trap":
            say("kernel> trap: cause=13")
        elif name == "fail":
            status = "failed error=NOT_FOUND"
        if name == "shutdown":
            say("system: shutdown=started action=shutdown")
            for final in FINAL_LINES:
                say(final)
            return
        joined = "spin: started" if name == "run" and words[1].endswith("spin.py") else ""
        say(f"shell: command={name} status={status}{joined}")


main()
