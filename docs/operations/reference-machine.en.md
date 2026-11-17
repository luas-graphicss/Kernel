# Reference machine, workload and initial budgets

[Português](reference-machine.md)

Defines where and under what load the project's measurements are taken, and the limits the tests apply today. Results obtained with TCG are not extrapolated to physical hardware.

## Reference machine

| Dimension | Value |
| --- | --- |
| Emulator | QEMU 9.2.4, xPack package `9.2.4-1`, pinned by hash in `toolchain.lock.toml` |
| Accelerator | TCG, one hart |
| Machine | `virt,aia=none,acpi=off`, CPU `rv64,h=off,v=off`, `virtio-mmio.force-legacy=false` |
| Firmware | OpenSBI 1.5.1 `fw_dynamic`, from the same package |
| Guest RAM | 256 MiB |
| Devices | NS16550 serial port. Depending on the scenario, a `virtio-rng-device` connected to `rng-builtin` and one `virtio-blk-device` per disk: the boot image, read-only, with the serial `kernel-boot`, and the data volume, with the serial `kernel-data`. In the scenarios with a network, a `virtio-net-device` connected by a `dgram` netdev, over Unix sockets, to the test station on the host |
| Image | `kernel.elf` with `init.img` as the boot module, from the `qemu-riscv64` profile. The program suites use `tests.img` |
| Layout | Kernel at `0x80200000`, supervisor heap of 8 MiB and, in each process, a user virtual region of 16 MiB at `0x40000000` |

The source of these values is `config/profiles/qemu-riscv64.toml`. ADR 0001 explains the choice.

## Measurement host

The first measurements came from a Linux x86_64 host with 2 Intel Xeon vCPUs at 2.5 GHz and 4 GiB of RAM, without hardware acceleration for the guest. The baseline with devices and a persistent volume came from a host with 2 Intel Xeon vCPUs at 2.9 GHz and 4 GiB of RAM. The baseline with the network and the operational environment came from a host with the same configuration and Linux 6.18, whose TCP/IP stack is the peer of the network suites. The qualification baseline came from a host with that same configuration. Every new measurement records the host along with it.

The time is that of the host, measured by `kernel-tool` around each QEMU run, and includes the start of the emulator and of OpenSBI. The guest reads its own monotonic time from the `time` counter, with the frequency the DTB reports, and uses it for the quantum and for deadlines. The latencies of the performance budgets are measured with that time, and the other measurements on this page with that of the host.

## Reference workload

The suites of `kernel-tool test`:

