# Boot image

[Português](boot-image.md)

The boot image is a read-only file collection written to `boot.img` by `kernel-tool build` and presented by QEMU as the `kernel-boot` disk. The file service mounts it at `boot`. It has no directory records: each file stores its full path and directories are inferred from paths.

Integers are unsigned little-endian. Blocks are 4096 bytes and checksums are CRC-32.

## Contents

`config/boot/manifest.toml` lists files:

```toml
[[file]]
path = "system/license"
source = "LICENSE"
```

`source` names a repository file. Paths outside the repository, missing files and directories fail the build. Only `path` and `source` keys are accepted.

The build adds `system/release`, recording the system interface version and target runtime:

```
abi=1
runtime=micropython-1.29
```

## Layout

| Blocks | Contents |
| --- | --- |
| 0 | Header |
| 1 onward | File table |
| After the table | File contents in table order, each starting at a block boundary |

### Header

| Offset | Size | Field | Rule |
| --- | --- | --- | --- |
| 0 | 8 | `magic` | `KBOOTIMG` |
| 8 | 4 | `version` | 1 |
| 12 | 4 | `abi` | System interface version: 1 |
| 16 | 16 | `runtime` | Zero-padded runtime name and version |
| 32 | 4 | `entries` | File count, up to 64 |
| 36 | 4 | `table_bytes` | Table size |
| 40 | 4 | `table_checksum` | Table CRC-32 |
| 44 | 4 | `total_blocks` | Image blocks |
| 48 | 12 | reserved | Zero |
| 60 | 4 | `checksum` | CRC-32 of bytes 0–59 |

### Table

One entry per file, in strictly ascending path-byte order.

| Offset | Size | Field | Rule |
| --- | --- | --- | --- |
| 0 | 2 | `path_length` | 1–255 |
| 2 | 2 | reserved | Zero |
| 4 | 4 | `first_block` | First content block |
| 8 | 4 | `size` | File bytes, up to 262,144 |
| 12 | 4 | `checksum` | Content CRC-32 |
| 16 | `path_length` | `path` | `/`-separated names following persistent-volume name rules |

## Validation

Mounting reads the header and table and rejects the entire image if:

- Magic, header checksum or a reserved field is invalid: `CORRUPTED`.
- Format version, `abi` or `runtime` differs from what the running system expects: `UNSUPPORTED`. Expected runtime comes from guest `sys.implementation` and build-time `toolchain.lock.toml`.
- Image size exceeds the device or is smaller than its own table.
- The table checksum fails; it has over 64 entries, ends inside an entry, has trailing bytes, or contains invalid, duplicate or unordered paths.
- Files overlap, leave an unowned block or do not end at `total_blocks`.
- A path traverses through a file.

File contents are read and checksum-verified on first read. An invalid file returns `CORRUPTED` for that read; other files remain readable.

Every modification returns `READ_ONLY`. Service status reports a read-only mount with reason `verified`.

Format and validation are implemented in `src/kernel_services/filesystem/boot/layout.py` and `backends/boot.py`. The host assembles the image in `host/kernel_tool/storage/boot_image.py` using the same encoding functions.
