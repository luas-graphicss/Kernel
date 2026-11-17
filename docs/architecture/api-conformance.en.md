# Conformance matrix of the public APIs

[Português](api-conformance.md)

Each line is an operation the system offers to a process, to a program or to whoever operates the console, with its state and the test that exercises it in the guest. What has no line here is not supported. The last section lists what is most often expected of a system and does not exist in this one.

The requirements matrix, in `requirements.en.md`, says what the project needs to deliver. This page says what each interface does today and where that is checked.

The Portuguese page is the one `tests/conformance/test_api_conformance.py` compares with the code. This translation follows it.

## How to read

| State | Meaning |
| --- | --- |
| Supported | Serves any process that presents the capability the operation requires |
| Restricted | Serves only the process that supervises the service: `init` or the system manager. From another process it returns `ACCESS_DENIED` |

An evidence written as `suite/scenario/case` points to a case of a test program that runs in the guest. The command is `kernel-tool test --suite <suite>`, or `kernel-tool fault-test --suite <suite>` for `device-reset`, `storage-crash` and `network-faults`. The result is in `build/qemu-riscv64/reports/<suite>.json`, in the line `test: suite=... case=<case> checks=N result=ok` of the scenario transcript. Without the case, the evidence is the whole scenario, checked by the lines it must produce. A file path points to a test that runs on the host with `pytest`.

A line only counts with the suite passing. The CI workflow runs every suite on each pull request, and `tests/host/test_ci_workflow.py` fails when a suite registered in `kernel-tool` is left without a step in the workflow. The record of the acceptance run, with the counts of each case, is in `docs/acceptance/network-and-operational-environment.en.md`.

`tests/conformance/test_api_conformance.py` compares the Portuguese page with the code. Every syscall, every service operation and every shell command needs exactly one line. Every line needs evidence, and every evidence needs to name a scenario, a case or a file that exists. For a shell command, one of the scenarios cited needs to type the command.

## Syscalls: `kernel_protocol.syscalls.numbers`

ABI version 0, described in `specs/abi/syscalls.en.md` and in the pages it cites. A number outside the table returns `UNSUPPORTED`.

| Syscall | State | Evidence |
| --- | --- | --- |
| `process_exit` | Supported | `processes/cases/exit-status-and-finalization` |
| `debug_write` | Supported | `memory/cases/system-call-pointers` |
| `clock_now` | Supported | `scheduling/cases/clock-limits` |
| `process_yield` | Supported | `scheduling/cases/yield-to-an-equal` |
| `capability_close` | Supported | `capabilities/cases/stale-and-forged-handles` |
| `capability_derive` | Supported | `capabilities/cases/attenuated-delegation` |
| `capability_revoke` | Supported | `capabilities/cases/revocation-with-descendants` |
| `capability_inspect` | Supported | `capabilities/cases/attenuated-delegation` |
| `endpoint_create` | Supported | `ipc/cases/endpoint-ownership` |
| `ipc_send` | Supported | `ipc/cases/delivery-and-transfer`, `ipc/cases/queue-limits` |
| `ipc_receive` | Supported | `ipc/cases/delivery-and-transfer`, `ipc/cases/deadlines` |
| `ipc_call` | Supported | `ipc/cases/reply-correlation`, `ipc/cases/deadlines` |
| `ipc_reply` | Supported | `ipc/cases/reply-correlation` |
| `buffer_create` | Supported | `memory/cases/shared-buffers` |
| `buffer_map` | Supported | `memory/cases/shared-buffers`, `capabilities/cases/mappings-follow-capabilities` |
| `buffer_unmap` | Supported | `memory/cases/shared-buffers` |
| `process_spawn` | Supported | `processes/cases/spawn-authority-and-validation` |
| `process_wait` | Supported | `processes/cases/exit-status-and-finalization` |
| `process_kill` | Supported | `processes/cases/exit-status-and-finalization`, `processes/cases/teardown-releases-resources` |
| `process_interrupt` | Supported | `processes/cases/exit-status-and-finalization`, `ipc/cases/cancellation` |
| `system_counters` | Supported | `memory/cases/system-call-pointers`, `processes/cases/teardown-releases-resources` |
| `device_list` | Supported | `devices/cases/discovery-and-claims` |
| `device_claim` | Supported | `devices/cases/discovery-and-claims` |
| `device_open` | Supported | `devices/cases/feature-negotiation` |
| `device_config` | Supported | `devices/cases/feature-negotiation` |
| `device_submit` | Supported | `devices/cases/descriptor-validation` |
| `device_wait` | Supported | `devices/cases/descriptor-validation`, `device-reset/stalled-device/device-reported-failure` |
| `device_reset` | Supported | `devices/cases/feature-negotiation`, `device-reset/stalled-device/memory-pinned-until-reset` |
| `serial_write` | Supported | `devices/cases/serial-port` |
| `serial_read` | Supported | `devices/cases/serial-port` |
| `system_power` | Supported | `system-journey/journey-first-boot`, `system-journey/journey-second-boot`, `applications/applications` |