- `bootstrap`, scenario `boot`, three times: full boot, Python policy, admission and execution of `init`, which starts `echo` and the console, entropy, block and file services, checks each one and stops them. The scenario runs with the serial port, the entropy source, the boot image and a disposable data volume.
- `bootstrap`, scenario `runtime-selftest`: probes of collector roots in `s0` to `s11` and in a stack slot, cases of integers, bytes, exceptions, imports, bindings and collection under pressure, 10,000 transitions of the corpus and repeated restarts of the interpreter.
- `bootstrap`, seven failure scenarios: oversized DTB, DTB without memory, insufficient RAM, incompatible segment, fault in U-mode and trap in the supervisor, with the runtime stopped and with its heap exhausted.
- `memory`, `processes`, `capabilities`, `ipc`, `scheduling`, `devices`, `vfs` and `storage`: the programs in `tests/guest/programs/suites/`, one boot per scenario. The disks are disposable images that `kernel-tool` creates for the run.
- `processes`, scenario `cycles`: 100 warm-up cycles and 10,000 measured ones. Each cycle creates a process of the `echo` service, exchanges two calls with it and waits for it to end.
- `fault-test --suite device-reset`, scenario `stalled-device`: a block device that stops answering, up to the request deadline and the reset.
- `fault-test --suite storage-crash`: the record of writes and flushes of one boot, 66 crash points in 11 transactions and 1,000 sequences generated from seed 1. The mount of each image runs on the host.
- `verify-filesystem --corpus tests/faults/storage`: the 21 images of the corpus.
- `network`: the programs in `tests/guest/programs/suites/network`, in one boot, against the test station: echo, datagrams, connections in both directions, a 20 KiB send checked by hash and a 16 KiB connection started by the peer.
- `network-interop`, two scenarios, one with a clean link and another with 3% loss, 2% duplication and 10% reordering, generated from seed 7: sending and receiving 128 KiB, a 64 KiB round trip through the guest, a 64 KiB connection started by the peer, four fragmented datagrams of 3072 bytes and 32 KiB to a peer that reads slowly.
- `applications`: 28 commands typed into the shell, with 13 requests to start programs from `tests/guest/apps`, one of them refused by the limit.
- `supervision`: five cases over a set of test services, one boot without a network device and four boots with refused configurations.
- `system-journey`: two boots over the same data volume, with 28 and 7 commands typed into the shell and a transfer of 6240 bytes over TCP written to a file.
- `fault-test --suite network-faults`: 31 malformed specimens in 32 frames, 32 forged connection requests, 1.5 s of link down, one reset of the network device and one restart of the service with a client waiting.
- `release-journey`: five boots. Three use the same data volume: the first initialization, a boot with the boot image of another version and the return to the previous image. The other two use prepared volumes, one with the newest root damaged and another in an unknown format.
- `repeat-boot`: the scenario `boot-to-shell`, one boot of the release image with a valid volume and the isolated network, until the shell accepts `shutdown`.
- `benchmark`, scenario `guest-measurements`: 10,000 calls to an echo process and 50 exits, each measured from the `kill` until the frames of the process are free again.
- `benchmark`, scenario `process-churn`: the `cycles` scenario, with the tracing of the supervisor collector on.
- `benchmark`, scenario `system-measurements`: a session through the shell. `mem` with the system at rest. Then four `spin.py`, bound to the processor, two `chatter.py`, which rewrite and reread a file of 960 bytes, one in `tmp` and another in `data`, and `latency.py`, which waits 400 times for a 5 ms deadline and measures the delay after it. Finally four `ballast.py`, each with 1,280 KiB on the heap, and `mem` again.
- `soak`: a single boot, with the rounds described in `release-procedure.en.md`.
- `fuzz`: the 14 targets of the families `boot`, `interface`, `storage` and `network`, from the seeds of each target and from `tests/fuzz/corpus/`.

## Initial budgets

These are limits that fail the test when exceeded. They are not measured results or product targets.

| Resource | Budget | Where it is applied |
| --- | --- | --- |
| Time of a boot up to the final status | 60 s | `deadlines.boot_seconds` of the profile |
| Time of the runtime self-test | 600 s | `deadlines.selftest_seconds` of the profile |
| Time of the `cycles` scenario | 900 s | `deadlines.soak_seconds` of the profile |
| Time of a session with the network or with the shell | 300 s | `deadlines.session_seconds` of the profile |
| DTB accepted | 64 KiB | DTB validation at boot |
| Physical memory of the profile | 256 MiB | The boot refuses the machine with less RAM |
| Supervisor heap | 8 MiB | Link layout, checked by the policy at boot |
| User region | 16 MiB of virtual addresses per process | Link layout; the image is refused if it does not fit |
| Default heap and stack of a process | 1 MiB and 64 KiB | User image header |
| Heap per process | 4 MiB | Admission by the policy |
| Processes | 16 | Admission by the policy and native table |
| Quantum | 10 ms | Python supervisor, at each run of a process |
| Capabilities per process | 128 | Capability table |
| Payload of a message | 4 KiB | Message validation on send |
| Pending messages per endpoint | 64 | Endpoint queue |
| Pending IPC bytes | 1 MiB per process and 16 MiB in total | IPC quota on send |
| Debug write | 256 bytes per call | `debug write` call |
| VirtIO transports | 8 | Inventory of the DTB devices |
| Requests in progress per device | 4, of up to 4 segments each | Request queue of the supervisor |
| Console input | 256 bytes waiting, lines of up to 255 bytes and 4 complete lines waiting | Serial port of the supervisor and line discipline |
| Path | 1024 bytes, 32 components and names of up to 255 bytes | File service, before consulting the volume |
| Persistent volume | From 8 to 65,536 blocks of 4096 bytes | Verification at mount |
| Boot image | 64 files of up to 256 KiB | Image validation at mount |
| Sockets | 64 in total and 16 per process | Network service, on open |
| TCP connections | 96 | Network service, counting those opening, closing and waiting in `time-wait` |
| Bytes in socket buffers | 1 MiB for all sockets | Single budget of the network service |
| Reassembly | 16 datagrams, 1 MiB and 30 s | IPv4 stack, apart from the socket budget |
| Applications running | 4, with a heap of 2 MiB each | `[access.application]` in `config/system/system.conf` |
| Restarts of a service | 2 or 3 every 60 s | `[service.*]` in `config/system/system.conf` |
| Shell line | 255 bytes and 16 words | Shell, before running the command |

