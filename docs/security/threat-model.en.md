# Threat model

[Português](threat-model.md)

What the kernel protects against, what is outside its scope and how each input boundary is bounded and tested. Applies to the `qemu-riscv64` profile.

## Assets

- Integrity of the native supervisor, supervisor interpreter and frozen policies.
- Process isolation: memory, capabilities and accounted resources.
- Persistent data and the `fsync` guarantee.
- Availability: CPU, memory, queues and the supervisor reserve.
- Build chain: toolchain, pinned sources and the resulting image.

## Actors

| Actor | Trust |
| --- | --- |
| U-mode application | None. It may be malicious or defective |
| U-mode service | Limited to its granted capabilities; responsible for the resources it manages |
| Profile device | Responses are untrusted and validated. It is assumed to access only memory named by descriptors |
| Network peer | None |
| Volume contents, boot image and DTB | Untrusted until validated |
| Operator | Trusted: selects the image, profile and boot arguments |

A compromised host, malicious firmware, malicious physical device, unmediated DMA and microarchitectural side channels are outside the model. Validating pointers in Python does not solve any of them.

## Input boundaries

Every boundary has limits, a defined error result and a negative test.

| Boundary | Limits | Error result | Evidence |
| --- | --- | --- | --- |
| Firmware-provided DTB | 64 KiB, version 17, ordered non-overlapping blocks, depth 8, names up to 255 bytes, 16 reserved ranges, one RAM range | `boot: device tree rejected reason=` and boot termination | `tests/native/device_tree_test.c` harness with truncation and mutations under ASan and UBSan; `device-tree-too-large` and `device-tree-without-memory` scenarios |
| User image in `/chosen` | 72-byte header, version 2, base equal to the user region, segments in multiples of 4096 bytes within the region and module, entry within file-backed code | `policy: rejected=boot-module reason=` and boot termination | `tests/native/user_image_test.c` harness; `incompatible-segment` scenario |
| Syscall arguments | Known number; handle resolved in the caller's table with type and rights checked; entire memory range mapped with the operation's permission; 256 bytes per `debug_write` | Negated error code in `a0`, no partial effect | `memory`, `capabilities` and `ipc` suites |
| Process creation request | 296 bytes, version 1, module name of 1–64 bytes, argument up to 64 bytes, at most 8 grants; policy chooses priority and quotas | Negated error code; no part of the new process remains | `processes` suite; `spawn-failures` scenario; `tests/conformance/test_spawn_request.py` |
| IPC message | 24-byte header, payload up to 4 KiB, 64 messages per endpoint, 1 MiB pending per sender and 16 MiB globally; one transferred capability per message | Negated error code to sender; rejected message does not enter the queue | `tests/native/message_test.c` harness; `ipc` suite; `tests/conformance/test_wire.py` |
| U-mode program | Every exception other than `ecall` terminates the process; timer interrupts only suspend it | `user: fault` report and `fault` reason for process waiters | `user-fault` scenario; `memory` suite |
| Boot arguments | 255 bytes. Policy reads `init=` with a valid module name and `trace=schedule`; the rest is ignored | Invalid name ends boot with `policy: rejected=init` | DTB harness; name rule in `tests/conformance/test_spawn_request.py` |
| DTB-described devices | One interrupt controller with at most 1023 sources, one serial port, eight VirtIO transports; interrupts within controller sources; registers in their own page outside RAM and the user region | `boot: rejected=devices reason=` and boot termination; unidentified transport stays out of the list | `tests/native/device_inventory_test.c` harness with mutations under ASan and UBSan; `devices` suite |
| Device request | 104 bytes, 1–4 segments; each names a process buffer by handle, with direction-specific rights and a range within the buffer; read segments before write segments; 4 requests in flight | Negated error code; no buffer remains pinned | `tests/native/virtio_device_test.c` harness; `descriptor-validation` case in `devices` |
| Device responses | Completion names an in-flight request head and writes no more than permitted; configuration read only when stable; bounded reset-confirmation reads | Device stopped with `device: slot=N state=failed reason=` or quarantined; memory stays pinned | `tests/native/virtio_queue_test.c` and `virtio_device_test.c`; `kernel-tool fault-test --suite device-reset` |
| Serial input | 256 received bytes waiting; lines up to 255 bytes; four pending lines; unsupported control bytes discarded | Overlong line rejected with `MESSAGE_TOO_LARGE`; queue drops reported as `console: dropped-lines=N`; serial-ring overflow counted natively but not reported to the console | `tests/conformance/test_console.py`; `services` scenario in `devices` |
| Service request | Exact per-operation format; administration only for the supervising process identified by the supervisor; unexpected capability closed | Error response; nothing changes | `service-authority` case in `devices`; `vfs` suite |
| Path | 1024 bytes, 32 components, names up to 255 bytes of valid UTF-8 without zero bytes; `..` cannot escape the namespace root | `ACCESS_DENIED`, `INVALID_ARGUMENT` or `LIMIT_EXCEEDED` before any volume lookup | `tests/conformance/test_namespace_paths.py`; `path-resolution` and `namespaces-and-rights` cases in `vfs` |
| Persistent volume | 8–65,536 blocks; complete tree validated on mount: pointers, checksums, generations, node numbers, depth 32, no block referenced twice | Unavailable with `CORRUPTED` or `UNSUPPORTED`, or read-only mount; never formatted | `kernel-tool verify-filesystem --corpus tests/faults/storage`, with 21 images; `tests/conformance/test_filesystem_format.py` and `test_filesystem_recovery.py`; `unformatted-device`, `unknown-format-version` and `damaged-newest-root` scenarios in `storage` |
| Boot image | Checksummed header and table; up to 64 files of at most 256 KiB; contiguous files with no trailing bytes; matching interface and runtime | Mount unavailable; an invalid file returns `CORRUPTED` on read | `tests/host/test_boot_image.py`; `boot-image` case in `vfs` |
| Network frame | Up to 1514 bytes; every header checked before use: lengths, checksums, sender, destination; IPv4 without options; 16 datagrams and 1 MiB in reassembly for 30 s; 32 neighbors; burst-limited ICMP replies and resets | Dropped and counted by rule; no socket or buffer retained | `tests/conformance/test_network_malformed.py`, `test_network_reassembly.py`, `test_network_link.py`; `malformed-traffic` case in `kernel-tool fault-test --suite network-faults`, with 31 specimens |
| Peer connections | 8 pending requests per listening socket; 96 connections; 16 KiB per direction and 16 out-of-order segments per connection; 1 MiB service buffer budget | Requests beyond backlog dropped and counted; writes that do not fit wait; out-of-window segments ignored | `tests/conformance/test_network_tcp.py`; `connection-flood` in `network-faults` and `slow-reader` in `network-interop` |
| Socket-service request | Session requires possession of service-issued access; per-access rights; handles valid only for the receiving process and service instance; 16 sockets per process, 64 total | `ACCESS_DENIED`, `INVALID_HANDLE` or `LIMIT_EXCEEDED`; nothing changes | `access-rights` and `socket-quota` cases in `network` |
| System configuration | 16,384 bytes, 256 lines, 32 sections, 16 keys per section; only numbers, strings and lists; known sections, keys, services and rights; acyclic dependencies; processes within profile limits | `system: configuration=rejected reason=` and boot termination, with no configured service started | `tests/conformance/test_configuration.py`; `configuration-missing`, `configuration-circular`, `configuration-excessive` and `configuration-inconsistent` scenarios in `supervision` |
| System-control request | Only manager-admitted processes identified by the supervisor, with configured rights; command up to 63 printable bytes; 8 pending waits | `ACCESS_DENIED`, `INVALID_ARGUMENT` or `LIMIT_EXCEEDED` | `tests/conformance/test_control_protocol.py`; `applications` suite with `authority.py` |
| Shell line | 255 bytes, 16 words, closed quotes; command from the table; decimal numbers within range | `shell: command=<name> status=failed error=` and the prompt returns | `tests/conformance/test_shell_words.py`; `applications` and `system-journey` suites |
| Application program | File up to 65,536 bytes, executed in its own process with policy-granted capabilities; bounded heap; no file imports | Process ends with status 1 and a diagnostic; other processes continue | `applications` suite: `failing.py`, `broken.txt`, `missing.py`, `hog.py`, `spin.py` |

