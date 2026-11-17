# Buffers

[Português](buffers.md)

A buffer is a physical memory range the supervisor grants to processes through capabilities. It carries data larger than a message payload without sharing Python objects between runtimes.

## Creation

`buffer_create(bytes)` reserves zeroed memory and returns a handle with `READ`, `WRITE`, `MAP` and `DELEGATE`. The size is rounded to a power-of-two number of 4096-byte pages and charged to the creator's memory quota.

| Condition | Error |
| --- | --- |
| Zero size | `INVALID_ARGUMENT` |
| More than 4 MiB | `LIMIT_EXCEEDED` |
| Process memory quota exhausted | `LIMIT_EXCEEDED` |
| No frames above the supervisor reserve | `OUT_OF_MEMORY` |

## Mapping

`buffer_map(handle, rights, description)` maps the buffer into the calling process. `rights` must be `READ` or `READ | WRITE`; any other value returns `INVALID_ARGUMENT`. The capability must have `MAP` and the requested rights. The supervisor chooses the address and writes a 16-byte description: address and length, 8 bytes each.

`buffer_unmap(address)` removes the mapping starting at that address. An address that is not a mapping returns `INVALID_ARGUMENT`.

## Ownership

The creator owns the buffer. Another process can reach it only through a derived capability with rights chosen by the owner. A reader with `READ | MAP` sees the same pages and cannot map them writable.

A mapping does not outlive the last capability that permits it:

- Revoking a capability removes mappings made through its descendants, including in other processes.
- Closing a weaker capability does not remove a mapping still permitted by another capability in the same process.
- When the owner dies, the buffer is destroyed and no process can map it again: `buffer_map` returns `PEER_CLOSED`.

A buffer submitted to a device request remains pinned until completion or a confirmed device reset. If its owner dies meanwhile, the buffer disappears for processes as usual, but its frames return to the allocator only when unpinned. With a quarantined device they do not return. See `devices.en.md`.

After a mapping disappears, accessing its page causes a page fault that terminates the process; a syscall pointing there returns `BAD_ADDRESS`. This also applies to an IPC reply targeting a mapping removed during the call.

The `memory` suite covers creation, limits, cross-process reads and writes, and mapping removal during a blocked call. The `capabilities` suite covers the relationship between mappings and capabilities.
