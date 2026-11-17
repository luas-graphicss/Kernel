# Diagnosing

[Português](diagnostics.md)

Where to look when something fails, in the guest and in the host tools.

## What the console says

Each line starts with the name of whoever wrote it.

| Prefix | Who writes | What it is for |
| --- | --- | --- |
| `boot:` | Native code, before the runtime | Memory, reserved regions, console, devices of the DTB |
| `trap:` | Native code | Unexpected trap in the supervisor: cause, `sepc`, `stval`, `sstatus`, `ra` and `sp` |
| `panic:` | Native code | Reason for a fatal stop |
| `policy:` | Python policy of the supervisor | Profile checked, initial process admitted and reaped, resources released or leaked, deadlock |
| `system:` | System manager | Configuration accepted or refused, state of each service, applications, shutdown |
| `shell:` | Shell | `shell: command=<name> status=ok` or `status=failed error=<ERROR>` after each command |
| `kernel:` | Native code | `kernel: power=restart` and the last line, `kernel: status=ok` or `kernel: status=failed` |

The last line says how the system ended. Without it, the kernel did not reach the end: it hung, was killed by the emulator deadline or the emulator crashed.

`policy: resources=leaked` lists the counters that did not return to their boot value. `policy: stopped=deadlock` says all processes were waiting for one another.

With `trace=collector` in the kernel arguments, the policy writes at the end `policy: collector=measured collections=<n> pause-total-us=<t> pause-p99-us=<p> pause-longest-us=<m>`. These are the pauses of the supervisor collector, measured by the timer. `benchmark` and `soak` start the system this way.

Different processes write to the console without coordinating with one another. The text of one may appear glued to the end of the line of another, as in `shell: command=run status=okspin: started`. The host tools look for the patterns inside the line and do not depend on where it ends.

## In the shell

- `ps` shows the state of the system, of each service, with restarts used and allowed, and of each application.
- `mem` shows usable, free and reserved frames, and the counters of processes, objects, capabilities, endpoints, buffers and pending IPC bytes.
- `net` shows address, link and counters of the interface; `net neighbors` shows the ARP table.
- `cat boot/system/release` shows the version, the interface of the boot image and the runtime.

The errors of each command are in `system-operation.en.md`.

## `kernel-tool` exit codes

| Status | Meaning |
| --- | --- |
| 0 | The verification passed |
| 1 | The verification failed |
| 2 | Incorrect use of the command |
| 3 | Infrastructure was missing: host tool, emulator, isolated network. Nothing was verified |

Status 3 never counts as a pass. In `verify --all` the verification is recorded as `incomplete`.

## Reports

| Path in `build/qemu-riscv64/` | Content |
| --- | --- |
| `reports/<suite>.json` | Each scenario, with failures, duration, hashes and the complete transcript |
| `reports/captures/<scenario>.pcap` | Traffic of the scenarios with a network |
| `qualification/verification.json` | Each verification of the matrix: passed, failed or incomplete, with the reason |
| `qualification/boots.json` | Each repeated boot, with duration and hash of the transcript |
| `qualification/measurements.json` | Machine, measurements and the result of each budget |
| `qualification/soak.json` | Rounds, trends, collector pauses and one sample per round |
| `qualification/reproduction.json` | Hashes of each clean build |
| `soak/soak.log` | Everything the guest wrote during the soak |
| `release/.../release-report.json` | Result of each gate |

The fuzzing reports are in `build/fuzz/`: `ledger.json` with the accumulated time, `report.json` with the last session and `findings/` with the failures.

## Reproducing a failure

- Scenario: `uv run kernel-tool test --suite <suite> --scenario <scenario>`. The transcript of the failure goes to the terminal and to the report.
- Fuzzing: copy the line from `build/fuzz/findings/<family>/<target>/<hash>.hex` to `tests/fuzz/regressions/<family>/<target>.hex` and run `uv run kernel-tool replay-corpus --family <family>`. The `.txt` file next to it carries the diagnostic of the original failure.
- Volume: `uv run kernel-tool inspect-volume <image>` and `uv run kernel-tool verify-filesystem --image <image>`.
- A boot that does not end: `uv run kernel-tool run --deadline <seconds>` closes the session and shows what the console wrote up to that point.

## What the tools do not show

There is no debugger attached to the guest and no memory dump. The diagnostic of a trap in the supervisor is the `trap:` line. A fault in a user process appears as its exit reason, in `wait` and in `ps`.