## Testable invariants

- An invalid DTB stops boot before the interpreter starts. An invalid user image stops it before any process exists.
- A process cannot read, write or execute another process's, supervisor, free or device memory. Such access causes a page fault that terminates only that process.
- A syscall pointer to unmapped memory, or memory without the required permission, returns `BAD_ADDRESS` and reads or writes nothing.
- A released handle never resolves again, even after slot reuse.
- Deriving or transferring a capability never expands rights; placing a handle integer in a payload does not transfer authority.
- A private frame is zeroed before being assigned to another process.
- Resource charging is atomic: every limit passes or nothing changes. Account totals equal global usage.
- Process creation that fails at any allocation releases everything already reserved.
- After 10,000 process and IPC cycles, free-frame, object, capability, endpoint, message and buffer counters equal their post-warmup values.
- No interrupt is accepted in S-mode; timer and external-interrupt paths neither run Python nor allocate.
- A driver never supplies or receives a physical address, and no device queue is mapped into a process.
- Device-request memory cannot return to the allocator while the device can reach it. An unconfirmed reset leaves it quarantined.
- Paths never resolve outside the client's namespace root; a derived namespace never has more rights than its source.
- A file handle is valid only for the process that opened it and the issuing service instance.
- An acknowledged `SYNC` survives loss of any writes not yet followed by a flush. After a crash, mounting exposes a whole commit.
- A volume that fails validation is never mounted writable; no volume is created, formatted or repaired to allow boot to continue.
- No layer automatically repeats a side-effecting operation whose outcome is unknown.
- A malformed packet is dropped by its layer's parser, counted and leaves no socket, connection or buffer behind.
- A process without service-issued network access cannot open sockets; restricted access never has more rights than its source.
- A peer or process cannot exceed the service's network-buffer budget regardless of how many sockets or connections it opens.
- Invalid configuration is never applied partially: none of its services starts.
- A failed service is restarted at most the configured number of times per window, with the same grants as its previous instance.
- An application receives only policy-granted endpoints with `SEND`. It receives no system capability, devices or control endpoint.
- Requested shutdown stops services and synchronizes volumes before calling firmware.
- The kernel ELF is static, has no undefined symbols and links only `libgcc` in addition to project objects.

