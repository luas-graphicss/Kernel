# Device services

[Português](device-services.md)

Drivers are U-mode processes started by `init` from the manifest in `kernel_services.init.manifest`. Each receives a device capability, described in `devices.en.md`, and offers the device to other processes through an IPC endpoint. Messages follow `messages.en.md`; formats are defined in `kernel_protocol.services`.

| Service | Program | Device | Priority |
| --- | --- | --- | --- |
| Console | `kernel_services.console.main` | Serial port | 1 |
| Entropy | `kernel_services.entropy.main` | VirtIO model 4 | 2 |
| Block | `kernel_services.block.main`, one process per disk | VirtIO model 2 | 1 |
| Files | `kernel_services.filesystem.main` | None: receives block-service endpoints | 2 |

The file service is described in `specs/filesystem/file-service.en.md`.

With `init=kernel_services.manager.main`, the system manager starts these services using the configured priority, heap and restart policy. It also starts `kernel_services.network.main`, which receives VirtIO model 1 and includes its driver in the same process. See `specs/system/control-service.en.md` and `specs/network/`. The lifecycle below applies to both startup paths.

## Lifecycle

Operations 1–15 are shared lifecycle operations. Service-specific operations start at 16.

| Number | Operation | Direction | Contents |
| --- | --- | --- | --- |
| 1 | `REGISTER` | Service to `init`, through the registration endpoint | Transfers the service endpoint. The block service also sends its disk serial number |
| 2 | `STOP` | `init` to service | Empty. The service completes outstanding work, replies and exits with status 0 |

A service's startup argument contains its supervising process identity in 8 bytes. `STOP` and administrative operations are accepted only from that process; other callers receive `ACCESS_DENIED`. Identity comes from supervisor-filled message metadata, not the payload.

`init` waits up to 20 seconds for registration and up to 20 seconds for shutdown. A service that fails to register is terminated and marked `failed`; one that ignores shutdown is terminated with `process_kill`.

An error response sets the message error flag and carries a 4-byte code. A request with an unexpected capability returns `INVALID_ARGUMENT` and closes that capability. Unknown operations return `UNSUPPORTED`.

## Block storage

Each client supplies its own buffer. Transfers take place in that buffer, not in message payloads.

| Number | Operation | Request | Response |
| --- | --- | --- | --- |
| 16 | `ATTACH` | Empty, with a buffer capability having `READ` and `WRITE` | Geometry |
| 17 | `READ` | Transfer | Empty; sectors are placed in the buffer |
| 18 | `WRITE` | Transfer | Empty |
| 19 | `FLUSH` | Empty | Empty, after device acknowledgment |
| 20 | `DETACH` | Empty | Empty; closes the client's buffer |
| 21 | `EVICT` | Client identity | Empty; service supervisor only |

Geometry, 44 bytes:

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 8 | Disk sectors |
| 8 | 4 | Bytes per sector: 512 |
| 12 | 4 | Flags: `0x1` read-only, `0x2` supports flush |
| 16 | 8 | Service instance |
| 24 | 20 | Zero-padded disk serial number |

A transfer occupies 16 bytes: first sector in 8 bytes, sector count in 4 and offset into the client's buffer in 4.

| Condition | Error |
| --- | --- |
| `ATTACH` without a buffer, or without `READ` and `WRITE` | `INVALID_ARGUMENT` |
| Fifth client | `LIMIT_EXCEEDED` |
| Transfer or flush without `ATTACH` | `BAD_STATE` |
| Sectors outside the disk | `INVALID_ARGUMENT` |
| Range outside the client's buffer | `INVALID_ARGUMENT`, returned by the supervisor to the driver |
| Write to a read-only disk | `READ_ONLY` |
| Flush on a disk without the command | `UNSUPPORTED` |
| Device reported failure | `IO_ERROR` |
| Device did not respond within 5 seconds | `IO_ERROR` for reads; `UNKNOWN_OUTCOME` for writes and flushes |

The driver resets an unresponsive device before replying, releasing request memory. If reset also fails, the device is quarantined and subsequent requests return `IO_ERROR`.

The `kernel_client.blocks` client library treats a dead or unresponsive block service the same way: `IO_ERROR` for reads and `UNKNOWN_OUTCOME` for writes and flushes. No request is automatically repeated.

Flush support authorizes a volume to accept writes. Without it the file service mounts the volume read-only.

## Console

| Number | Operation | Request | Response |
| --- | --- | --- | --- |
| 16 | `WRITE` | Up to 1024 text bytes | Accepted byte count in 4 bytes |
| 17 | `READ_LINE` | Wait duration in nanoseconds, 8 bytes. `0xFFFFFFFFFFFFFFFF` waits indefinitely | Line without its terminator |

Output converts each `\n` to `\r\n`. The service writes while the transmitter accepts bytes and gives up after 1 second. Its response reports how many request bytes were sent; the client decides whether to resend the remainder. Requests above 1024 bytes return `MESSAGE_TOO_LARGE`.

Input is assembled into lines and echoed.

| Received byte | Effect |
| --- | --- |
| `\r`, `\n` or `\r\n` | Ends the line |
| Backspace or delete | Removes the last whole character, including multi-byte UTF-8 |
| `0x15` | Clears the line |
| TAB | Enters the line as a space |
| `0x1B` and its escape sequence | Discarded through the final byte of `ESC [`, the byte after `ESC O`, or otherwise the first non-intermediate byte. A control byte inside the sequence ends it and has its usual effect |
| Other control byte | Discarded |
| Byte beyond 255 in a line | Discarded with an audible echo signal. The line remains rejected until fully cleared |

A rejected line is never delivered truncated. Its `READ_LINE` returns `MESSAGE_TOO_LARGE`; the next read receives the next line.

At most four complete lines wait for a reader. Each additional line is discarded and the service prints `console: dropped-lines=N`, where N is the total discarded since service startup.

Only one reader may wait at a time. A new `READ_LINE` cancels the previous one with `CANCELLED`. If no line arrives before the deadline, the response is `TIMED_OUT`.

The supervisor's emergency console does not depend on this service.

## Entropy

| Number | Operation | Request | Response |
| --- | --- | --- | --- |
| 16 | `READ` | Byte count from 1 to 256, in 4 bytes | Device-provided bytes |

An out-of-range count returns `INVALID_ARGUMENT`. A device that does not respond within 2 seconds is reset and the request returns `IO_ERROR`.

Without an entropy device this service does not exist. `init` reports `init: entropy=unavailable`; no other component supplies replacement bytes.

## Evidence

The `devices` suite covers drivers and, in its `services` scenario, all three services and rejection of unauthorized callers. `without-entropy` boots without the entropy device. `tests/conformance/test_console.py` covers line discipline and `tests/conformance/test_services.py` covers the manifest.
