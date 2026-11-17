# ADR 0006: Persistence

[Português](0006-persistence.md)

Status: accepted.

## Context

The system needs to store files and survive a power loss without a native POSIX stack. Deciding the durability contract after the format leads to an `fsync` that promises what the disk does not deliver.

## Decision

There are three backends behind the VFS service:

- Boot image, read-only.
- Temporary filesystem, with no promise of persistence.
- Persistent volume in a versioned format of its own, implemented in Python, with copy-on-write data and metadata.

The persistent volume follows this contract:

1. Blocks of 4096 bytes. Metadata has a type, a generation and a validated length, and every pointer carries the CRC-32 of the block it points to. Trees have bounded depth and fan-out.
2. Two alternating superblocks point to the committed root, each with its generation.
3. A transaction writes new data and metadata without overwriting what the protected roots still reach.
4. The new root is only published after the transport confirms ordering and flush of the blocks.
5. `fsync` only returns success after the flush that follows the publication of the root.
6. Recovery picks the consistent root with the highest generation and validates what it reaches.
7. The volume does not store a free-block map. Mounting rebuilds it from the roots, and a released block is only reused after the root that reached it ceases to exist.

The commit is of the whole volume, not of one file. `fsync` on any file publishes everything that changed in the mount.

An accepted `write` does not mean durability, and `close` does not replace `fsync`. A full disk, a wrong checksum or an unknown format produce an error or a read-only mount. The system never formats a volume in order to boot.

Symlinks and hard links stay out of version 1.0.

The format is in `specs/filesystem/volume-format.en.md`, the boot image in `specs/filesystem/boot-image.en.md` and the service in `specs/filesystem/file-service.en.md`. The code is in `src/kernel_services/filesystem/` and runs the same in the guest and in `kernel-tool`, which uses it to create, verify and inspect images.

## Consequences

The filesystem is a large piece of work, and the proof of consistency after a failure blocks its delivery. A checksum detects corruption, but does not authenticate the disk against deliberate tampering.

Since the commit is of the whole volume, one `fsync` costs the rewrite of every directory changed since the previous commit, from the leaf to the root. A directory fits in one block and a file has one index level, which limits a directory to 4080 bytes of entries and a file to 2,084,864 bytes.

The image of the user runtime is still loaded by QEMU in the range the DTB describes in `/chosen`. The boot image is something else: a read-only disk, mounted by the file service after the drivers start.

## Assumptions to confirm

- One index level and one block per directory are enough for version 1.0. The index already has a level field, today always zero.
- The cost of rewriting the tree up to the root on each `fsync` fits the deadlines of the clients. It has not been measured with deep trees yet.
- The contract holds on a physical disk. It was exercised on the `virtio-blk` of QEMU, with a flush error injected by `blkdebug` and with the write log of `blklogwrites`.

## Resolved assumptions

- The `virtio-blk` of the pinned QEMU accepts flush and allows the failure to be injected. The `flush-failure` scenario and the `flush-trace-replay` stage depend on that.
- Block of 4096 bytes and CRC-32.
- Orphan blocks need no recovery: with no map written, they are already free at the next mount.
