# Persistent volume format

[Português](volume-format.md)

Format version 1. A volume is a sequence of 4096-byte blocks on a block device. Data and metadata are copy-on-write: transactions never overwrite blocks reachable from a protected root. Decisions are in ADR 0006; implementation is in `src/kernel_services/filesystem/`.

Integers are unsigned little-endian. All checksums use `zlib` CRC-32.

## Geometry

| Item | Value |
| --- | --- |
| Block | 4096 bytes |
| Blocks 0 and 1 | Superblock slots |
| Block 2 onward | Tree: directories, file indices and data |
| Minimum volume | 8 blocks |
| Maximum volume | 65,536 blocks, 256 MiB |

Creation uses only the first 65,536 blocks of a larger device. A superblock declaring more blocks than its device contains is rejected.

## Superblock

The superblock occupies its block's first 64 bytes. The remainder is zero.

| Offset | Size | Field | Rule |
| --- | --- | --- | --- |
| 0 | 8 | `magic` | `KVOLSUPR` |
| 8 | 4 | `version` | 1 |
| 12 | 4 | `block_bytes` | 4096 |
| 16 | 4 | `total_blocks` | 8–65,536, not above device size |
| 20 | 4 | reserved | Zero |
| 24 | 8 | `generation` | Starts at 1; remainder modulo 2 selects the slot |
| 32 | 8 | `next_node` | Next node number, greater than 1 |
| 40 | 4 | `root_block` | Root-directory block, from 2 to `total_blocks - 1` |
| 44 | 4 | `root_checksum` | Root-directory block CRC-32 |
| 48 | 8 | `volume` | Identifier chosen on creation |
| 56 | 4 | reserved | Zero |
| 60 | 4 | `checksum` | CRC-32 of bytes 0–59 |

Generation 1 uses slot 1, generation 2 uses slot 0, and so on. Publishing the next generation never overwrites the current superblock.

Slot reads validate `magic`, then `version` and `block_bytes`, then checksum, then remaining fields. Different version or block size returns `UNSUPPORTED` before checksum validation because another format may calculate checksums differently. Other failures return `CORRUPTED`.

## Metadata blocks

Directories and file indices start with a 16-byte header.

| Offset | Size | Field | Rule |
| --- | --- | --- | --- |
| 0 | 4 | `magic` | `KDIR` for directories, `KIDX` for file indices |
| 4 | 4 | `payload_bytes` | Up to 4080 |
| 8 | 8 | `generation` | Generation of the commit that wrote the block |
| 16 | `payload_bytes` | payload | Type-specific content |

Bytes after the payload are zero. Generation is at least 1 and no greater than its referrer's: the superblock for the root, or the parent directory otherwise.

Metadata blocks do not store their own checksum. Their whole-block CRC-32 is stored in the incoming pointer. Replacing a block requires rewriting every ancestor through the superblock.

## Directory

The payload is a sequence of entries in strictly ascending name-byte order. Each directory fits in one block.

| Offset | Size | Field | Rule |
| --- | --- | --- | --- |
| 0 | 1 | `kind` | 1 for file, 2 for directory |
| 1 | 1 | `name_length` | 1–255 |
| 2 | 2 | reserved | Zero |
| 4 | 4 | `block` | Child directory or file-index block; zero for empty files |
| 8 | 4 | `checksum` | Target-block CRC-32; zero without a block |
| 12 | 8 | `node` | Unique volume node number, greater than 1 and below `next_node` |
| 20 | 8 | `size` | File bytes, up to 2,084,864; zero for directories |
| 28 | `name_length` | `name` | Name |

Names are valid UTF-8 without zero bytes or `/`. `.` and `..` are not names. Root has node number 1 and appears in no entry. Node numbers are never reused.

## File

Empty files have no block. Others have an index block whose payload is:

| Offset | Size | Field | Rule |
| --- | --- | --- | --- |
| 0 | 1 | `level` | Zero: pointers target data blocks |
| 1 | 7 | reserved | Zero |
| 8 | 8 per pointer | pointers | Block number in 4 bytes and block CRC-32 in 4 |

The index contains exactly one pointer per 4096 bytes of file size, rounded up. Block zero denotes a hole: it reads as zeros, consumes no space and has checksum zero. Data blocks contain 4096 file bytes without a header. Bytes after EOF in the final block are zero.

## Limits

| Limit | Value | When reached |
| --- | --- | --- |
| Name | 255 bytes | `INVALID_ARGUMENT` |
| Directory entries | 4080 bytes: 28 fixed bytes plus name per entry | `LIMIT_EXCEEDED` |
| Depth | 32 directory levels including root | `LIMIT_EXCEEDED` |
| File | 2,084,864 bytes, 509 data blocks | `LIMIT_EXCEEDED` |
| Space | Free blocks minus reserve | `NO_SPACE` |

The format has no symbolic or hard links.

## Valid-tree guarantees

Validation follows everything reachable from a superblock. It returns `CORRUPTED` for:

- Pointers outside the tree-block range.
- Blocks referenced twice, including directory cycles.
- Duplicate, root or never-assigned node numbers.
- More than 32 directory levels.
- Wrong block type, checksum mismatch, oversized payload or nonzero trailing bytes.
- Block generation above its referrer's generation.
- Truncated entries, invalid or unordered names, unknown types or impossible sizes.
- An index not covering file size, or a hole with a checksum.