The other limits of the profile are in `specs/abi/resource-profile.en.md`. Those of devices and files are in `specs/abi/devices.en.md` and in `specs/filesystem/`, those of the network in `specs/network/protocols.en.md` and those of the system in `specs/system/configuration.en.md`.

## Performance budgets

These are the limits `kernel-tool benchmark` applies to the release images. The `budgets` gate fails the release when one of them is exceeded or was not measured. The measured values are in the qualification baseline, at the end of this page.

| Metric | Budget | How it is measured |
| --- | --- | --- |
| Boot up to the shell ready and the orderly shutdown | 15 s | Host clock, from the start of the emulator to the end of the shutdown, with the release image, a valid volume and the isolated network |
| Memory committed at rest | 96 MiB | Machine memory minus the free frames, with the mandatory services and the shell waiting |
| Memory committed under load | 224 MiB | The same calculation, with the four application slots taken and each heap filled |
| Small IPC round trip | p99 of 25 ms | Guest clock, 10,000 calls to an echo process, without disk and without network |
| Ready-task response | p99 of 250 ms | Guest clock, delay after the deadline of a timer, with the mandatory services, four applications bound to the processor and two to files |
| Pause of the supervisor collector | p99 of 25 ms and maximum of 100 ms | Histogram kept by the supervisor, read in the session under load |
| Release after exit | Maximum of 1 s | Guest clock, from the `kill` of a process until its frames are free again |
| Growth of live resources | No persistent worsening after the warm-up | `cycles` scenario and `kernel-tool soak` |

Changing one of these budgets asks for an ADR and a new baseline.

## First baseline

Measured on a clean clone, on the host described above, before virtual memory, preemptive processes and IPC existed.

| Measurement | Value |
| --- | --- |
| Scenario `boot` | 5.3 s for the three runs |
| Scenario `runtime-selftest` | 44.2 s |
| Each failure scenario | Less than 0.2 s |
| Full build | 25 s |
| `kernel.elf` | 1,160,112 bytes in the file and 145,948 bytes in the loadable segments: 80,140 of code, 63,808 of read-only data and 2,000 of data |
| `kernel-selftest.elf` | 1,249,112 bytes in the file |
| `init.img` | 118,104 bytes |

## Baseline with processes and IPC

Measured on a host with the same configuration: Linux x86_64, 2 Intel Xeon vCPUs at 2.5 GHz and 4 GiB of RAM.

| Measurement | Value |
| --- | --- |
| Scenario `boot` | 0.4 s for the three runs |
| Scenario `runtime-selftest` | 48.0 s |
| Scenario `runtime-trap` | 2.0 s |
| Each of the other failure scenarios | Less than 0.2 s |
| Suites `memory`, `capabilities` and `ipc` | 0.6 s, 0.2 s and 0.5 s |
| Suite `processes`, scenarios `cases` and `spawn-failures` | 1.9 s and 0.3 s |
| Scenario `cycles` | 69.1 s |
| Suite `scheduling`, scenarios `cases` and `schedule-trace` | 1.3 s and 0.1 s |
| Full build | 35 s |
| `kernel.elf` | 1,503,960 bytes in the file. Loadable segments: 104,998 bytes of code, 76,032 of read-only data and 1,034,464 without content in the file, from the static tables of the supervisor |
| `kernel-selftest.elf` | 1,601,504 bytes in the file |
| `init.img` | 136,424 bytes |
| `tests.img` | 226,078 bytes |

The `init` of this measurement does not repeat the allocation load of the first: it starts the `echo` service, checks one reply and ends. The two values of the `boot` scenario are not comparable.

## Baseline with devices and a persistent volume

Measured on a clean clone, on a Linux x86_64 host with 2 Intel Xeon vCPUs at 2.9 GHz and 4 GiB of RAM. The host is a different one, and the times are not comparable with those of the earlier baselines.

