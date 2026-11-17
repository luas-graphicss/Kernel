# ADR 0007: Failure policy

[Português](0007-failure-policy.md)

Status: accepted.

## Context

A kernel that keeps running on possibly corrupted state is worse than one that stops. And a boot that fails silently leaves no evidence for whoever investigates.

## Decision

Each class of failure has a defined behavior:

| Failure | Behavior |
| --- | --- |
| Invalid boot input: DTB, memory or user image | One-line native diagnostic, `kernel: status=failed` and shutdown |
| Unexpected trap in S-mode | Trap report on the emergency stack, then panic |
| Invariant violation in the supervisor | Panic with a minimal diagnostic and halt |
| Unhandled exception in the supervisor Python | Traceback on the serial port and boot ended with a failure |
| Invalid input in a syscall | Error to the caller, with no access out of bounds |
| Process failure in U-mode | Trap report, end of the process and return of the status |
| Unhandled exception in an application | End the process, return the status and release the resources |
| OOM in a process | Reject the allocation or end the process, without consuming the supervisor reserve |
| Death of a service | Invalidate old endpoints, complete waits and restart only as the manifest says |
| Device without a response | Deadline, one reset attempt and, if it fails, quarantine of the device |
| Device that violates the protocol | Stopped by the supervisor, with the memory of the requests still pinned, until a reset |
| Write or flush error in a commit | `IO_ERROR` if the root was never sent, `UNKNOWN_OUTCOME` if it was; the volume refuses everything until it is mounted again |
| Corrupted or truncated volume, or one of unknown format | Read-only mount or unavailable, with the reason; never formatting |
| Restart of the file service | Normal recovery of the volume; old sessions and handles refused; no request re-executed |
| Flood of logs or events | Limiting and accounted dropping, preserving the critical reserve |

The panic path does not use the Python heap, does not depend on a service in U-mode and writes through the emergency UART. A second trap during the diagnostic shuts down without printing again.

Hard IRQ saves context, acknowledges the source, records data in a preallocated buffer and returns. It does not run Python, does not collect, does not format a log and does not allocate.

Every wait has a monotonic deadline. Recovering is not retrying without a limit.

Every boot ends with a line `kernel: status=ok` or `kernel: status=failed`, followed by `sbi_system_reset`. `kernel-tool` uses three exit codes to separate the cases: `0` for success, `1` for a failure of what was verified and `3` for unavailable infrastructure, such as a download that failed or a missing tool.

## Consequences

A test only passes when the status line, the assertions of the scenario and the exit code of the emulator agree. A boot that exceeds the deadline is a failure, not a skipped test.

Every line has a scenario or a suite case, with two caveats. Of the death of a service there are the closing of the endpoints, the completion of the waits and, with the system manager, the automatic restart within the count and the window of the configuration, as ADR 0009 records. Of the flood there are the bounded event queue and the bounded serial input, both with accounted dropping.

A client tells a definitive error from an unknown result by the code: `UNKNOWN_OUTCOME` only appears when an operation with an effect may have happened. No layer repeats an operation with an effect on its own.

## Assumptions to confirm

- Quarantine of DMA frames after a reset failure does not exhaust memory in long sequences of failures. The quarantined frames only return at the next boot.
- The restart policy of the manifest, with a count and a window, avoids a restart loop without masking a permanent defect.
