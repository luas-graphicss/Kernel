# Resource profile

[Português](resource-profile.md)

A profile describes the machine, memory layout and limits used to build and test an image. Profiles are TOML files in `config/profiles/`. The only profile is `qemu-riscv64`.

`kernel-tool` reads the profile, passes layout and limits to the native build and assembles the QEMU command line. The supervisor gives compiled limits to Python policy, which checks them against the DTB.

## `[machine]`

| Field | Meaning |
| --- | --- |
| `emulator` | Emulator binary name in the pinned package |
| `machine` | `-machine` value |
| `cpu` | `-cpu` value |
| `harts` | `-smp` value |
| `memory_mib` | Machine RAM in MiB |
| `accelerator` | `-accel` value |
| `globals` | List of `-global` values |
| `firmware` | Firmware component name in `toolchain.lock.toml` |

## `[layout]`

Addresses and sizes are in bytes.

| Field | Meaning |
| --- | --- |
| `kernel_base` | Kernel link address |
| `user_region_base` | Virtual start address of every process image |
| `user_region_bytes` | Virtual range available to a process image, heap, guard page and stack |
| `supervisor_stack_bytes` | Supervisor stack |
| `emergency_stack_bytes` | Stack used only by fatal-trap reporting |
| `user_heap_bytes` | User-image runtime heap |
| `user_stack_bytes` | User-image stack |

## `[limits]`

These are limits to demonstrate, not measured results. Changing one requires repeating affected tests.

| Field | Value | At the limit |
| --- | --- | --- |
| `memory_bytes` | 256 MiB | Boot rejected if the DTB describes less |
| `processes` | 16 | Capacity error, no partial creation |
| `supervisor_heap_bytes` | 8 MiB | Controlled handling; corruption requires panic |
| `process_heap_bytes` | 4 MiB | Admission rejected; no automatic growth |
| `capabilities_per_process` | 128 | Atomic grant failure |
| `delegation_depth` | 16 | New derivation rejected |
| `ipc_inline_payload_bytes` | 4 KiB | Use a granted buffer or reject |
| `endpoint_messages` | 64 | Backpressure and deadline |
| `ipc_pending_bytes_per_process` | 1 MiB | Enforced alongside the global limit |
| `ipc_pending_bytes_global` | 16 MiB | Enforced alongside the per-process limit |

Quotas aggregate across all resources of the same process. Splitting a request across messages does not bypass a limit.

## `[deadlines]`

| Field | Meaning |
| --- | --- |
| `boot_seconds` | Host timeout before a boot scenario counts as failed |
| `selftest_seconds` | Runtime self-test timeout |
| `soak_seconds` | Timeout for the 10,000 process and IPC cycle scenario |
