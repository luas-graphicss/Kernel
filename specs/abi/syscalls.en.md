# Syscalls

[Português](syscalls.md)

ABI version 1.0, frozen under `specs/compatibility.en.md`.

## Convention

A U-mode process executes `ecall` with:

| Register | Contents |
| --- | --- |
| `a7` | Syscall number |
| `a0`–`a5` | Arguments |
| `a0` on return | Nonnegative result or negated error code |

All other integer and floating-point registers retain their values. Execution resumes at the instruction after `ecall`.

The supervisor trusts neither caller nor client library:

- Handles are resolved in the caller's capability table. Unknown handles or wrong object types return `-INVALID_HANDLE`; missing rights return `-ACCESS_DENIED`.
- A pointer is accepted only if its entire range is mapped with the required permissions. Otherwise `-BAD_ADDRESS` is returned without effect. Requests and messages are copied into the supervisor before interpretation.
- A deadline is an absolute `clock_now` timestamp in nanoseconds. `0xFFFFFFFFFFFFFFFF` means no deadline. An operation that would wait with an expired deadline returns `-TIMED_OUT` without blocking.

## Table

| Number | Name | Arguments | Result |
| --- | --- | --- | --- |
| 0 | `process_exit` | `a0`: status | Does not return |
| 1 | `debug_write` | `a0`: buffer address, `a1`: length | Bytes written |
| 2 | `clock_now` | None | Nanoseconds since boot |
| 3 | `process_yield` | None | 0 |
| 4 | `capability_close` | `a0`: handle | 0 |
| 5 | `capability_derive` | `a0`: handle, `a1`: rights | Derived capability handle |
| 6 | `capability_revoke` | `a0`: handle | Invalidated capability count |
| 7 | `capability_inspect` | `a0`: handle | Type, rights and depth |
| 8 | `endpoint_create` | None | Endpoint handle |
| 9 | `ipc_send` | `a0`: endpoint, `a1`: message address, `a2`: length, `a3`: capability to transfer or 0, `a4`: deadline | 0 |
| 10 | `ipc_receive` | `a0`: endpoint, `a1`: buffer address, `a2`: capacity, `a3`: metadata address, `a4`: deadline | Message length |
| 11 | `ipc_call` | `a0`: endpoint, `a1`: message address, `a2`: length, `a3`: reply address, `a4`: reply capacity, `a5`: control-block address | Reply length |
| 12 | `ipc_reply` | `a0`: reply capability, `a1`: message address, `a2`: length, `a3`: capability to transfer or 0 | 0 |
| 13 | `buffer_create` | `a0`: size in bytes | Buffer handle |
| 14 | `buffer_map` | `a0`: handle, `a1`: mapping rights, `a2`: description address | 0 |
| 15 | `buffer_unmap` | `a0`: mapping address | 0 |
| 16 | `process_spawn` | `a0`: system capability, `a1`: request address | Process handle |
| 17 | `process_wait` | `a0`: process handle, `a1`: deadline | Termination status |
| 18 | `process_kill` | `a0`: process handle | 0 |
| 19 | `process_interrupt` | `a0`: process handle | 0 |
| 20 | `system_counters` | `a0`: system capability, `a1`: buffer address, `a2`: buffer size | Counter count |
| 21 | `device_list` | `a0`: system capability, `a1`: buffer address, `a2`: buffer size | Device count |
| 22 | `device_claim` | `a0`: system capability, `a1`: slot | Device handle |
| 23 | `device_open` | `a0`: device, `a1`: requested features, `a2`: session address | 0 |
| 24 | `device_config` | `a0`: device, `a1`: offset, `a2`: buffer address, `a3`: length | Bytes copied |
| 25 | `device_submit` | `a0`: device, `a1`: request address | Request token |
| 26 | `device_wait` | `a0`: device, `a1`: completion address, `a2`: deadline | 1 |
| 27 | `device_reset` | `a0`: device | 0 |
| 28 | `serial_write` | `a0`: device, `a1`: buffer address, `a2`: length | Bytes accepted |
| 29 | `serial_read` | `a0`: device, `a1`: buffer address, `a2`: capacity, `a3`: deadline | Bytes read |
| 30 | `system_power` | `a0`: system capability, `a1`: action | 0 |

Any other number returns `-UNSUPPORTED`.

Calls 4–7 are described in `capabilities.en.md`, 8–12 in `messages.en.md`, 13–15 in `buffers.en.md`, 16–20 in `processes.en.md`, and 21–29 in `devices.en.md`. Call 30 is described below.

## Process and time

### `process_exit`

Terminates the process. The supervisor retains the low 32 bits of `a0` as status, releases process resources and delivers status to waiters.

### `debug_write`

Writes bytes to the supervisor diagnostic console.

- Length above 256: `-MESSAGE_TOO_LARGE`; nothing read or written.
- Unreadable range `[address, address + length)`, or 64-bit addition overflow: `-BAD_ADDRESS`; nothing written.
- Zero length is valid and returns 0.

This syscall requires no capability. It is the diagnostic channel for programs and suites, bypassing the console service; ordinary process output should use the console endpoint described in `device-services.en.md`. Removing this syscall is an incompatible change under `specs/compatibility.en.md`.

### `clock_now`

Returns monotonic nanoseconds since boot, derived from the `time` counter and the DTB frequency. The value never decreases.

### `process_yield`

Yields the processor. The process stays ready and returns to the end of its priority queue.

### `system_power`

Records the firmware action requested at system termination: action 0 shuts down, action 1 restarts.

- Requires `ADMIN` on the system capability. Wrong object type returns `-INVALID_HANDLE`; missing rights return `-ACCESS_DENIED`.
- Actions other than 0 or 1 return `-INVALID_ARGUMENT` without change.

The call returns immediately and terminates no processes. The system ends when its last user process exits. If termination succeeded and restart was requested, the supervisor prints `kernel: power=restart` before `kernel: status=ok` and requests a cold reboot through SBI's reset extension. Otherwise it requests shutdown. Without a call, shutdown is the default.

The system manager owns the application/service shutdown sequence described in `specs/system/control-service.en.md`.

## Traps other than syscalls

Any other U-mode exception terminates the process. The supervisor prints `user: fault` with cause, `scause`, `sepc`, `stval` and process index, then releases its resources. Waiters receive reason `fault` and the `scause` value. The process is never resumed.

Timer interrupts are not errors. They suspend the process at quantum expiry and return it to the queue with its context intact.

Numbers are defined in `native/include/kernel/abi/syscalls.h` and `kernel_protocol.syscalls.numbers`.