`system_power` requires `ADMIN` on the system capability. The two boots of the journey show the restart and the power off requested by the manager, and `applications/applications` shows the refusal to an application.

## Service lifecycle: `kernel_protocol.services.lifecycle`

Described in `specs/abi/device-services.en.md`. It applies to every service of the system.

| Operation | State | Evidence |
| --- | --- | --- |
| `REGISTER` | Supported | `supervision/supervision-cases/dependency-order`, `bootstrap/boot` |
| `STOP` | Restricted | `supervision/supervision-cases/dependency-order`, `devices/services/service-authority` |

## Console service: `kernel_protocol.services.console`

Described in `specs/abi/device-services.en.md`.

| Operation | State | Evidence |
| --- | --- | --- |
| `WRITE` | Supported | `devices/services/console-service` |
| `READ_LINE` | Supported | `devices/services/console-service`, `tests/conformance/test_console.py` |

## Entropy service: `kernel_protocol.services.entropy`

Described in `specs/abi/device-services.en.md`. Without `virtio-rng` the service does not exist, as the scenario `devices/without-entropy` shows, and the network service does not start.

| Operation | State | Evidence |
| --- | --- | --- |
| `READ` | Supported | `devices/services/entropy-service` |

## Block service: `kernel_protocol.services.block`

Described in `specs/abi/device-services.en.md`.

| Operation | State | Evidence |
| --- | --- | --- |
| `ATTACH` | Supported | `devices/services/block-service` |
| `READ` | Supported | `devices/services/block-service` |
| `WRITE` | Supported | `devices/services/block-service` |
| `FLUSH` | Supported | `devices/services/block-service`, `storage/cases/durable-after-sync` |
| `DETACH` | Supported | `devices/services/block-service` |
| `EVICT` | Restricted | `storage/cases/durable-after-sync`, `devices/services/service-authority` |

## File service: `kernel_protocol.services.files`

Described in `specs/filesystem/file-service.en.md`. The volume format is in `specs/filesystem/volume-format.en.md`.

| Operation | State | Evidence |
| --- | --- | --- |
| `ROOT` | Restricted | `vfs/cases`, `devices/services/service-authority` |
| `EVICT` | Restricted | `applications/applications`, `devices/services/service-authority` |
| `ENTER` | Supported | `vfs/cases/namespaces-and-rights` |
| `LEAVE` | Supported | `vfs/cases/open-handles` |
| `SUBSPACE` | Supported | `vfs/cases/namespaces-and-rights`, `vfs/cases/path-resolution` |
| `DROP` | Supported | `vfs/cases/namespaces-and-rights` |
| `STATUS` | Supported | `vfs/cases/boot-image`, `vfs/cases/files-and-directories` |
| `OPEN` | Supported | `vfs/cases/files-and-directories`, `vfs/cases/path-resolution` |
| `CLOSE` | Supported | `vfs/cases/open-handles` |
| `READ` | Supported | `vfs/cases/files-and-directories`, `vfs/cases/boot-image` |
| `WRITE` | Supported | `vfs/cases/files-and-directories`, `storage/cases/volume-full` |
| `TRUNCATE` | Supported | `vfs/cases/files-and-directories` |
| `SYNC` | Supported | `storage/cases/durable-after-sync`, `storage/persistence-verify` |
| `STAT` | Supported | `vfs/cases/files-and-directories` |
| `LIST` | Supported | `vfs/cases/files-and-directories` |
| `MAKE_DIRECTORY` | Supported | `vfs/cases/files-and-directories` |
| `REMOVE` | Supported | `vfs/cases/files-and-directories`, `vfs/cases/open-handles` |
| `RENAME` | Supported | `vfs/cases/files-and-directories` |

The durability of `SYNC` after a crash is checked outside the guest, by `storage-crash/flush-trace`, by the images in `tests/faults/storage` and by `tests/conformance/test_filesystem_recovery.py`.

## Socket service: `kernel_protocol.services.network`

Described in `specs/network/socket-service.en.md`. A process without an access issued by the service neither opens a socket nor reaches the device: that is what `network/network-cases/access-rights` checks with a process that receives only the endpoint.

