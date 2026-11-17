# Privileged boundary review

[Português](privileged-boundary-review.md)

Review of the code that runs in S-mode and decides what a process may do. It was performed on November 17, 2026, on the 1.0.0rc1 release candidate tree, by the author of the qualification tools. This is not an independent audit.

## Method

Each file below was read in full or in the indicated section, looking for process-provided values used as indices, lengths or addresses without validation; size additions or multiplications that could overflow; access to user memory without validation; kernel state reachable through a stale handle; and memory returned to the allocator while a device can still reach it.

The review relies on three automated checks that cover what reading alone cannot:

- Hosted native tests in `tests/native/`, under AddressSanitizer and UndefinedBehaviorSanitizer.
- Native fuzzing targets in `tests/fuzz/native/`, with the same sanitizers, for the DTB, user image, message header and process creation request.
- Adversarial QEMU suites: `memory`, `capabilities`, `ipc`, `devices` and `device-reset`.

## Reviewed code

| Area | Files | What was checked |
| --- | --- | --- |
| Traps | `native/arch/riscv64/traps/trap_vector.S`, `trap.c`, `native/arch/riscv64/context/user_context.S` | A supervisor trap uses the emergency stack and ends in a panic with a diagnostic, without depending on the failed `sp`. A user trap saves integer registers, floating-point registers and trap state in the process frame, which resides in kernel memory. The `sstatus` used to enter U-mode is assembled without `SPP`, `SUM` or `MXR` |
| Syscall dispatch | `native/supervisor/processes/syscall.c`, `native/include/kernel/abi/syscalls.h` | A number outside the table returns `UNSUPPORTED`. All 31 numbers have handlers, with no gaps. `debug_write` bounds the length before copying to the stack |
| User memory | `native/supervisor/memory/address_space.c`, `range.c` | Ranges are checked against the process region without adding address and length. Copies walk the process page table one page at a time and require the operation's permissions. The supervisor never dereferences a user pointer |
| Buffers and mappings | `native/supervisor/memory/buffer.c`, `native/supervisor/processes/syscall_memory.c` | Sizes are bounded and charged to the quota. Memory is zeroed on allocation. Mapping is allowed only in the process window, with the capability and requested rights |
| DMA | `native/supervisor/processes/syscall_device.c`, `native/supervisor/devices/virtio/device.c`, sections of `queue.c` | A segment names a buffer by capability, with read or write rights according to the direction and an offset checked against the buffer size. The supervisor calculates the physical address. The buffer remains pinned until completion or confirmed reset, and a destroyed buffer's frames return to the allocator only when unpinned. Device-provided indices and lengths are checked; an invalid value marks the device as failed |
| IPC | `native/supervisor/processes/syscall_ipc.c`, `native/supervisor/ipc/message.c` | Message size is bounded before copying. The header is validated field by field. A reply destination is checked again at delivery because its mapping may have changed while the process waited |
| Capabilities and handles | `capability_require` in `native/supervisor/objects/kernel_objects.c`, sections of `slot_table.c` | Every operation resolves the handle in the caller's space, checks the object type and requires the rights. The handle carries the slot generation, and reserved bits are rejected |
| Collector roots | `ports/micropython/shared/memory/collector.c`, `ports/micropython/supervisor/platform.c`, `ports/micropython/supervisor/bindings/` | Collection scans registers and the stack. Bindings do not retain Python objects in static C variables |
| Supervisor bindings | `ports/micropython/supervisor/bindings/processes.c`, `machine.c`, `module.c` | Only frozen policy calls them. `spawn_initial` validates the program name and its length; handles go through generation-checked lookup |

## Result

No isolation, size-arithmetic or ownership defect was found in the reviewed sections.

Observations that are not defects:

1. Several syscalls check that the destination is writable, perform the operation and then write the result without checking the write's return value. This is correct because the kernel is not preemptible and nothing can undo a mapping between validation and the write. More than one hart or S-mode preemption would require reviewing these sites.
2. `buffer_unpin` decrements its counter without checking whether it is already zero. Callers are balanced and the hosted tests pass under sanitizers. A check there would turn a future error into a panic rather than silent underflow.
3. The console does not serialize lines from different processes. This does not affect isolation and is described in `docs/operations/diagnostics.en.md`.

## Outside this review

- MicroPython, OpenSBI and QEMU are third-party code. Known advisories for each pinned version are recorded in `config/release/advisories.toml`.
- Python services and drivers run in U-mode and face the same barriers as any process.
- The frame allocator, page tables, process lifecycle and device registry were read only at the sites reached by the paths above. They have hosted tests and QEMU suites, but were not reviewed line by line.
- Side channels, hardware failures and multiple harts are outside the threat model.
