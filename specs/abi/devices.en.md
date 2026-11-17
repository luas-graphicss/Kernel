# Devices

[Português](devices.md)

The supervisor discovers devices in the DTB, exclusively owns their registers and queues, and grants each device to a U-mode driver through a capability. The driver chooses requests. The supervisor validates them and writes the physical addresses the device will read. Decisions are recorded in ADR 0008.

## Discovery

At boot the supervisor looks for:

- One `sifive,plic-1.0.0` or `riscv,plic0` interrupt controller with an S-mode external-interrupt context.
- The `ns16550a` serial port already used as the boot console, if it declares an interrupt.
- Up to eight `virtio,mmio` transports.

Malformed descriptions stop boot with `boot: rejected=devices reason=`: multiple controllers, more than 1023 sources, transports without interrupts or registers, interrupts outside the controller's sources, or more than eight transports. Without an S-mode controller, boot continues with no devices.

A transport is registered only if its registers start on a page boundary, lie outside RAM and the user region, report the VirtIO-MMIO version 2 signature and have a nonzero model. Each registered device produces a `boot: device=` line with slot, type, model and interrupt.

| Slot | Device |
| --- | --- |
| 0 | Serial port |
| 1–8 | VirtIO transports in ascending address order |

## Device capability

| Call | Rule |
| --- | --- |
| `device_list(system, address, capacity)` | Requires `READ` on the system capability and a buffer of at least 144 bytes. Writes one 16-byte entry per present device and returns the entry count |
| `device_claim(system, slot)` | Requires `ADMIN` on the system capability. Returns a device handle with `READ`, `WRITE`, `ADMIN` and `DELEGATE` |

Each list entry contains four 32-bit integers: slot, type, model and state. Type 1 is serial and type 2 is VirtIO. The model is the VirtIO device ID: 1 for network, 2 for block and 4 for entropy.

A device has one owner at a time. `device_claim` returns `BAD_STATE` while any device capability exists in any process, and `INVALID_ARGUMENT` for an empty slot. The capability can be derived and granted normally; `init` claims each device and grants its driver only `READ`, `WRITE` and `ADMIN`.

| Right | Permits |
| --- | --- |
| `READ` | `device_config`, `device_wait`, `serial_read` |
| `WRITE` | `device_submit`, `serial_write` |
| `ADMIN` | `device_open`, `device_reset` |

Calling a VirtIO operation on serial, or the reverse, returns `UNSUPPORTED`.

## VirtIO device states

| Value | State | Meaning |
| --- | --- | --- |
| 0 | `closed` | No session; may be opened |
| 1 | `ready` | Negotiated and accepting requests |
| 2 | `failed` | Protocol violation or device-requested reset; only `device_reset` can leave this state |
| 3 | `quarantined` | Reset was not acknowledged; unusable until the next boot |

The serial port always reports `ready`.

## Session

`device_open(device, features, session_address)` requires `ADMIN`. `features` may contain only bits 0–23, specific to the device type; any other bit returns `INVALID_ARGUMENT`.

The supervisor resets the device and negotiates: it requires `VIRTIO_F_VERSION_1`, accepts only requested features the device offers, checks that `FEATURES_OK` remains set and programs queues with 16 descriptors each. Queue 0 is mandatory. Queue 1 is programmed when offered, as with `virtio-net`, which uses one receive and one transmit queue. A device lacking version 1, rejecting features or offering a smaller queue is marked failed in its status register; the call returns `UNSUPPORTED`.

| Condition | Error |
| --- | --- |
| Another process owns the session, or state is not `closed` | `BAD_STATE` |
| Reset unacknowledged | `IO_ERROR`, and quarantine |
| Session block is not writable | `BAD_ADDRESS` |

The session block is 24 bytes: accepted features in 8, session generation in 8, queue size in 4 and programmed queue count in 4. Generation changes on every reset.

Only the session opener may use `device_config`, `device_submit` and `device_wait`. Another process holding the same capability receives `BAD_STATE`.

`device_config(device, offset, address, length)` requires `READ` and copies 1–256 configuration bytes. If configuration changes during the read, the supervisor retries up to four times, then returns `BAD_STATE` if it does not stabilize.

## Requests

`device_submit(device, request_address)` requires `WRITE`. A request is 104 bytes.

| Offset | Size | Field | Rule |
| --- | --- | --- | --- |
| 0 | 4 | `queue` | Session-programmed queue index: 0 or 1 |
| 4 | 4 | `segment_count` | 1–4 |
| 8 | 24 per segment | `segments` | Up to four |

A segment:

| Offset | Size | Field | Rule |
| --- | --- | --- | --- |
| 0 | 8 | `buffer` | Handle to a caller-owned buffer capability |
| 8 | 4 | `offset` | Start within the buffer |
| 12 | 4 | `length` | At least 1, not beyond the buffer end |
| 16 | 4 | `flags` | Bit 0: device writes this segment. Other bits zero |
| 20 | 4 | reserved | Zero |

