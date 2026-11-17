# User image

[Português](user-image.md)

The file format carrying U-mode programs. Firmware supplies it as a boot module in the `linux,initrd-start` to `linux,initrd-end` range of the DTB `/chosen` node.

The image contains the user MicroPython runtime and frozen Python modules. Every process is created from it; its program is the module named in the creation request. Contents are linked at virtual address `load_base`, starting with the header itself. There is no relocation.

## Header

72 bytes of unsigned little-endian integers:

| Offset | Size | Field | Rule |
| --- | --- | --- | --- |
| 0 | 4 | `magic` | Bytes `4B 55 49 4D`, ASCII `KUIM` |
| 4 | 4 | `version` | `2` |
| 8 | 8 | `load_base` | Profile user-region base |
| 16 | 8 | `file_bytes` | File size including header |
| 24 | 8 | `entry` | First instruction address |
| 32 | 8 | `text_bytes` | Code starting at `load_base` |
| 40 | 8 | `rodata_bytes` | Read-only data immediately after code |
| 48 | 8 | `data_bytes` | Writable data and BSS immediately after read-only data |
| 56 | 8 | `heap_bytes` | Default runtime heap when creation does not override it |
| 64 | 8 | `stack_bytes` | Stack |

## Address space

Each process receives these ranges, in order from `load_base`:

| Range | Permissions | Pages |
| --- | --- | --- |
| Code | Read and execute | Shared by all processes |
| Read-only data | Read | Shared by all processes |
| Data and BSS | Read and write | Private |
| Heap | Read and write | Private |
| 4096-byte guard page | None | Unmapped |
| Stack | Read and write | Private |

No page is simultaneously writable and executable. Private pages are zeroed before receiving contents. Outside these ranges and mapped buffers, access causes a page fault that terminates the process; this includes address zero, supervisor memory, free memory and device registers.

## Validation

The supervisor rejects the image with the following reasons:

| Reason | Condition |
| --- | --- |
| `truncated-header` | Module smaller than 72 bytes |
| `bad-magic` | Wrong `magic` |
| `unsupported-version` | `version` other than 2 |
| `segment-outside-region` | Wrong `load_base`, or code, data, heap, guard and stack exceed the region |
| `bad-segment` | Zero `text_bytes`, or `text_bytes`, `rodata_bytes` or `data_bytes` not a multiple of 4096 |
| `bad-reservation` | Zero or non-page-multiple `heap_bytes` or `stack_bytes` |
| `bad-file-size` | `file_bytes` below 72, above module size or above `text_bytes + rodata_bytes + data_bytes` |
| `bad-entry` | Odd `entry`, before the header end or beyond file-backed code |

Rejection prints `policy: rejected=boot-module reason=<reason>` and stops boot before any process exists.

A heap requested in `process_spawn` replaces `heap_bytes` and undergoes the same size calculation. Python policy applies the profile's per-process heap limit before creation starts.

The image link generates the header in `ports/micropython/user/image_header.S`. Offsets are in `native/include/kernel/abi/user_image.h`; the host reader is `host/kernel_tool/images/user_image.py`.
