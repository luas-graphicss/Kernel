# ADR 0004: Process model

[Português](0004-process-model.md)

Status: accepted.

## Context

Untrusted applications cannot run inside the supervisor interpreter, and two programs cannot share a heap, globals or collector state.

## Decision

Each process has an address space, a private MicroPython runtime and a single executable context. There are no threads inside a process; internal concurrency uses events.

The lifecycle is `new`, `ready`, `running`, `blocked`, `dying` and `reaped`, with the transitions of `src/kernel_core/processes/lifecycle.py`. Any other transition is an error.

The native table keeps identity and executable state. The Python scheduler keeps only policy metadata. Before applying a selection, the native mechanism revalidates generation and state, so that an old decision does not reactivate a process that has ended.

The initial policy has four priority levels, round-robin within the level and aging: a ready process that waits `AGING_THRESHOLD` selections goes up one level until it runs, and then returns to its base priority. The nominal quantum is 10 ms and is not a real-time guarantee.

Whoever blocks waiting for the owner of an endpoint lends it their own priority, for up to 8 chained processes. The donation ends together with the wait.

Process identities are generational handles, defined in ADR 0005.

## Consequences

One runtime per process uses more memory than a shared interpreter. The initial budget is 16 processes with up to 4 MiB of heap each.

The selection model and the accounting model are pure code, verified on CPython and on the target MicroPython. The Python supervisor applies them over the native mechanisms: at each step it picks a process and asks native code to run it for a quantum. The return says whether the process was preempted, yielded, blocked, ended or asked for the creation of another.

Every process is born from the same user image. Code and read-only data are the same pages in every process; data, heap and stack are private. The layout is in `specs/abi/user-image.en.md`, and creation, waiting and ending in `specs/abi/processes.en.md`.

Interrupts are only accepted while a process runs in U-mode. The supervisor, native or Python, is never interrupted. The timer interrupt saves the context of the process and returns control to the native loop, which expires the waits that are due and ends the quantum without running Python and without allocating.

The `processes` suite preempts a program that allocates without stopping and a loop that never yields. Both keep running until they are ended, and the integer and floating-point register patterns of the other processes do not change.

## Assumptions to confirm

- `AGING_THRESHOLD = 8` avoids starvation without inverting priorities in practice. The model proves the wait bound, not the adequacy of the value.
- Bounded priority donation resolves the IPC dependencies between services.