## Residual risks

- Isolation has been exercised only with QEMU TCG and one hart. No physical board has been tested.
- `debug_write` requires no capability: any process can write to the diagnostic console, 256 bytes per call.
- The file service is trusted for its volumes, and each driver for its assigned device. A defect may corrupt or expose data passing through it but cannot reach other processes' memory.
- CRC-32 detects accidental corruption. It does not authenticate a volume against deliberate modifications with recomputed checksums.
- Durability was demonstrated on QEMU `virtio-blk`, against loss, reordering and truncation of writes not followed by a flush. A disk acknowledging a flush it did not perform is outside the tested scope.
- Quarantined frames return only at the next boot. Repeated reset failures reduce available memory.
- Entropy comes from QEMU's `virtio-rng`. Without it the system provides none, and byte quality depends on the host.
- `init` and the system manager start with the system capability. A defect can affect process creation, devices, counter access and shutdown requests.
- The network service is trusted for its traffic. A defect may expose or alter connection data but cannot reach other processes' memory or volumes.
- Traffic is neither encrypted nor authenticated. Peers on the same network can read and forge packets; random initial sequence numbers hinder but do not prevent injection.
- Interoperability was demonstrated against Linux TCP/IP on an isolated network with moderate loss, duplication and reordering. Other peers and long network paths were not tested.
- The shell does not authenticate its operator: access to the serial port grants the rights in `[access.shell]`.
- Each application compiles its loaded source code. A MicroPython compiler defect remains contained in that process.
- A download hash proves correspondence with the lockfile, not upstream trustworthiness.
- TCG does not reproduce real hardware timing or failures.