| Measurement | Value |
| --- | --- |
| Scenario `boot` | 0.7 s for the three runs |
| Scenario `runtime-selftest` | 36.9 s |
| Scenario `runtime-trap` | 2.5 s |
| Each of the other failure scenarios | 0.1 s |
| Suites `memory`, `capabilities` and `ipc` | 0.6 s, 0.2 s and 0.5 s |
| Suite `processes`, scenarios `cases` and `spawn-failures` | 1.5 s and 0.3 s |
| Scenario `cycles` | 58.7 s |
| Suite `scheduling`, scenarios `cases` and `schedule-trace` | 1.2 s and 0.1 s |
| Suite `devices`, scenarios `cases`, `services` and `without-entropy` | 0.2 s, 0.4 s and 0.2 s |
| Suite `vfs` | 1.7 s |
| Suite `storage`, scenario `cases` | 3.6 s |
| Suite `storage`, scenarios `persistence-write` and `persistence-verify` | 0.4 s each |
| Suite `storage`, each of the other five scenarios | 0.2 s |
| `fault-test --suite device-reset`, scenario `stalled-device` | 7.1 s |
| `fault-test --suite storage-crash`, scenario `flush-trace` | 0.6 s |
| `fault-test --suite storage-crash`, images mounted | 226 from the matrix of 66 crash points, 8,000 from the 1,000 sequences, with 3,457 commits, and 424 from the record of one boot, with 51 events and 7 generations |
| Full build | 30 s |
| `kernel.elf` | 1,626,976 bytes in the file. Loadable segments: 115,508 bytes of code, 77,008 of read-only data and 1,039,664 without content in the file, from the static tables of the supervisor |
| `kernel-selftest.elf` | 1,724,504 bytes in the file |
| `init.img` | 245,584 bytes |
| `tests.img` | 396,990 bytes |
| `boot.img` | 49,152 bytes |

## Baseline with the network and the operational environment

Measured in an empty build directory, on a Linux 6.18 x86_64 host with 2 Intel Xeon vCPUs at 2.9 GHz and 4 GiB of RAM. The whole run, with the counts of each case, is in `docs/acceptance/network-and-operational-environment.en.md`.

| Measurement | Value |
| --- | --- |
| Scenario `boot` | 0.7 s for the three runs |
| Scenario `runtime-selftest` | 37.1 s |
| Scenario `runtime-trap` | 2.6 s |
| Each of the other failure scenarios | 0.1 s |
| Suites `memory`, `capabilities` and `ipc` | 0.6 s, 0.2 s and 0.6 s |
| Suite `processes`, scenarios `cases` and `spawn-failures` | 1.6 s and 0.3 s |
| Scenario `cycles` | 63.3 s |
| Suite `scheduling`, scenarios `cases` and `schedule-trace` | 1.2 s and 0.2 s |
| Suite `devices`, scenarios `cases`, `services` and `without-entropy` | 0.2 s, 0.4 s and 0.3 s |
| Suite `vfs` | 1.6 s |
| Suite `storage`, scenario `cases` | 3.3 s |
| Suite `storage`, scenarios `persistence-write` and `persistence-verify` | 0.4 s each |
| Suite `storage`, each of the other five scenarios | From 0.2 s to 0.3 s |
| Suite `network` | 13.1 s |
| Suite `network-interop`, scenarios `interop-clean-link` and `interop-impaired-link` | 2.5 s and 5.0 s |
| Suite `applications` | 5.0 s |
| Suite `supervision`, scenario `supervision-cases` | 2.4 s |
| Suite `supervision`, scenario `network-absent` | 0.3 s |
| Suite `supervision`, each of the four refused configuration scenarios | 0.2 s |
| Suite `system-journey`, first and second boot | 3.7 s and 0.6 s |
| `fault-test --suite device-reset`, scenario `stalled-device` | 7.2 s |
| `fault-test --suite storage-crash`, scenario `flush-trace` | 0.8 s |
| `fault-test --suite storage-crash`, images mounted | 226 from the matrix of 66 crash points, 8,000 from the 1,000 sequences, with 3,457 commits, and 424 from the record of one boot, with 51 events and 7 generations |
| `fault-test --suite network-faults` | 2.6 s |
| Full build | 33 s |
| `kernel.elf` | 1,635,424 bytes in the file. Loadable segments: 116,350 bytes of code, 77,176 of read-only data and 1,043,120 without content in the file, from the static tables of the supervisor |
| `kernel-selftest.elf` | 1,732,968 bytes in the file |
| `init.img` | 431,655 bytes |
| `tests.img` | 622,799 bytes |
| `boot.img` | 65,536 bytes |

