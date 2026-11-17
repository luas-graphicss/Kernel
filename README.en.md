# Kernel

[Português](README.md)

Python-first kernel for 64-bit RISC-V. The system policies are written in Python and run on MicroPython inside the supervisor, in S-mode. Each user process is another MicroPython, in U-mode, with its own address space. The native code, in C17 and Assembly, covers what depends on the machine and what cannot trust Python: boot, traps, virtual memory, context switching, capabilities, IPC, device transport and validation of process calls.

The target is the QEMU `virt` machine with the OpenSBI firmware. The guest has no Linux and does not use semihosting.

## What exists today

- Boot through OpenSBI with a validated DTB, an NS16550 console and trap diagnostics.
- Sv39 virtual memory: a frame allocator with a reserve for the supervisor and one address space per process, with code that cannot be written, data that cannot be executed and a guard page under the stack.
- Up to 16 processes in U-mode, each with a private MicroPython. The timer preempts a process that does not cooperate, and the context switch preserves integer and floating-point registers.
- Capabilities with generational handles: derivation that only reduces rights, transfer over IPC or at process creation, revocation of the derived ones and a quota per process.
- IPC over endpoints, with send, receive and call with a correlated reply, deadline, cancellation and a defined ending when the other side dies. Memory buffers granted by capability for data larger than one message.
- Python policy frozen into the kernel image. It checks the resource profile, admits processes within the quotas and chooses who runs: four priorities, round-robin, aging and bounded priority donation to whoever is serving a call.
- Devices discovered in the DTB and handed out by capability, each to one driver. The VirtIO-MMIO transport and the queues stay in the supervisor: the driver names buffers of its own process and never states a physical address. The memory of a request stays pinned until the device completes it or confirms the reset.
- Drivers and services in Python, in U-mode, for the serial port, `virtio-blk` and `virtio-rng`. The console has a line discipline, bounded input and output with backpressure. Requests to a device have a deadline. Without `virtio-rng` the system offers no entropy.
- File service with namespaces by capability and file and directory handles, over three mounts: the read-only boot image, a temporary in-memory file system and a persistent volume.
- Copy-on-write persistent volume, with two superblocks, a checksum on every pointer and whole commits. `sync` only answers after the device flush. A volume that fails verification becomes unavailable or read-only and is never formatted at boot.
- `init` in U-mode, which starts the services of its manifest with the declared capabilities, checks that they answer and stops them: `echo` and, for the devices the DTB describes, console, entropy, block and files.
- IPv4 networking in a Python service, in U-mode, with the `virtio-net` driver inside the process: Ethernet, ARP, fragmentation and bounded reassembly, ICMP, UDP and TCP with retransmission, congestion control, half-close and `TIME_WAIT`. An interface with a static address and a default route; no IPv6, DHCP or DNS.
- Sockets by capability: a process only opens a socket with an access issued by the service, which can be restricted and revoked. Operations have a timed wait, cancellation and backpressure, and network memory has a single budget.
- System manager in U-mode, which reads a declarative configuration, validated as a whole before it is applied, starts the services in dependency order and restarts whoever dies within a limit per window. A service that exhausts the limit becomes degraded and visible, and the rest carries on.
- Shell on the serial port, with `help`, `run`, `ps`, `kill`, `wait`, `mem`, `ls`, `cat`, `mkdir`, `write`, `rm`, `sync`, `net`, `ping` and `shutdown`. Each command is a request to a service and ends with a status line.
- Applications: Python programs read from the volume and run in their own processes, with only the files and the network the configuration grants.
- Orderly shutdown: new applications refused, applications ended, services stopped in reverse order, volumes synchronized and, at the end, power off or reboot through the SBI.
- Pure models of generational handles, process selection and resource accounting. A corpus of 10,000 transitions runs on CPython and inside the guest, and the results must be equal.
- `kernel-tool`, which downloads the hash-pinned toolchain, builds, starts QEMU with a deadline, runs the scenarios and inspects the images. It also creates, verifies and inspects volumes, and rebuilds the states a power loss would leave on the disk. For the network, it connects the guest to an isolated test station on the host, degrades the link on purpose, injects forged frames and records the traffic.
- Qualification through `kernel-tool`: the whole verification matrix in one command, fuzzing of 14 targets in four input families with a versioned corpus, repeated boot, a soak of one boot under mixed load, measurement of the budgets and a build redone in empty directories. Each report carries the hash of the images it refers to.
- Frozen 1.0 interfaces, with a compatibility policy: ABI, service protocol, images, configuration and volume format.
- Release bundle assembled on the host, with a manifest, checksums, an SBOM in SPDX 2.3, a license inventory and an OpenSSH signature with a key from outside the repository. Installation, update and rollback swap the images and keep the data volume.