Drivers name memory by handle and offset. They never supply or receive a physical address.

| Condition | Error |
| --- | --- |
| Handle is not a buffer in the process's table | `INVALID_HANDLE` |
| Buffer lacks `WRITE` for a device-write segment, or `READ` otherwise | `ACCESS_DENIED` |
| Range outside buffer, zero length, unknown flag or nonzero reserved field | `INVALID_ARGUMENT` |
| Read segment after a write segment | `INVALID_ARGUMENT` |
| Queue not programmed in the session | `INVALID_ARGUMENT` |
| Four requests in the queue, counting in-flight and undelivered completions | `LIMIT_EXCEEDED` |
| Device not `ready` | `BAD_STATE` |

An accepted request pins every buffer, writes descriptors into a supervisor-owned queue unmapped from all processes and notifies the device. It returns a positive token never reused on that device. A rejected request pins nothing.

`device_wait(device, completion_address, deadline)` requires `READ` and delivers a 16-byte completion: token in 8 bytes and device-written byte count in 4. Both queues use the same call; drivers distinguish completions by token. It returns 1. Without a ready completion, it waits until the deadline and returns `TIMED_OUT`. If the device is not `ready` and nothing remains to deliver, it returns `BAD_STATE`.

## Validating device responses

On each transport interrupt the supervisor reads the completion queue. It never rereads the descriptor table: each request chain is held in private supervisor memory, so device modifications cannot change what is released.

The device becomes `failed`, with `device: slot=N state=failed reason=`, for:

| Reason | Condition |
| --- | --- |
| `used-ring-violation` | More completions than in-flight requests; completion not naming an in-flight request head, including duplicates and out-of-range indices; written bytes above the request's allowance |
| `device-needs-reset` | Device set its reset bit in the status register |

Valid completions preceding the violation remain deliverable. Buffers of incomplete requests stay pinned.

## Reset and quarantine

`device_reset(device)` requires `ADMIN`. The supervisor writes zero to status and waits a bounded number of reads for acknowledgment.

- Acknowledged: unpin all in-flight request buffers, discard undelivered completions, zero the queue, increment generation and return to `closed` without a session owner.
- Unacknowledged: enter `quarantined`, print `device: slot=N state=quarantined reason=reset-not-acknowledged` and return `IO_ERROR`. Buffers remain pinned and their frames cannot be reused. `device_open` and `device_reset` subsequently return `BAD_STATE`.

The same reset occurs automatically when the session owner loses its last device capability by closing it or terminating.

## Pinned memory

A pinned buffer may lose its owner. Its mappings disappear and it ceases to exist for processes, but its frames return only when the last request completes or the device confirms reset. Counters 17–19 in `processes.en.md` report in-flight requests, pinned buffers and quarantined devices.

## Serial port

| Call | Rule |
| --- | --- |
| `serial_write(device, address, length)` | Requires `WRITE`. At most 256 bytes, otherwise `MESSAGE_TOO_LARGE`. Returns bytes accepted immediately, possibly fewer than requested or zero. Does not wait |
| `serial_read(device, address, capacity, deadline)` | Requires `READ`. Capacity 1–256. Returns already-received bytes up to capacity, or waits for the first byte until the deadline, then returns `TIMED_OUT` |

Reception fills a 256-byte buffer in the interrupt handler. Bytes arriving when full are discarded and counted.

The emergency console does not use these calls. The supervisor writes diagnostics and panics directly through transmitter polling, with or without a driver.

## External interrupts

External interrupts are accepted only while a process runs in U-mode or the supervisor waits without a ready process. Handling services at most 16 sources at once, runs the native device handler, wakes its waiting process and completes the source in the controller. A source without a handler is disabled. No Python runs and no memory is allocated.

## Limits

| Limit | Value |
| --- | --- |
| Devices | 9: serial port and 8 transports |
| Queues per device | Up to 2, 16 descriptors each |
| In-flight requests plus undelivered completions | 4 per queue |
| Segments per request | 4 |
| Readable configuration space | 256 bytes |
| Serial transfer | 256 bytes per call |

Values are in `native/include/kernel/abi/devices.h` and `kernel_protocol.devices.layout`. The `devices` suite covers discovery, ownership, negotiation, validation, block requests, entropy, serial and driver termination with pending requests. `kernel-tool fault-test --suite device-reset` covers deadline-triggered reset, pinning until reset, termination with pending requests and device-reported failure. Hosted tests `virtio_queue_test.c`, `virtio_device_test.c` and `device_inventory_test.c` cover queues, sessions and discovery. `network`, `network-interop` and `network-faults` exercise both queues on QEMU `virtio-net`; the `device-reset` network-fault case resets it with receive requests in flight.
