# ADR 0002: Boundary between Python and native code

[Português](0002-python-native-boundary.md)

Status: accepted.

## Context

The project is Python-first, but a real kernel needs mechanisms that stay correct when a Python process hangs, runs out of memory or sends malformed data. Without a written rule, the native layer grows until it becomes a second implementation of the policies.

## Decision

Python decides. Native code executes and validates.

In freestanding C17 and RISC-V Assembly: boot, trap entry and exit, context switch, MMU, validation of access to user memory, IPC primitives, capability enforcement and device transport. Assembly covers only what requires a machine instruction or convention: the entry point, the trap vector, the entry into U-mode and the reading of registers for the GC.

In Python: scheduling, process admission, quotas, supervision, VFS, filesystem, network protocols, driver behavior and applications.

A new native addition needs at least one of these reasons: it depends on privilege, accesses physical memory or registers, protects memory safety, is part of the ABI or integrates the interpreter. Convenience and unmeasured performance are not enough.

The native supervisor does not depend on Python to handle a trap, release a resource or end a process. Python does not run in hard IRQ.

The surface exposed to the supervisor Python is the `_supervisor` module. The arguments are process handles, sizes, counts and error codes, and the native side checks each one before using it. Each new binding enters this table with its reason.

| Binding | Returns | Reason |
| --- | --- | --- |
| `machine()` | Boot hart, base and size of the RAM | Facts from the DTB, which only native code reads and validates |
| `limits()` | Limits of the compiled profile and size of the supervisor heap | The profile is part of the ABI and the heap comes from the link layout |
| `user_region()` | Base and size of the user virtual region | Link layout of the user image |
| `arguments()` | Text of `bootargs` from the DTB | A fact from the DTB. The policy reads from it the initial program, in `init=`, and the trace request, in `trace=schedule` |
| `memory()` | Frame size and number of usable, free and supervisor-reserve frames | State of the physical allocator, from which the memory budget of the processes comes |
| `counters()` | The resource and activity counters of `specs/abi/processes.en.md` | State of the native mechanisms. The policy compares the resources before and after `init` |
| `prepare_program()` | `ok`, `absent` or the reason the user image was rejected | Validation of untrusted bytes before the policy admits a process |
| `footprint(heap_bytes)` | Private frames of a process with that heap, or zero if it does not fit in the region | Depends on the layout of the image and of the page tables |
| `spawn(program, heap_bytes, memory_frames, capabilities, ipc_pending_bytes)` | Handle of the first process, or a negated error code | Depends on privilege: creates the address space, the runtime and the system capability |
| `pending_spawn()` | Creation request on hold, already validated: who asked, program, priority, heap, memory and number of grants | The policy decides the admission without reading user memory |
| `admit_spawn(memory_frames, capabilities, ipc_pending_bytes)` | Handle of the process created, or a negated error code | Completes the creation on hold with the quotas the policy chose |
| `reject_spawn(error)` | Nothing | Delivers to the requester the error the policy chose |
| `run(handle, quantum_nanoseconds)` | Reason for the return, `preempted`, `yielded`, `blocked`, `exited`, `spawn` or `stale`, and two values that depend on it | Depends on privilege: switches the address space, arms the timer, enters U-mode and serves the syscalls |
| `next_event()` | Next event of the bounded queue, with the type and the process, or `None` | Processes become ready or end inside the native mechanisms |
| `events_overflowed()` | Whether the queue dropped any event since the last query | The policy rebuilds its own state from the native table when it loses events |
| `idle()` | Whether there was any wait with a deadline to wait for | Waits for the timer with `wfi` when no process is ready |
| `kill(handle)` | Zero or a negated error code | Ends the process and releases what it held |
| `release(handle)` | Zero or a negated error code | Returns the slot of the process after the policy accounted for the end |
| `process_state(handle)` | State of the process in the native table | The policy checks an old decision against the real state |

The user runtime has a native surface of its own, the `_process` module. It assembles the arguments and executes `ecall`. It is not a security boundary: the supervisor validates each call as `specs/abi/syscalls.en.md` describes.

## Consequences

Every call between the two sides has a cost and needs validation in both directions. The bindings return integers, booleans, strings, tuples and `None`. Physical addresses appear only as facts for budgeting and diagnostics: no binding accepts an address as an argument.

The supervisor interpreter and the frozen policies belong to the TCB. A policy error there weighs the same as an error in C.

## Assumptions to confirm

- The cost of IPC with policies in Python fits in the 10 ms quantum. Measure before moving any policy to C.
- Opaque generational handles are enough for Python to reference native objects without a parallel ownership table.
