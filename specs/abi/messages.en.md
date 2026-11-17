# Messages

[Português](messages.md)

Every IPC message starts with a 24-byte header followed by its payload. Integers are unsigned and little-endian. The format is defined field by field: neither side serializes C structs or Python objects.

## Header

| Offset | Size | Field | Rule |
| --- | --- | --- | --- |
| 0 | 2 | `version` | `1` |
| 2 | 2 | `flags` | Only the bits below |
| 4 | 4 | `operation` | Service-protocol operation number |
| 8 | 4 | `payload_bytes` | 0–4096 |
| 12 | 4 | reserved | Zero |
| 16 | 8 | `correlation` | Chosen by caller; repeated in reply |

Flags:

| Bit | Name | Meaning |
| --- | --- | --- |
| 0 | `FLAG_REPLY` | Message replies to a call |
| 1 | `FLAG_ERROR` | Reply carries an error code; valid only with `FLAG_REPLY` |

## Receive validation

Receivers validate in this order, stopping at the first error:

1. Fewer than 24 bytes: `INVALID_ARGUMENT`.
2. `version` other than 1: `UNSUPPORTED`.
3. Unknown flag bit, `FLAG_ERROR` without `FLAG_REPLY`, or nonzero reserved field: `INVALID_ARGUMENT`.
4. `payload_bytes` above 4096: `MESSAGE_TOO_LARGE`.
5. Total length different from `24 + payload_bytes`: `INVALID_ARGUMENT`.

Extra bytes are rejected, not ignored.

## Outside the header

Sender identity and transferred capabilities do not travel in the payload. The supervisor delivers them as metadata. A handle in the payload is only a number.

`correlation` associates a reply with its call; it does not prove exactly-once execution. Side-effecting operations define their own identifiers or idempotency in the service protocol.

## Endpoints

`endpoint_create` returns an endpoint owned by its creator. Only the owner receives: another process's `ipc_receive` returns `ACCESS_DENIED`, and `RECEIVE` is neither derived nor transferred.

An endpoint queues up to 64 messages in arrival order. Pending-message bytes count against the sender's 1 MiB IPC quota and the 16 MiB global budget. Exceeding either returns `LIMIT_EXCEEDED` without enqueueing anything.

## Sending

`ipc_send` requires `SEND`. The supervisor copies and validates the message and rejects `FLAG_REPLY`. Rejected messages never enter the queue.

When the queue is full, the sender blocks until space becomes available or the deadline expires. A full-queue owner sending to itself receives `WOULD_DEADLOCK` instead. An endpoint without an owner returns `PEER_CLOSED`; owner death wakes blocked senders with the same error.

Transferred capabilities follow `capabilities.en.md`. If transfer is rejected, the message is not enqueued.

## Receiving

`ipc_receive` requires `RECEIVE`. An empty queue blocks until a message arrives or the deadline expires. The message is copied to the supplied buffer and the supervisor writes 32 bytes of metadata:

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 8 | Sender identity |
| 8 | 8 | Transferred capability handle, or 0 |
| 16 | 8 | Reply capability handle, or 0 for messages not sent by `ipc_call` |
| 24 | 8 | Message length |

A buffer smaller than the message returns `MESSAGE_TOO_LARGE`. An unwritable buffer or metadata range returns `BAD_ADDRESS`. In both cases the message remains queued.

## Call and reply

`ipc_call` sends and blocks for a reply. Its control block is 24 bytes:

| Offset | Size | Field | Direction |
| --- | --- | --- | --- |
| 0 | 8 | Deadline | Input |
| 8 | 8 | Capability to transfer, or 0 | Input |
| 16 | 8 | Capability received with reply, or 0 | Output |

The server receives a single-use reply capability. `ipc_reply` requires `FLAG_REPLY` and the call's `correlation`; otherwise it returns `INVALID_ARGUMENT` and leaves the call pending. A reply exceeding the caller's buffer returns `MESSAGE_TOO_LARGE`. A valid reply is copied directly into caller memory and consumes the reply capability.

Every call ends in one of these ways:

| Situation | Caller receives | Effect |
| --- | --- | --- |
| Reply delivered | Reply length | Reply capability consumed |
| Deadline expires | `TIMED_OUT` | Queued call removed; later server reply returns `PEER_CLOSED` |
| Caller targeted by `process_interrupt` | `CANCELLED` | Same as deadline |
| Server dies or closes endpoint | `PEER_CLOSED` | Nothing else is delivered |
| Call to own endpoint or to a process waiting for the caller | `WOULD_DEADLOCK` | Nothing enqueued |
| Wait chain exceeds 8 processes | `LIMIT_EXCEEDED` | Nothing enqueued |

When reply and deadline race, both sides see the same outcome: either delivery succeeds and `ipc_reply` returns 0, or the caller receives `TIMED_OUT` and `ipc_reply` returns `PEER_CLOSED`.

The reference format implementation is `kernel_protocol.wire.message`. Metadata and control-block offsets are in `native/include/kernel/abi/ipc.h`. The `ipc` suite covers malformed messages, delivery, transfer, queue limits, peer death, cancellation, deadlines, correlation, endpoint ownership and deadlock rejection.
