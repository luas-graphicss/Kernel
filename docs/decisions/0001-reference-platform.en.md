# ADR 0001: Reference platform

[Português](0001-reference-platform.md)

Status: accepted.

## Context

The kernel needs a single, reproducible target before any subsystem. A target with an explicit privilege model and stable devices lets boot, traps and the runtime be proven without depending on a specific board.

## Decision

The target of version 1.0 is 64-bit RISC-V, little-endian, profile RV64GC, on the QEMU `virt` machine with one hart.

| Dimension | Pinned value |
| --- | --- |
| Emulator | QEMU 9.2.4, xPack package `9.2.4-1`, TCG accelerator |
| Machine | `virt,aia=none,acpi=off`, with `virtio-mmio.force-legacy=false` |
| CPU | `rv64,h=off,v=off`, one hart |
| Firmware | OpenSBI 1.5.1 in M-mode, the `fw_dynamic` shipped in the QEMU package |
| Privileges | Kernel in S-mode, processes in U-mode |
| Memory | 256 MiB from the address described in the DTB |
| Console | NS16550 UART discovered in the DTB; SBI DBCN before the DTB is validated |

Versions, URLs and hashes are in `toolchain.lock.toml`. The executable profile is in `config/profiles/qemu-riscv64.toml`.

Device and memory addresses come from the validated DTB. The only fixed address in the code is the kernel link address, `0x80200000`, which is the entry point OpenSBI uses on this machine.

The native supervisor code is compiled for `rv64imac_zicsr_zifencei` with the `lp64` ABI and runs with `sstatus.FS` off. The only floating-point instructions of the kernel are in the entry to and the exit from U-mode, in Assembly, and they save and restore `f0` to `f31` and `fcsr` of the process.

## Consequences

Passing on QEMU does not qualify physical hardware. SMP and the vector and virtualization extensions stay out: `h=off` and `v=off` keep an application from depending on them by accident.

Sv39 with 4 KiB pages fits the budget of the profile: the `processes` suite keeps 16 processes alive at the same time, each with its own address space, and the frame reserve of the supervisor stays free.

With this firmware, the reason passed to `sbi_system_reset` does not reach the exit code of QEMU, because the shutdown goes through `syscon-poweroff`. The final state of the boot is the `kernel: status=` line on the serial port, evaluated together with the exit code of the emulator.

## Assumptions to confirm

- The user runtime moves to the `lp64d` ABI. The context switch already saves the FP registers and `fcsr`, and a process can execute floating-point instructions, but the two profiles of the runtime are still compiled without them.
- PLIC and VirtIO-MMIO are pinned in the profile, but no driver uses them yet.