| Operation | State | Evidence |
| --- | --- | --- |
| `ROOT` | Restricted | `network/network-cases/access-rights` |
| `EVICT` | Restricted | `network/network-cases/access-rights`, `applications/applications` |
| `ENTER` | Supported | `network/network-cases/access-rights` |
| `LEAVE` | Supported | `network/network-cases/socket-quota` |
| `RESTRICT` | Supported | `network/network-cases/access-rights` |
| `STATUS` | Supported | `network/network-cases/interface-and-echo`, `network/network-cases/socket-quota` |
| `NEIGHBORS` | Supported | `network/network-cases/interface-and-echo` |
| `ECHO` | Supported | `network/network-cases/interface-and-echo` |
| `OPEN` | Supported | `network/network-cases/socket-quota`, `network/network-cases/access-rights` |
| `BIND` | Supported | `network/network-cases/datagrams`, `network/network-cases/listening` |
| `LISTEN` | Supported | `network/network-cases/listening` |
| `ACCEPT` | Supported | `network/network-cases/listening`, `network/network-cases/deadlines-cancellation-and-backpressure` |
| `CONNECT` | Supported | `network/network-cases/streams` |
| `SEND` | Supported | `network/network-cases/streams`, `network-interop/interop-impaired-link/upload-verified-by-the-peer` |
| `RECEIVE` | Supported | `network/network-cases/streams`, `network-interop/interop-impaired-link/download-verified-by-checksum` |
| `SEND_TO` | Supported | `network/network-cases/datagrams` |
| `RECEIVE_FROM` | Supported | `network/network-cases/datagrams`, `network-interop/interop-clean-link/fragmented-datagrams` |
| `FINISH` | Supported | `network/network-cases/streams`, `network/network-cases/listening` |
| `CLOSE` | Supported | `network/network-cases/socket-quota` |
| `DESCRIBE` | Supported | `network/network-cases/streams` |
| `REVOKE` | Supported | `network/network-cases/access-rights` |

## Network protocols

What each layer accepts and refuses is in `specs/network/protocols.en.md`. The peer of the suites is the Linux TCP/IP stack of the host, on an isolated network.

| Protocol | State | Evidence |
| --- | --- | --- |
| `virtio-net` driver | Supported, without offload | `network/network-cases/interface-and-echo`, `network-faults/network-faults/device-reset` |
| Ethernet II | Supported, without VLAN | `network-faults/network-faults/malformed-traffic`, `tests/conformance/test_network_link.py` |
| ARP | Supported | `network/network-cases/interface-and-echo`, `tests/conformance/test_network_link.py` |
| IPv4 | Supported, without options and without forwarding | `network/network-cases/datagrams`, `tests/conformance/test_network_malformed.py` |
| Fragmentation and reassembly | Supported, with limits | `network-interop/interop-clean-link/fragmented-datagrams`, `tests/conformance/test_network_reassembly.py` |
| ICMP echo and destination unreachable | Supported | `network/network-cases/interface-and-echo`, `network/network-cases/datagrams` |
| UDP | Supported | `network/network-cases/datagrams` |
| TCP | Supported, without window scaling, SACK and timestamps | `network/network-cases/streams`, `network/network-cases/listening`, `tests/conformance/test_network_tcp.py` |
| TCP with loss, duplication and reordering | Supported | `network-interop/interop-impaired-link/upload-verified-by-the-peer`, `network-interop/interop-impaired-link/relay-through-the-guest` |
| Peer that reads slowly and return of buffers | Supported | `network-interop/interop-impaired-link/slow-reader`, `network-interop/interop-impaired-link/buffers-returned` |
| Flood of connection requests | Contained by the accept queue | `network-faults/network-faults/connection-flood` |
| Link down and back | Supported | `network-faults/network-faults/link-blackout` |
| Service restart with a client waiting | Supported | `network-faults/network-faults/service-restart-with-a-waiting-client` |

## Control service: `kernel_protocol.services.control`

Described in `specs/system/control-service.en.md`. The manager only serves the shell: an application does not receive the control endpoint, and `applications/applications` checks that it is not served through any handle it has or guesses.

| Operation | State | Evidence |
| --- | --- | --- |
| `STATUS` | Supported | `system-journey/journey-first-boot`, `supervision/network-absent` |
| `ENDPOINT` | Supported | `system-journey/journey-first-boot` |
| `ACCESS` | Supported | `system-journey/journey-first-boot` |
| `LAUNCH` | Supported | `applications/applications` |
| `APPLICATIONS` | Supported | `applications/applications` |
| `SIGNAL` | Supported | `applications/applications` |
| `WAIT` | Supported | `applications/applications` |
| `MEMORY` | Supported | `system-journey/journey-first-boot` |
| `POWER` | Supported | `system-journey/journey-first-boot`, `system-journey/journey-second-boot` |

The encoding of each request and reply is checked in `tests/conformance/test_control_protocol.py`.

## Supervision and configuration

