# Capabilities

[Português](capabilities.md)

Every authority held by a process is a capability in its table: a supervisor object, a set of rights and a link to the capability from which it was derived. The process names it with a handle in the format described in `handles.en.md`. Decisions are recorded in ADR 0005.

## Rights

| Bit | Name | Permits |
| --- | --- | --- |
| `0x01` | `RIGHT_SEND` | Sending to an endpoint; replying with a reply capability |
| `0x02` | `RIGHT_RECEIVE` | Receiving from an endpoint |
| `0x04` | `RIGHT_READ` | Mapping a buffer read-only; waiting for a process; reading system counters and the device list; reading device configuration, completions and input; granting a buffer for a device-read segment |
| `0x08` | `RIGHT_WRITE` | Mapping a buffer writable; submitting requests and output to a device; granting a buffer for a device-write segment |
| `0x10` | `RIGHT_MAP` | Mapping a buffer |
| `0x20` | `RIGHT_DELEGATE` | Deriving, transferring or granting the capability |
| `0x40` | `RIGHT_ADMIN` | Creating processes and claiming devices through the system capability; killing or interrupting a process; opening and resetting a device |

## Objects

| Type | Value | Created by | Initial rights |
| --- | --- | --- | --- |
| System | 1 | Granted to `init` as its first handle | `ADMIN`, `READ`, `DELEGATE` |
| Process | 2 | `process_spawn`, in the creator's table | `READ`, `ADMIN`, `DELEGATE` |
| Endpoint | 3 | `endpoint_create` | `SEND`, `RECEIVE`, `DELEGATE` |
| Buffer | 4 | `buffer_create` | `READ`, `WRITE`, `MAP`, `DELEGATE` |
| Reply | 5 | Delivered to the server with a call | `SEND`, single-use |
| Device | 6 | `device_claim`, in the claimant's table | `READ`, `WRITE`, `ADMIN`, `DELEGATE` |

A process starts with only what its creator granted in the creation request. Global names, paths and process identifiers confer no authorization.

## Operations

| Call | Rule |
| --- | --- |
| `capability_derive(handle, rights)` | Creates a derived capability in the same table. Requires `DELEGATE` on the source, and requested rights must be a subset of its rights; otherwise `ACCESS_DENIED`. Empty rights or unknown bits return `INVALID_ARGUMENT`. The derived capability is one level deeper |
| `capability_inspect(handle)` | Returns type in bits 0–7, rights in bits 8–15 and depth starting at bit 16 |
| `capability_revoke(handle)` | Invalidates all descendants in every process and returns their count. The named capability and its siblings remain valid |
| `capability_close(handle)` | Removes the capability from the table. Descendants remain valid and depend on the removed capability's parent |

A closed or revoked handle never becomes valid again, even when its slot is reused: the slot receives a different generation.

## Transfer

A capability reaches another process in two ways. Both install a derived capability in the destination table:

- As a grant in `process_spawn`. The child finds it in the startup block's handle list, in request order.
- As a transferred capability in `ipc_send`, `ipc_call` or `ipc_reply`. The new handle arrives in message metadata, never in the payload.

Transfer requires `DELEGATE`. `RECEIVE` is never derived, granted or transferred: only the endpoint creator receives from it. Reply capabilities cannot be transferred.

Placing a handle integer in a payload transfers nothing. Its number has meaning only in the table of the process that received it from the supervisor.

## Object lifetime

An object exists while any capability references it. When an endpoint owner dies or closes its `RECEIVE` capability, the endpoint closes: pending messages are discarded, senders receive `PEER_CLOSED`, and reply waiters wake with the same error. Process termination closes every capability in its table.

Devices exist from boot and are never destroyed. Closing the last device capability makes it available to another claimant; if the closing process owned its session, the supervisor first resets it as described in `devices.en.md`.

## Limits

| Limit | Value | When reached |
| --- | --- | --- |
| Capabilities per process | 128 | `LIMIT_EXCEEDED`, no partial effect |
| Derivation depth | 16 | `LIMIT_EXCEEDED` |
| Grants per creation request | 8 | `INVALID_ARGUMENT` |

Values are defined in `native/include/kernel/abi/rights.h` and `kernel_protocol.identity.rights`. The `capabilities` suite of `kernel-tool test` covers stale and forged handles, attenuated delegation, descendant revocation, quotas, absence of ambient authority and capability-bound mappings.
