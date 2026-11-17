# Handles

[Português](handles.md)

A handle identifies a table slot and that slot's generation. It is opaque to its recipient and has meaning only in the issuing table.

## Format

Unsigned 64-bit integer:

| Bits | Field | Rule |
| --- | --- | --- |
| 0–23 | `index` | Slot position, from 0 to table capacity minus 1 |
| 24–55 | `generation` | From 1 to `0xFFFFFFFF` |
| 56–63 | reserved | Zero |

`0` is the invalid handle. Since generations start at 1, no issued handle is zero.

## Slot lifecycle

1. The table starts with every slot free and generation 1.
2. `allocate` occupies a free slot and returns its current-generation handle. With no free slot it fails with `LIMIT_EXCEEDED`.
3. `resolve` accepts a handle only if the index exists, the slot is occupied, the generation matches and reserved bits are zero. Otherwise it returns `INVALID_HANDLE`.
4. `release` validates as `resolve` does, frees the slot and increments the generation.
5. If the generation was already at its maximum, the slot is retired: it never returns to the free list, and usable table capacity decreases by one.

After `release`, the old handle fails `resolve` forever, including after slot reuse.

Free-slot selection is LIFO: the last released slot is reused first. This is deterministic and part of the contract tested by the conformance corpus.

## Authority

A handle carries no authority outside the recipient process's table. Sending its integer in a payload does not transfer a capability. See ADR 0005.

The reference implementation is `kernel_protocol.identity`. Generation width is a table parameter so tests can exhaust the counter in few steps; the production format uses 32 bits.
