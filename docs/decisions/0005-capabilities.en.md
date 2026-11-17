# ADR 0005: Capabilities and generational identity

[Português](0005-capabilities.md)

Status: accepted.

## Context

Ambient authority, in which a process can do everything its user can, prevents minimal delegation and makes it hard to audit what a service reaches. The kernel also needs identifiers that do not become valid again after the object has died.

## Decision

Every authority is a capability: object, generation, rights and delegation link. Rights name concrete operations, such as send, receive, read, write, map, delegate and administer.

A process references a capability by a 64-bit handle, local to its own table:

| Bits | Field |
| --- | --- |
| 0 to 23 | Slot index |
| 24 to 55 | Generation, starting at 1 |
| 56 to 63 | Reserved, always zero |

The value zero is never a valid handle. Releasing a slot increases the generation; when the counter reaches the maximum, the slot is retired instead of reused. An old handle does not resolve again.

Authority rules:

- The supervisor validates the capability in every operation, even when the caller uses the official client library.
- Delegating only reduces rights. The maximum delegation depth is 16.
- Copying the integer of a handle to another process transfers nothing. The transfer is a native operation that installs the capability in the table of the recipient.
- The identity of the sender comes from metadata filled in by the supervisor, never from a field of the payload.
- Each process has at most 128 capabilities. `init` grants only what the manifest of the service declares.

The encoding and the model of the table are in `src/kernel_protocol/identity/`, the format in `specs/abi/handles.en.md` and the operations in `specs/abi/capabilities.en.md`. The table the supervisor enforces is native, in `native/supervisor/capabilities/` and `native/supervisor/objects/`.

## Consequences

A service does not act as a proxy: it authorizes the operation on the resource with the capability the client presented.

Every syscall that receives a handle resolves it in the table of the caller and checks the type of the object and the rights. The right to receive from an endpoint is neither derived nor transferred: only whoever created the endpoint receives from it.

## Assumptions to confirm

- The cost of revoking fits in one syscall. Revocation marks the descendants and then scans the capability registry to remove the marked ones; that cost has not been measured yet.
- 24 bits of index and 32 of generation are enough for the expected lifetime of a slot.