The hashes of the images and the tool inventory are in the reports `bootstrap.json` and `artifacts.json`. They change with every commit and so are not copied here.

## Qualification baseline

Measured in an empty build directory, on a Linux 6.18 x86_64 host with 2 Intel Xeon vCPUs at 2.9 GHz and 4 GiB of RAM, over the images of version `1.0.0rc1`. The whole run, with the release gates, is in `docs/acceptance/qualification-and-distribution.en.md`.

| Measurement | Value |
| --- | --- |
| Scenario `boot` | 0.7 s for the three runs |
| Scenario `runtime-selftest` | 35.0 s |
| Scenario `runtime-trap` | 2.6 s |
| Each of the other failure scenarios | 0.1 s |
| Suites `memory`, `capabilities` and `ipc` | 0.6 s, 0.2 s and 0.5 s |
| Suite `processes`, scenarios `cases` and `spawn-failures` | 1.5 s and 0.3 s |
| Scenario `cycles` | 61.5 s |
| Suite `scheduling`, scenarios `cases` and `schedule-trace` | 1.2 s and 0.1 s |
| Suite `devices`, scenarios `cases`, `services` and `without-entropy` | 0.1 s, 0.4 s and 0.2 s |
| Suite `vfs` | 1.6 s |
| Suite `storage`, scenario `cases` | 3.0 s |
| Suite `storage`, scenarios `persistence-write` and `persistence-verify` | 0.4 s each |
| Suite `storage`, each of the other five scenarios | 0.2 s |
| Suite `network` | 12.9 s |
| Suite `network-interop`, scenarios `interop-clean-link` and `interop-impaired-link` | 2.4 s and 4.2 s |
| Suite `applications` | 4.9 s |
| Suite `supervision`, scenario `supervision-cases` | 2.3 s |
| Suite `supervision`, scenario `network-absent` | 0.3 s |
| Suite `supervision`, each of the four refused configuration scenarios | 0.2 s |
| Suite `system-journey`, first and second boot | 3.4 s and 0.5 s |
| Suite `release-journey`, each of the five scenarios | From 0.4 s to 0.5 s |
| `fault-test --suite device-reset`, scenario `stalled-device` | 7.2 s |
| `fault-test --suite storage-crash`, scenario `flush-trace` | 0.6 s |
| `fault-test --suite network-faults` | 2.5 s |
| `repeat-boot`, each of the 1,000 boots | Minimum of 0.27 s, median of 0.29 s, p99 of 0.38 s and maximum of 0.46 s |
| Boot up to the shell ready and the orderly shutdown | 0.46 s, for a budget of 15 s |
| Memory committed at rest | 22.9 MiB, for a budget of 96 MiB |
| Memory committed under load | 31.2 MiB, for a budget of 224 MiB |
| Small IPC round trip | p50 of 0.91 ms, p99 of 1.63 ms and maximum of 2.03 ms in 10,000 calls, for a budget of 25 ms at p99 |
| Ready-task response | p50 of 33.1 ms, p99 of 80.0 ms and maximum of 82.5 ms in 400 samples, for a budget of 250 ms at p99 |
| Pause of the supervisor collector | p99 and maximum of 2.72 ms in 3 collections, for budgets of 25 ms and 100 ms |
| Release after exit | p50 of 0.71 ms and maximum of 1.07 ms in 50 exits, for a budget of 1 s |
| Full build | 34 s |
| `kernel.elf` | 1,643,184 bytes in the file. Loadable segments: 116,812 bytes of code, 77,592 of read-only data and 1,046,368 without content in the file, from the static tables of the supervisor |
| `kernel-selftest.elf` | 1,740,744 bytes in the file |
| `init.img` | 431,655 bytes |
| `tests.img` | 626,047 bytes |
| `boot.img` | 65,536 bytes |

The collector pauses come from few collections, which is why the p99 and the maximum coincide. The boot measurements are from the host clock, and those of IPC, response and release are from the guest clock.

## Rules

- Changing a budget requires updating the profile, repeating the affected tests and recording the new baseline here.
- A limit does not go up to hide a leak or a regression.
- Outliers stay in the report. The average does not replace the worst case.