The file service validates all metadata at mount and each data-block checksum on read. `kernel-tool verify-filesystem` also validates all data blocks.

## Transaction and commit

Changes accumulate in memory. File writes go directly to free device blocks. Blocks allocated by the current transaction may be rewritten in place; blocks reachable from a published root may not.

Committing generation `G + 1`:

1. Write changed file indices and directories to free blocks, deepest first through the root, all with generation `G + 1`.
2. Flush the device.
3. Write generation `G + 1`'s superblock into its slot.
4. Flush the device.
5. Reply to the requester.

A commit publishes every volume change since the previous commit. There are no per-file commits.

| Failure | Requester result | Device state |
| --- | --- | --- |
| Steps 1 or 2 | `IO_ERROR` | Generation `G` |
| Steps 3 or 4 | `UNKNOWN_OUTCOME` | Generation `G` or `G + 1` |

Either failure marks the volume failed; every operation returns `IO_ERROR` until remount. The next mount decides from device contents.

## Crash points

The failure model is power loss: any combination of writes not followed by a flush may disappear, and one may be torn. For a commit from `G` to `G + 1`:

| Crash point | Recovered generation |
| --- | --- |
| Before tree flush, with any subset of writes retained | `G`; only blocks free in `G` were modified |
| After tree flush, before superblock | `G` |
| During superblock write | `G` if lost or torn, `G + 1` if complete |
| After final flush | `G + 1` |

No point mounts a mixture, and an acknowledged generation remains recoverable.

`kernel-tool fault-test --suite storage-crash` exercises three stages recorded in `reports/storage-crash.json`:

| Stage | Behavior |
| --- | --- |
| `crash-matrix` | Eleven minimal transactions, crashing after each device event. Up to four volatile writes, every loss combination is tested; above that, prefixes, each write alone, each omitted write and each torn write. Transactions: create file, append, overwrite a range, truncate, extend, create directory, rename, replace by rename, move directory entries, remove file and remove directory |
| `crash-sequences` | Generated sequences of 24 operations with 8 crashes each. Defaults to 1000 sequences from seed 1; `--sequences` and `--seed` override these, and reports retain seeds |
| `flush-trace-replay` | Reads QEMU's write/flush log while the guest performs seven transactions, checks that each superblock lies between two flushes and replays crashes against that log |

Every image must recover read-write at a committed generation no older than the last acknowledgment, with the same tree digest as that generation.

## Allocation and reuse

No free-block map is stored. Mounting reconstructs it by traversing the selected root.

- A block released by the transaction producing `G + 1` remains reachable from `G`. It becomes free only after `G + 2` is published and `G`'s superblock disappears.
- With two valid superblocks, blocks reachable only from the older root remain protected by the same rule.
- Blocks allocated and freed in the same transaction become free immediately.
- Interrupted-transaction blocks are reachable from no root and are already free at the next mount, without scanning or repair.

The reserve is `total_blocks / 8`, capped at 34 blocks, plus one per metadata node with pending changes. Space-consuming operations return `NO_SPACE` before starting if they cannot fit outside the reserve. Space-releasing operations, including removal, shrinking and replacing by rename, may use it. Writes may be partial: they return accepted bytes or `NO_SPACE` if none were accepted.

When space is lacking and blocks await the next generation, the volume performs two commits to reclaim them and retries the operation once.

## Mounting and recovery

1. Devices smaller than 8 blocks return `CORRUPTED`.
2. Read both slots. A superblock with an unknown version or block size rejects the whole volume with `UNSUPPORTED`, even if the other slot is readable: the unknown slot may represent newer state.
3. No valid superblocks: `CORRUPTED`.
4. Try valid superblocks newest first. Choose the first whose tree validates. If none does, return `CORRUPTED`.
5. Select mount mode from the table.

| Situation | Mode | Reason |
| --- | --- | --- |
| Consecutive valid superblocks, newest tree valid | Read-write | `clean` |
| Same, but previous tree invalid | Read-write | `previous-root-damaged` |
| Only one superblock, generation 1 | Read-write | `clean` |
| Only one superblock, another generation | Read-write | `recovered` |
| Newest tree invalid, previous mounted | Read-only | `newest-root-damaged` |
| Nonconsecutive superblock generations | Read-only | `generation-gap` |
| Read-only device | Read-only | `device-read-only` |
| Device without flush | Read-only | `device-without-flush` |

Read-only volumes reject all modifications with `READ_ONLY`. The system never creates, formats or repairs a volume to mount it. Blank devices appear as unavailable mounts with an error; boot proceeds without them.

Without flush, steps 2 and 4 provide no guarantee, so the volume rejects writes.

## Digest

Tools and tests compare tree digests: CRC-32 chained over each entry's path, type and size, followed by file contents. It depends on stored content, not block placement or commit count.

## Corpus

`tests/faults/storage/` contains 21 images with expected verdicts in `manifest.toml`: valid volumes, single-superblock volumes, incorrect checksums or generations, truncation, unknown version or block size, multiply-referenced blocks, directory cycles, out-of-range pointers, wrong types, duplicate node numbers and blocks newer than their root. `kernel-tool verify-filesystem --corpus tests/faults/storage` checks them all; `kernel-tool build-corpus` regenerates them from `host/kernel_tool/corpus/recipes.py`.
