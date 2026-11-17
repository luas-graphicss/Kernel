# Services and configuration

[Português](services-and-configuration.md)

How to read the state of the services, what happens when one of them fails and how to change the system configuration. The complete rules are in `specs/system/configuration.en.md` and in `specs/system/control-service.en.md`.

## What runs

The system manager starts five services, in the order of the dependencies the configuration declares:

| Service | Does | Needs |
| --- | --- | --- |
| `console` | Input and output through the serial port | Nothing |
| `entropy` | Random bytes from the device | Nothing |
| `storage` | Disks and files | Nothing |
| `network` | Interface, IPv4 stack and sockets | `entropy` |
| `shell` | The prompt | `console` and `storage` |

`ps` shows each one:

```
ps: service=network state=ready restarts=0/3 starts=1
```

`restarts=0/3` are the failures within the current window and the limit from the configuration. `starts` counts how many times the service started since boot.

| State | Meaning | What to do |
| --- | --- | --- |
| `ready` | Running | Nothing |
| `starting` | Process created, not answering yet | Wait up to 20 seconds |
| `blocked` | Waits for a service it needs | Look at the state of the other service |
| `degraded` | Failed more times than the window allows and stayed stopped | Fix the cause and restart the system |
| `stopped` | Stopped in order, during shutdown | Nothing |

## When a service fails

The manager notices the death of a service within 50 ms and writes on the console what it does. This excerpt is from the `restart-with-a-pending-request` case of the `supervision` suite, in which the `client` service depends on `base` and `base` is ended by force:

```
system: service=base state=failed reason=killed value=0
system: service=client state=stopped clean=1
system: service=base state=restarting attempt=1 limit=2
system: service=base state=ready
system: service=client state=ready
```

Before restarting a service, the manager stops those that depend on it and starts them again afterwards. Whoever was using the old instance receives an error on the pending operations and needs to open again what it had: files, sockets, connections. Nothing is retried on its own.

The limit exists so that a broken service does not loop. The image in the repository allows 2 restarts in 60 seconds for `console`, `entropy` and `storage`, and 3 for `network` and `shell`. Once the limit is exhausted:

```
system: service=network state=degraded restarts=3 window-seconds=60
system: state=degraded
```

The system carries on with what is left. Without a network device, which is what `kernel-tool run --without-network` produces, the boot looks like this:

```
system: devices serial=1 entropy=1 network=0 block=2
system: configuration=accepted name=kernel services=5
system: service=console state=ready
system: service=entropy state=ready
system: service=network state=failed stage=start
system: service=network state=restarting attempt=1 limit=3
system: service=network state=failed stage=start
system: service=network state=restarting attempt=2 limit=3
system: service=network state=failed stage=start
system: service=network state=restarting attempt=3 limit=3
system: service=network state=failed stage=start
system: service=network state=degraded restarts=3 window-seconds=60
system: service=shell state=ready
system: state=degraded
```

`net` and `ping` return `BAD_STATE`, and files, programs and shutdown work. A degraded service only comes back with a new boot.

`console` and `storage` are different: the shell depends on both. If one of them degrades, the shell stays `blocked` and there is no prompt. The state remains visible in the `system:` lines, which go out through the kernel's diagnostic console and not through the service.

## Changing the configuration

The configuration is the file `config/system/system.conf`, copied to `system/config` in the boot image. The system reads it once, at boot, and there is no command to change it while running.

1. Edit `config/system/system.conf`.
2. Check before starting: `uv run pytest tests/conformance/test_configuration.py`. The first test loads the file of the repository with the same validator as the guest.
3. `uv run kernel-tool build` builds the boot image again.
4. `uv run kernel-tool run`.

Common changes:

| To | Change |
| --- | --- |
| Change the address | `address`, `prefix` and `gateway` in `[interface]`. The gateway must be in the same subnet |
| Remove the network | Remove `[service.network]` and `[interface]`. The two sections leave together |
| Allow more applications | `limit` in `[access.application]`, up to 8. Each application is a process, and the profile admits 16 in total |
| Give an application more memory | `heap_bytes` in `[access.application]`, up to 4 MiB, in multiples of 4096 |
| Keep applications from writing | `files = "read"` in `[access.application]` |
| Keep applications from listening on ports | Remove `"listen"` from `network` in `[access.application]` |
| Tolerate more failures of a service | `restarts` and `window_seconds` in `[service.<name>]` |

## When the configuration is refused

The system does not start with an invalid configuration. It does not apply the part it understood: it reports the first error, starts no service and ends.

```
system: configuration=rejected reason=gateway-off-link subject=interface.gateway
policy: reaped=init reason=exit value=1 live=0 memory-in-use=0
policy: resources=released
kernel: status=failed
```

`reason` states the rule and `subject` states where: the line, the section, the key or the service. The complete table is in `specs/system/configuration.en.md`. The most common ones:

| `reason` | Means |
| --- | --- |
| `missing-document` | The boot image has no `system/config` |
| `syntax` | The line named is not a section, an assignment or a comment |
| `unknown-key`, `unknown-section` | A mistyped name, or a key in the wrong section |
| `out-of-range` | A number outside the range of the key, or a heap that is not a multiple of 4096 |
| `dependency-cycle` | Two services that depend on each other |
| `missing-dependency` | `network` without `entropy` in `needs`, or `shell` without `console` and `storage` |
| `gateway-off-link` | Gateway outside the subnet of the address |
| `process-budget` | Services and applications add up to more processes than the profile admits |

To get back to a system that starts, fix the file and build the image again. The data volume is not touched by a refusal.

## Shutdown

`shutdown` and `shutdown restart` stop the services in the reverse order of their start. Each service has 20 seconds to finish what it is doing. The sequence and the console lines are in `system-operation.en.md`.
