# Trusted computing base

[Português](trusted-computing-base.md)

The components that must be correct for the kernel's guarantees to hold. A defect in any item below can violate isolation or integrity.

## At runtime

| Component | Source | Role |
| --- | --- | --- |
| OpenSBI 1.5.1 `fw_dynamic` | Binary from the hash-pinned xPack QEMU `9.2.4-1` package | M-mode, PMP, SBI interface and handling of non-delegated traps |
| Native supervisor | `native/` | Boot, traps, DTB and user-image validation, frame allocator and Sv39 page tables, context switching, timer, object and capability tables, IPC, buffers, process lifecycle, syscall validation and emergency console. For devices: DTB discovery, interrupt controller, VirtIO-MMIO transport and request queues, buffer pinning, reset, quarantine and serial-port bytes |
| Runtime port, supervisor profile | `ports/micropython/shared/` and `ports/micropython/supervisor/` | Interpreter lifecycle, GC roots, `_supervisor` bindings and fatal exception handling |
| MicroPython 1.29.0 core | `py/`, `shared/runtime/gchelper_native.c`, `shared/runtime/gchelper_rv64i.s`, `shared/libc/string0.c` from the pinned tarball | VM, collector, objects, memory and string functions |
| GCC 15.2.0 `libgcc` | `rv64imac_zaamo_zalrsc/lp64` multilib of the pinned compiler | Compiler-emitted support routines; linked members appear in the `kernel-tool verify-artifacts` report |
| Frozen policies | `src/kernel_core/` and `src/kernel_protocol/` | Resource-profile validation, process admission and quotas, scheduling and supervision |

The runtime's `user` profile, the `kernel_client` library, `kernel_drivers` drivers and `kernel_services` services are not part of the system TCB. They run in U-mode and the supervisor validates every call they make. Services have limited authority but are trusted for the resources they manage: the file service for its mounted volumes and each driver for its assigned device. `init` starts with the system capability and is responsible for creating the other processes and handing each device to its driver.

The volume format and recovery code in `kernel_services.filesystem` decide what survives a failure. This code does not protect process isolation, but the entire `fsync` guarantee depends on it.

## At build time

GCC, binutils, `mpy-cross`, MicroPython tools and `kernel-tool` produce the image. Tampering with any of them compromises the result. Versions and hashes are pinned in `toolchain.lock.toml` and `uv.lock`, and hashes are checked before use.

QEMU plays the role of hardware. It is not part of the guest TCB, but every test result depends on it. Durability tests also depend on QEMU's block layer: `blkdebug` injects the flush error and `blklogwrites` records the order of writes and flushes that `kernel-tool` replays.

## Growing the TCB

A new component enters this list only if ADR 0002 justifies its native implementation or if it is a policy the supervisor must execute. Optional MicroPython modules stay disabled until a requirement calls for them. Every new `_supervisor` binding is recorded in ADR 0002.
