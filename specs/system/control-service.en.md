# System manager and control service

[Português](control-service.md)

`kernel_services.manager.main` is the first user process when boot receives `init=kernel_services.manager.main`, as supplied by `kernel-tool run`. It runs in U-mode at priority 1 and alone receives the system capability. It reads configuration, starts and supervises services, serves the shell's control endpoint, launches applications and conducts shutdown. See `configuration.en.md` and `applications.en.md`.

Without the argument, `kernel_services.init.main` remains the default: it starts device services, checks them and exits. This is what the `bootstrap` suite's `boot` scenario runs.

## Startup

The manager records its actions in `system:` console lines.

1. `system: manager=started runtime=micropython privilege=user`.
2. Read inventory and claim devices: `system: devices serial=1 entropy=1 network=1 block=2`.
3. Start storage: one block service per disk plus the file service, to read `boot/system/config`.
4. Validate configuration. Rejection stops storage and exits with failure. Acceptance prints `system: configuration=accepted name=kernel services=5`.
5. Start services in dependency order; each reports `system: service=<name> state=ready`.
6. Print `system: state=running`, or `system: state=degraded` if any service did not become ready.

A service becomes ready when its process registers within 20 seconds. It receives only its required grants:

| Service | Processes | Receives |
| --- | --- | --- |
| `console` | 1 | Serial port |
| `entropy` | 1 | Entropy device |
| `storage` | 3 | One disk per block service; block-service endpoints for the file service |
| `network` | 1 | Network device, entropy-service endpoint and interface configuration |
| `shell` | 1 | Control endpoint with `SEND` |

No service receives the system capability.

## States

| Value | Service state | Meaning |
| --- | --- | --- |
| 0 | `stopped` | Not started or cleanly stopped |
| 1 | `starting` | Process created, not yet registered |
| 2 | `ready` | Registered and running |
| 3 | `degraded` | Restart budget exhausted; remains stopped |
| 4 | `blocked` | Waiting for a dependency |

| Value | System state | Meaning |
| --- | --- | --- |
| 0 | `starting` | Configuration not yet applied |
| 1 | `running` | All configured services `ready` |
| 2 | `degraded` | At least one service not `ready` |
| 3 | `stopping` | Shutdown requested |

## Supervision

On each iteration, at most 50 ms apart, the manager checks every ready service's process.

Service death prints `system: service=<name> state=failed` with exit reason and value. Direct and indirect dependents stop in reverse startup order. The manager restarts the failed service if policy allows, then its dependents.

Policy permits `restarts` failures within `window_seconds`; older failures stop counting. Within budget it prints `system: service=<name> state=restarting attempt=N limit=M`. Exhaustion produces `system: service=<name> state=degraded restarts=N window-seconds=W`, with no further restarts in that window. There is no unbounded restart loop.

Unavailable dependencies leave a service `blocked`, with `system: service=<name> state=blocked waiting-for=<other>`. Unrelated services continue: without a network device, `network` degrades while storage, console and shell remain usable.

New instances receive exactly the previous grants. Old-instance clients receive `PEER_CLOSED` on pending calls and `INVALID_HANDLE` for old handles; no operation is replayed for them. The shell discards stale handles and requests the endpoint again.

## Control service

The manager creates the control endpoint and grants it only to the shell. Possession is not authorization: the manager records admitted process identities and `[access.shell]` rights, then checks supervisor-provided sender identity on every message. Unlisted processes receive `ACCESS_DENIED` for every operation.

| Right | Operations |
| --- | --- |
| `observe` | `STATUS`, `APPLICATIONS`, `WAIT`, `MEMORY` |
| `launch` | `LAUNCH` |
| `signal` | `SIGNAL` |
| `power` | `POWER` |

