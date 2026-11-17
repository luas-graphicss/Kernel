# Processes

[Português](processes.md)

A process consists of an address space, a capability table and a private MicroPython runtime. The model is recorded in ADR 0004.

## Creation

`process_spawn` takes the system capability with `ADMIN` and the address of a 296-byte request. Integers are unsigned and little-endian.

| Offset | Size | Field | Rule |
| --- | --- | --- | --- |
| 0 | 4 | `version` | `1`; otherwise `UNSUPPORTED` |
| 4 | 4 | `priority` | 0, most urgent, through 3 |
| 8 | 8 | `heap_bytes` | Multiple of 4096; zero uses the image-declared heap |
| 16 | 8 | `memory_bytes` | Multiple of 4096; memory quota beyond runtime usage, including created buffers |
| 24 | 4 | `name_length` | 1–64 |
| 28 | 4 | `argument_length` | 0–64 |
| 32 | 4 | `grant_count` | 0–8 |
| 36 | 4 | reserved | Zero |
| 40 | 128 | `grants` | Eight handle/rights pairs, 8 bytes per field; unused pairs zeroed |
| 168 | 64 | `name` | Zero-padded program module path |
| 232 | 64 | `argument` | Zero-padded program argument bytes |

The name is a frozen-module path: lowercase letters, digits and `_`, separated into components by `.`. Invalid fields return `INVALID_ARGUMENT`.

Each grant follows `capabilities.en.md`: unknown handles return `INVALID_HANDLE`; rights absent from the source, missing `DELEGATE` or requested `RECEIVE` return `ACCESS_DENIED`.

After native validation, Python policy decides admission:

| Condition | Error |
| --- | --- |
| Priority more urgent than the creator's | `ACCESS_DENIED` |
| `heap_bytes` exceeds the profile's per-process limit | `LIMIT_EXCEEDED` |
| 16 live processes | `LIMIT_EXCEEDED` |
| Process memory budget exhausted | `LIMIT_EXCEEDED` |
| Insufficient frames above the supervisor reserve | `OUT_OF_MEMORY` |

Creation is atomic. A process appears only after its address space, runtime, grants and creator handle exist; any failure releases everything. `spawn-failures` verifies this by failing each creation allocation in turn.

The creator receives a process handle with `READ`, `ADMIN` and `DELEGATE`.

## Startup

The supervisor prepares a 256-byte startup block with heap and stack bounds, process identity, granted handles in request order, module name and argument. The runtime reads it, imports the module and executes `main()`. A truthy return exits with status 0; a falsy return or exception exits with status 1.

Request and startup-block offsets are in `native/include/kernel/abi/process.h`. The reference request encoder is `kernel_protocol.wire.spawn`.

## Scheduling

There are four priorities. The supervisor runs the most urgent ready process for a 10 ms quantum, round-robin within each priority. A ready process waiting for 8 selections gains one priority level until it runs, then returns to its own priority.

A process blocked in `ipc_call`, or in `ipc_send` on a full queue, donates priority to the endpoint owner while waiting, through chains of at most 8 processes. Donation ends with the wait and never exceeds the donor's priority.

The client library defaults new processes to priority 2. `init` runs at priority 1.

## Waiting and termination

`process_wait` requires `READ` and returns termination status: reason in the high 32 bits and value in the low 32.

| Reason | Code | Value |
| --- | --- | --- |
| `exit` | 1 | Status passed to `process_exit` |
| `fault` | 2 | Exception `scause` |
| `killed` | 3 | Zero |

If the process is alive, the caller blocks until termination or the deadline. Waiting for a process directly or indirectly waiting for the caller returns `WOULD_DEADLOCK`. Chains beyond 8 processes return `LIMIT_EXCEEDED`.

`process_kill` requires `ADMIN` and terminates the process; an already-terminated target returns `BAD_STATE`. `process_interrupt` requires `ADMIN` and a blocked target: its waiting call returns `CANCELLED`. A nonblocked target returns `BAD_STATE`.

Termination for any reason releases mappings, capabilities, pending messages and memory. Private frames are zeroed before reuse by another process. Exit status remains available through `process_wait` while a process handle exists.

## Counters

`system_counters` requires `READ` on the system capability and writes twenty little-endian 64-bit integers. Buffers smaller than 160 bytes return `INVALID_ARGUMENT`.

| Index | Counter |
| --- | --- |
| 0 | Usable frames |
| 1 | Free frames |
| 2 | Supervisor-reserve frames |
| 3 | Processes |
| 4 | Objects |
| 5 | Capabilities |
| 6 | Endpoints |
| 7 | Pending messages |
| 8 | Pending IPC bytes |
| 9 | Buffers |
| 10 | Dropped events |
| 11 | Process failures |
| 12 | Context switches |
| 13 | Preemptions |
| 14 | Rejected allocations |
| 15 | Timer interrupts |
| 16 | Serviced external interrupts |
| 17 | In-flight device requests |
| 18 | Device-request-pinned buffers |
| 19 | Quarantined devices |

Suites compare resource counters before and after each case. Policy does the same across `init` and prints `policy: resources=released` or the list of changes.