The kernel uses a single hart, and isolation was exercised only on QEMU with TCG. Durability was demonstrated only on QEMU's `virtio-blk`: a disk that confirms a flush it did not perform is outside what was tested. The network was exercised against the Linux TCP/IP stack, on an isolated network; traffic is not encrypted, and the shell does not authenticate whoever is on the serial port.

Version 1.0 is not qualified yet. Two release gates ask for 24 hours of execution each, the soak and the fuzzing of each family, and they have not been met. The state of each gate, with what was run, is in the [qualification record](docs/acceptance/qualification-and-distribution.en.md).

## Host requirements

- Linux x86_64. The packages in `toolchain.lock.toml` are for that platform.
- [uv](https://docs.astral.sh/uv/). The project is developed with version 0.13.5. uv installs the Python 3.13 named in `.python-version`.
- `make` and the host GCC, reachable as `cc` and as `gcc`, with AddressSanitizer and UndefinedBehaviorSanitizer. It builds `mpy-cross` and the hosted native tests. On Amazon Linux 2023 the sanitizer runtime comes separately, in the `libasan` and `libubsan` packages. Without `make`, `cc` or `gcc`, `build` ends with status 3 and says which one is missing.
- Paths without spaces for the repository, the build directory and the toolchain cache. `make` splits file names at spaces, and `build` refuses such a path with status 3 and names it. Accented characters are fine.
- About 2.5 GB free for the toolchain. It lives in `~/.cache/kernel-tool` or in the directory named by `KERNEL_TOOL_CACHE`.
- For the network: permission to create a network namespace with a TAP interface. Running as root works, as does a host that allows unprivileged user namespaces with access to `/dev/net/tun`, or passwordless `sudo`. Without it `run` carries on without a network, and the network suites end with status 3.

## Build and run

```sh
uv sync --frozen
uv run kernel-tool toolchain
uv run kernel-tool build
uv run kernel-tool run
```

`toolchain` downloads and checks the pinned GCC, QEMU and MicroPython. `build` produces the images in `build/qemu-riscv64/`. `run` starts the system in QEMU with the shell on this terminal, a data volume that persists in `build/qemu-riscv64/system/` and the isolated network, and ends when the system powers off:

```
kernel> ping 10.0.2.2 2
ping: from=10.0.2.2 bytes=32 time-us=4540
ping: from=10.0.2.2 bytes=32 time-us=2022
ping: sent=2 received=2
shell: command=ping status=ok
kernel> shutdown
```

`--deadline` limits the session time and `--without-network` leaves the network out. When the input comes from a pipe or a file, `run` only delivers it to the system after `shell: ready`. The default profile is `qemu-riscv64`; `--profile` chooses another file from `config/profiles/`. Shell usage is in [Operating the system](docs/operations/system-operation.en.md).

## Verify

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict host src
uv run pytest tests/host tests/conformance
uv run kernel-tool native-check
uv run kernel-tool test --suite bootstrap
uv run kernel-tool test --suite memory
uv run kernel-tool test --suite processes
uv run kernel-tool test --suite capabilities
uv run kernel-tool test --suite ipc
uv run kernel-tool test --suite scheduling
uv run kernel-tool test --suite devices
uv run kernel-tool test --suite vfs
uv run kernel-tool test --suite storage
uv run kernel-tool test --suite network
uv run kernel-tool test --suite network-interop
uv run kernel-tool test --suite applications
uv run kernel-tool test --suite supervision
uv run kernel-tool test --suite system-journey
uv run kernel-tool test --suite release-journey
uv run kernel-tool fault-test --suite device-reset
uv run kernel-tool fault-test --suite storage-crash
uv run kernel-tool fault-test --suite network-faults
uv run kernel-tool verify-filesystem --corpus tests/faults/storage
uv run kernel-tool verify-artifacts --reproduce
```

| Command | What it checks |
| --- | --- |
| `native-check` | Hosted native tests under sanitizers and the static analysis of the supervisor |
| `test --suite bootstrap` | Nine scenarios on QEMU: repeated boot, runtime self-test, oversized DTB, DTB without memory, insufficient RAM, incompatible segment, fault in U-mode and trap in the supervisor, with the runtime stopped and with its heap exhausted |
| `test --suite memory` | Adversarial programs in U-mode: access to memory of another process, of the supervisor, free memory, device memory and the guard page; invalid pointers in syscalls; shared buffers; memory zeroed between processes; quotas and the supervisor reserve |
| `test --suite processes` | Exit status, authority and validation at creation, preemption of a loop that does not cooperate, register preservation, 16 simultaneous processes and release of resources at exit. Two separate scenarios: failure of each allocation of a creation, and 10,000 process and IPC cycles without resource growth |
| `test --suite capabilities` | Stale and forged handles, attenuated delegation, revocation with descendants, quota, absence of ambient authority and mappings that follow the capability |
| `test --suite ipc` | Malformed messages, delivery and transfer, queue limits, death of the other side, cancellation, deadlines, reply correlation, endpoint ownership and deadlock refusal |
| `test --suite scheduling` | Round-robin, priority without starvation, priority donation, wait chain limit, deadline racing the reply, clock limits and yield. A separate scenario records the scheduling trace of the boot |
| `test --suite devices` | Drivers in U-mode: access only to the device received, contention for the same device, incompatible negotiation, descriptors outside the granted buffers and exit with a pending request. Two separate scenarios: the console, block and entropy services with the authority of each operation, and boot without an entropy source |
| `test --suite vfs` | File service over the boot image and the temporary file system: paths with `..`, oversized names and invalid UTF-8, namespaces and rights, handles, concurrent clients and stale handles after the service restarts |
| `test --suite storage` | Persistent volume on `virtio-blk`: full disk, `sync` tied to the flush and service restart. Seven separate scenarios: data written in one boot and checked in the next, read-only device, unformatted device, unknown format version, damaged newest root and flush error |
| `test --suite network` | Network service against the test station: interface and echo, empty, large and truncated datagrams and datagrams to a port without a socket, connections in both directions, listening, timed wait, cancellation and backpressure, socket quota and access rights, with a process without access that neither opens a socket nor reaches the device |
| `test --suite network-interop` | Data exchanged with the Linux TCP/IP stack, checked by hash, in two scenarios: a clean link and a link with 3% loss, 2% duplication and 10% reordering. Sending and receiving 128 KiB, a 64 KiB round trip, a connection started by the peer, fragmented datagrams, a peer that reads slowly and return of the buffers |
| `test --suite applications` | Programs from the volume started by the shell: arguments, memory not shared between runs, capabilities received, exception, syntax error, missing file, loop ended by `kill`, exhausted heap, application limit and shutdown with applications running |
| `test --suite supervision` | Start and stop order, a service that never becomes ready, restart with a pending request, restart limit and window. Five separate scenarios: a system without a network device, with the network degraded and the rest in use, and four configurations refused with nothing applied: missing, with a circular dependency, with an excessive value and inconsistent |
| `test --suite system-journey` | Two boots over the same volume, operated through the shell: files, programs, `ping`, a TCP transfer written to a file, `sync`, shutdown with an application stuck in a connection and restart; the second boot checks the data of the first and powers off |
| `test --suite release-journey` | First initialization, update to a boot image of another version over the same volume and return to the previous image with the data of both. Two separate scenarios: a volume with the newest root damaged, which becomes read-only, and a volume in an unknown format, which is neither mounted nor changed |
| `fault-test --suite device-reset` | A device that stops answering: request deadline, driver exit with pending IO and a reset that fails, without returning to the allocator the memory still exposed to the device |
| `fault-test --suite storage-crash` | States a power loss would leave on the disk, with loss, cut and reordering of the writes not yet flushed: 66 crash points in 11 transactions, 1,000 sequences generated from seed 1 and the record of writes and flushes of one boot on QEMU. Each state must mount at a whole commit, with every `sync` confirmed. The mount runs on the host, with the guest's recovery code |
| `fault-test --suite network-faults` | 31 specimens of malformed frames, from Ethernet to TCP, each counted by the parser of its layer; 32 forged connection requests against an accept queue; 1.5 s of link down in the middle of a transfer; reset of the network device; restart of the service with a client waiting |
| `verify-filesystem --corpus` | The 21 images of `tests/faults/storage`, valid, truncated, incompatible and corrupted, each with the expected verdict |
| `verify-artifacts --reproduce` | Static linking, origin of every link input, layout and hashes of the images, and no path of the build machine inside them; builds again in another directory and requires identical images |
| `inventory` | Version and hash of each tool used in the build |

The reports are in `build/qemu-riscv64/reports/`, and the traffic captures of the network suites in `reports/captures/`.

For volumes outside the suites, `create-volume` writes an empty volume to a file that does not exist yet, `inspect-volume` prints the superblocks and the tree of an image and `build-corpus` rewrites the corpus images from the recipes. No command formats or repairs a volume that already exists.

`kernel-tool` ends with 0 on success, 1 when a verification fails, 2 on a usage error and 3 when the infrastructure is unavailable, for example a pinned tool that could not be downloaded or run.

## Qualify and distribute

```sh
uv run kernel-tool verify --all
uv run kernel-tool repeat-boot --count 1000
uv run kernel-tool benchmark
uv run kernel-tool reproduce-build
uv run kernel-tool fuzz --all --budget-hours 24
uv run kernel-tool soak --hours 24
uv run kernel-tool release-check
```

| Command | What it does |
| --- | --- |
| `verify --all` | Runs everything the previous section lists, plus `verify-interfaces` and the replay of the fuzzing corpus, and records one result per verification. A verification that could not run stays incomplete and does not count as a success |
| `verify-interfaces` | Compares the files of the frozen interfaces with the digests in `specs/frozen-interfaces.toml` |
| `fuzz`, `replay-corpus` and `promote-corpus` | Mutate the boot, interface, storage and network inputs for the time requested for each family; replay the seeds, the corpus and the regressions; copy to `tests/fuzz/corpus/` what reached new code |
| `repeat-boot` | Starts the release image up to the shell and shuts down in order, as many times as requested, with the result of each boot |
| `benchmark` | Measures boot, memory, IPC, ready-task response, pauses of the supervisor collector and release after exit, and compares them with the budgets |
| `soak` | Keeps one boot under a load of processes, files, network and memory, and fails persistent resource growth |
| `reproduce-build` | Builds twice in empty directories and requires images equal to each other and equal to those of the current build |
| `release-check` | Evaluates the twelve release gates and assembles the bundle in `build/qemu-riscv64/release/`. It ends with status 1 while any gate is open. It does not publish, create a tag or use a key |
| `release-sign` and `release-verify` | Sign the checksums of a bundle with a key from outside the repository and check checksums and signature |
| `install`, `update` and `rollback` | Install a bundle in a directory with its data volume, swap the installed release and go back to the previous one when it reads the volume format |

The qualification reports are in `build/qemu-riscv64/qualification/` and in `build/fuzz/`. The complete sequence is in [Qualifying and assembling a release](docs/operations/release-procedure.en.md), and the use of a bundle in [Installing, updating and recovering](docs/operations/installation.en.md).

## Layout

| Path | Content |
| --- | --- |
| `native/` | Supervisor in C17 and RISC-V Assembly |
| `ports/micropython/` | MicroPython port: common part, `supervisor` profile and `user` profile |
| `src/` | Guest Python: `kernel_protocol`, `kernel_core`, `kernel_client`, `kernel_drivers`, `kernel_services` and `kernel_apps`, with the shell and the application runner |
| `apps/` | Programs the boot image carries in `apps/` |
| `host/kernel_tool/` | Build, run and verification tool |
| `tests/` | Host tests, conformance corpus, hosted native tests, guest self-test, adversarial programs of the suites, volume corpus and, in `tests/fuzz/`, the native targets and the fuzzing corpus |
| `specs/abi/` | Handles, errors, syscalls, capabilities, messages, buffers, processes, devices, device services, user image and resource profile |
| `specs/filesystem/` | Volume format, boot image and file service protocol |
| `specs/network/` | Supported protocols and socket service |
| `specs/system/` | Configuration, manager and control service, applications |
| `specs/compatibility.md` and `specs/frozen-interfaces.toml` | Compatibility policy and digests of the frozen interfaces |
| `config/boot/` | Manifest of the boot image files |
| `config/system/` | System configuration that goes into the boot image |
| `config/profiles/` | Machine, memory layout, limits and deadlines of each profile |
| `config/release/` | Review of the security advisories of each pinned component |
| `docs/` | Architecture decisions, requirements, conformance, security, operation and acceptance records |

## Documentation

Every document has a Portuguese version, the original, and an English version next to it with the `.en.md` suffix.

- [Operating the system](docs/operations/system-operation.en.md), [operating the network](docs/operations/network-operation.en.md) and [services and configuration](docs/operations/services-and-configuration.en.md)
- [Requirements matrix](docs/architecture/requirements.en.md) and [conformance matrix of the public APIs](docs/architecture/api-conformance.en.md)
- [Acceptance record of the network and the operational environment](docs/acceptance/network-and-operational-environment.en.md) and [qualification record](docs/acceptance/qualification-and-distribution.en.md)
- [Installing, updating and recovering](docs/operations/installation.en.md), [qualifying and assembling a release](docs/operations/release-procedure.en.md) and [diagnostics](docs/operations/diagnostics.en.md)
- [Compatibility policy](specs/compatibility.en.md)
- [Differences between CPython and the guest runtime](docs/architecture/runtime-differences.en.md)
- [Architecture decisions](docs/decisions/)
- [Volume format](specs/filesystem/volume-format.en.md), [boot image](specs/filesystem/boot-image.en.md) and [file service](specs/filesystem/file-service.en.md)
- [Network protocols](specs/network/protocols.en.md) and [socket service](specs/network/socket-service.en.md)
- [System configuration](specs/system/configuration.en.md), [manager and control service](specs/system/control-service.en.md) and [applications](specs/system/applications.en.md)
- [Threat model](docs/security/threat-model.en.md), [trusted computing base](docs/security/trusted-computing-base.en.md), [privileged boundary review](docs/security/privileged-boundary-review.en.md) and [vulnerability response](docs/security/vulnerability-response.en.md)
- [Reference machine, workload and budgets](docs/operations/reference-machine.en.md)
- [Continuous integration](docs/operations/continuous-integration.en.md)

## License

GPL-3.0-only. The full text is in [LICENSE](LICENSE).