Described in `specs/system/control-service.en.md` and in `specs/system/configuration.en.md`.

| Behavior | State | Evidence |
| --- | --- | --- |
| Start in dependency order and stop in the reverse order | Supported | `supervision/supervision-cases/dependency-order` |
| A service that never becomes ready and a visible degraded state | Supported | `supervision/supervision-cases/readiness-and-degraded-state`, `supervision/network-absent` |
| Restart with a pending request | Supported | `supervision/supervision-cases/restart-with-a-pending-request` |
| Restart limit per window | Supported | `supervision/supervision-cases/restart-budget`, `supervision/supervision-cases/restart-window` |
| Missing configuration refused with nothing applied | Supported | `supervision/configuration-missing` |
| Circular dependency refused | Supported | `supervision/configuration-circular` |
| Value above the limit refused | Supported | `supervision/configuration-excessive` |
| Inconsistent configuration refused | Supported | `supervision/configuration-inconsistent` |
| Document validated as a whole before any effect | Supported | `tests/conformance/test_configuration.py`, `tests/conformance/test_service_supervision.py` |
| Orderly shutdown with applications running | Supported | `applications/applications`, `system-journey/journey-first-boot` |

## Applications

Described in `specs/system/applications.en.md`. The API of the program is `kernel_apps.runtime.current()`, with `arguments`, `files` and `network`.

| Behavior | State | Evidence |
| --- | --- | --- |
| Program read from the volume and run in its own process | Supported | `applications/applications`, `system-journey/journey-first-boot` |
| Arguments delivered, without memory of the previous run | Supported | `applications/applications` |
| Only the capabilities of the policy, without administration | Supported | `applications/applications` |
| Exception, syntax error and missing file with status 1 | Supported | `applications/applications` |
| Loop that does not cooperate ended, exhausted heap contained | Supported | `applications/applications` |
| Limit of applications running | Supported | `applications/applications` |
| Files and network used by a program | Supported | `system-journey/journey-first-boot`, `system-journey/journey-second-boot` |

## Shell: `kernel_apps.shell.commands.table`

Described in `docs/operations/system-operation.en.md`. Every command ends with a line `shell: command=<name> status=...`, and a name outside the table returns `UNSUPPORTED`.

| Command | State | Evidence |
| --- | --- | --- |
| `help` | Supported | `system-journey/journey-first-boot` |
| `run` | Supported | `applications/applications`, `system-journey/journey-first-boot` |
| `ps` | Supported | `applications/applications`, `supervision/network-absent` |
| `kill` | Supported | `applications/applications` |
| `wait` | Supported | `applications/applications`, `system-journey/journey-first-boot` |
| `mem` | Supported | `system-journey/journey-first-boot` |
| `ls` | Supported | `system-journey/journey-first-boot`, `system-journey/journey-second-boot` |
| `cat` | Supported | `system-journey/journey-first-boot`, `system-journey/journey-second-boot` |
| `mkdir` | Supported | `system-journey/journey-first-boot` |
| `write` | Supported | `system-journey/journey-first-boot` |
| `rm` | Supported | `system-journey/journey-first-boot`, `system-journey/journey-second-boot` |
| `sync` | Supported | `system-journey/journey-first-boot`, `system-journey/journey-second-boot` |
| `net` | Supported | `system-journey/journey-first-boot`, `supervision/network-absent` |
| `ping` | Supported | `system-journey/journey-first-boot` |
| `shutdown` | Supported | `system-journey/journey-first-boot`, `system-journey/journey-second-boot` |

The splitting of the line into words and its limits are checked in `tests/conformance/test_shell_words.py`. The refusal of a line that went past the console limit is in `tests/conformance/test_shell_interpreter.py`, and the cleanup of a refused `write` in `tests/conformance/test_shell_write.py`.

## Outside what is supported

Nothing on this list has a hidden partial implementation: the interface does not exist, and whoever looks for it gets `UNSUPPORTED`, `ImportError` or the absence of the name.

| Area | Does not exist |
| --- | --- |
| Processes | `fork`, `exec`, signals, threads and more than one hart. A process is born through `process_spawn`, from an image the system already has |
| Shell | Pipes, redirection, variables, wildcards, history and authentication of whoever is on the serial port |
| Files | Current directory, symlinks and hard links |
| Network | IPv6, DHCP, DNS, forwarding, multicast, VLAN, IPv4 options, encrypted traffic and sockets by name or by path |
| TCP | Window scaling, SACK, timestamps, urgent data and keepalive |
| Python | `open`, `input`, `compile`, `sys.argv`, `sys.exit`, `typing` and importing a module from a file of the volume. The other differences are in `runtime-differences.en.md` |
| Configuration | Rereading with the system running and changing a value on the fly |
