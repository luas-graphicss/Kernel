# Error codes

[Português](errors.md)

One set of codes applies to syscalls, messages and Python models. Values are small integers, stable within an ABI version.

| Code | Name | When it occurs |
| --- | --- | --- |
| 0 | `OK` | Operation completed |
| 1 | `INVALID_ARGUMENT` | Invalid format or range: truncated message, nonzero reserved field, negative count |
| 2 | `INVALID_HANDLE` | Nonexistent index, stale generation, free slot, nonzero reserved bits or wrong object type |
| 3 | `BAD_STATE` | Lifecycle transition not allowed in the object's current state |
| 4 | `LIMIT_EXCEEDED` | Process quota, global budget, table capacity, derivation depth or wait-chain limit exhausted |
| 5 | `BAD_ADDRESS` | Memory range not mapped with the permission required by the operation |
| 6 | `MESSAGE_TOO_LARGE` | Payload exceeds the operation or receiver-buffer limit |
| 7 | `UNSUPPORTED` | Unknown syscall number, operation or version |
| 8 | `ACCESS_DENIED` | Capability exists but lacks the required right |
| 9 | `TIMED_OUT` | Deadline passed before completion |
| 10 | `CANCELLED` | Wait interrupted by `process_interrupt` |
| 11 | `PEER_CLOSED` | Peer died, closed the endpoint or no longer awaits the reply |
| 12 | `OUT_OF_MEMORY` | No physical memory above the supervisor reserve |
| 13 | `WOULD_DEADLOCK` | Waiting would create a process cycle |
| 14 | `IO_ERROR` | Device reported failure, did not answer a side-effect-free request, or volume failed and requires remounting |
| 15 | `NO_SPACE` | Volume lacks free blocks |
| 16 | `NOT_FOUND` | Path or name does not exist, or an open file was removed |
| 17 | `ALREADY_EXISTS` | Name already exists in the directory |
| 18 | `NOT_A_DIRECTORY` | Operation requires a directory but found a file |
| 19 | `IS_A_DIRECTORY` | Operation requires a file but found a directory |
| 20 | `NOT_EMPTY` | Directory being removed or replaced still has entries |
| 21 | `READ_ONLY` | Mount or device rejects changes |
| 22 | `CORRUPTED` | Volume, image or block does not match its format or checksum |
| 23 | `UNKNOWN_OUTCOME` | A side-effecting operation may or may not have happened: device or service did not confirm in time |
| 24 | `CONNECTION_REFUSED` | Peer rejected a connection with a reset, or a datagram received a port-unreachable response |
| 25 | `CONNECTION_RESET` | Established connection terminated by peer reset |
| 26 | `UNREACHABLE` | No route, link down, neighbor resolution unanswered or path reports destination unreachable |

A syscall returns its result in `a0`: a nonnegative value on success, or the negated error code. `debug_write` with an invalid pointer returns `-5`.

Python values are in `kernel_protocol.errors.codes`. Models and client-library functions raise `KernelError` with the code. C values are in `native/include/kernel/abi/errors.h`. `tests/conformance/test_abi_constants.py` compares both sides, including syscall numbers, rights, process limits and formats.

A failed syscall leaves no partial effect. After `LIMIT_EXCEEDED`, resource accounts are unchanged.

Codes 14–23 originate in device and file services; the supervisor returns only `IO_ERROR`, from `device_open` and `device_reset`. Codes 24–26 originate in the network service, described in `specs/network/socket-service.en.md`, and are never returned by the supervisor. `UNKNOWN_OUTCOME` alone does not establish whether the operation happened. It does not authorize a retry: the recipient must query state as described in `specs/filesystem/file-service.en.md`.