| Number | Operation | Request | Response |
| --- | --- | --- | --- |
| 16 | `STATUS` | Empty | System and service states |
| 17 | `ENDPOINT` | Service name, 1–32 bytes: `console`, `storage`, `network` | Empty, service-endpoint capability with `SEND` and `DELEGATE` |
| 18 | `ACCESS` | `storage` or `network` | Empty, configured file-namespace or network-access capability |
| 19 | `LAUNCH` | Command line, 1–63 bytes | Application identity, 4 bytes |
| 20 | `APPLICATIONS` | Empty | Entry per known application |
| 21 | `SIGNAL` | Identity in 4 bytes | Empty; application terminated |
| 22 | `WAIT` | Identity in 4, wait nanoseconds in 8 | Exit reason in 1, value in 4 |
| 23 | `MEMORY` | Empty | `system_counters` values, 8 bytes each |
| 24 | `POWER` | Action in 1 byte: 0 shutdown, 1 restart | Empty; shutdown begins afterward |

`STATUS` returns system state in 1 byte, service count in 1, then per service: state, failures within window, restart limit, startup count and name length in 1 byte each, followed by the name.

`APPLICATIONS` returns per application: identity in 4 bytes, state in 1, reason in 1, value in 4, command length in 2, then command. State 1 is `running`, 2 is `exited`. Reason and value follow `process_wait` in `specs/abi/processes.en.md`.

| Operation | Condition | Error |
| --- | --- | --- |
| Any | Unadmitted process or missing right | `ACCESS_DENIED` |
| Any | Capability attached or malformed body | `INVALID_ARGUMENT` |
| `ENDPOINT`, `ACCESS` | Access policy does not grant the service | `ACCESS_DENIED` |
| `ENDPOINT`, `ACCESS` | Service not ready | `BAD_STATE` |
| `ENDPOINT` | Unknown service name | `NOT_FOUND` |
| `LAUNCH` | Shutdown underway | `BAD_STATE` |
| `LAUNCH` | Application limit reached | `LIMIT_EXCEEDED` |
| `LAUNCH` | Empty, over-63-byte, space-prefixed or nonprintable-ASCII command | `INVALID_ARGUMENT` |
| `SIGNAL`, `WAIT` | Unknown identity | `NOT_FOUND` |
| `SIGNAL` | Already-exited application | `BAD_STATE` |
| `WAIT` | Timeout, or zero wait while running | `TIMED_OUT` |
| `WAIT` | Eight waits already pending | `LIMIT_EXCEEDED` |
| `WAIT` | Shutdown began | `CANCELLED` |
| `POWER` | Unknown action | `INVALID_ARGUMENT` |
| `POWER` | Shutdown already requested | `BAD_STATE` |

The manager retains the eight most recently exited applications in addition to running ones. Older identities return `NOT_FOUND`.

## Orderly shutdown

`POWER` is the only requested shutdown/restart path. Both use the same sequence:

1. `system: shutdown=started action=shutdown` or `action=restart`; subsequent `LAUNCH` returns `BAD_STATE`.
2. Terminate running applications, each reporting `system: application=N state=exited reason=killed value=0`. Pending waits get `CANCELLED`. Print `system: shutdown=applications stopped=N`.
3. Send `STOP` in reverse startup order: `shell`, `network`, `storage`, `entropy`, `console`. Network ends sessions and aborts connections. Files synchronizes volumes before replying. Each gets 20 seconds; nonresponders are killed and report `clean=0`.
4. Call `system_power` with the requested action; print `system: shutdown=complete clean=1`, or `clean=0` if any service failed to stop cleanly.
5. Manager exits. Supervisor checks resource release, prints `kernel: power=restart` for restart, then `kernel: status=ok`, and requests firmware shutdown or cold reboot.

`system_power`, described in `specs/abi/syscalls.en.md`, only records the action. It executes at step 5 only on successful termination: failed boots shut down even if restart was requested.

## Evidence

`tests/conformance/test_service_supervision.py` covers start/stop order, restart budget/window, degraded state and dependent restarts. `tests/conformance/test_control_protocol.py` covers these formats.

QEMU `supervision` cases are `dependency-order`, `readiness-and-degraded-state`, `restart-with-a-pending-request`, `restart-budget` and `restart-window`. Its `network-absent` scenario requires degradation after three attempts while shell and storage remain usable. `applications` covers `LAUNCH`, `SIGNAL`, `WAIT` and limits. `system-journey` covers shutdown with an active application, restart and a second boot reading first-boot data.
