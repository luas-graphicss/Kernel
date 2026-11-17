# Continuous integration

[Português](continuous-integration.md)

The workflow `.github/workflows/ci.yml` runs on every pull request and on every push to `main`. It runs the same commands as local development and publishes nothing.

## Steps

1. `uv sync --frozen`
2. `ruff format --check`, `ruff check`, `mypy --strict host src` and `pytest tests/host tests/conformance`
3. `kernel-tool verify-interfaces`
4. `kernel-tool toolchain`
5. `kernel-tool native-check`
6. `kernel-tool replay-corpus --all` and `kernel-tool fuzz --all --budget-hours 0.05`, which gives three minutes to each family
7. `kernel-tool build`
8. `kernel-tool test --suite bootstrap`
9. `kernel-tool test` with the suites `memory`, `processes`, `capabilities`, `ipc`, `scheduling`, `devices`, `vfs`, `storage`, `network`, `network-interop`, `applications`, `supervision`, `system-journey` and `release-journey`, one step for each
10. `kernel-tool repeat-boot --count 25`, `kernel-tool benchmark` and `kernel-tool soak --hours 0.05`
11. `kernel-tool fault-test` with the suites `device-reset`, `storage-crash` and `network-faults`, one step for each. The second runs the 1,000 default sequences, from seed 1
12. `kernel-tool verify-filesystem --corpus tests/faults/storage`
13. `kernel-tool verify-artifacts` and `kernel-tool reproduce-build`

No step is optional and none uses `continue-on-error`. The reports in `build/qemu-riscv64/reports/` and in `build/qemu-riscv64/qualification/`, `build/fuzz/report.json` and the failures in `build/fuzz/findings/` are attached to the run even when a step fails. The traffic captures of the network suites go along, in `reports/captures/`.

The workflow does not qualify a release. Steps 6 and 10 run short versions of the fuzzing, the repeated boot and the soak, so that a regression shows up in the pull request. The gates of 1,000 boots, of 24 hours of soak and of 24 hours of fuzzing per family do not fit in the time limit of a job and run on the machine of whoever prepares the release, as `release-procedure.en.md` describes. The workflow does not run `release-check` either: without those gates it would always end in failure.

`tests/host/test_ci_workflow.py` reads the workflow and fails when a suite registered in `kernel-tool`, of scenarios or of faults, does not have exactly one step, or when some step uses `continue-on-error`. A new suite enters `kernel-tool` and the workflow in the same change.

## Isolated network

The suites `network`, `network-interop`, `network-faults`, `applications` and `system-journey` connect the guest to a test station that runs on the host, inside a network namespace of its own, with a TAP interface and the Linux TCP/IP stack. Nothing leaves that namespace: it has no route to the runner or to the internet.

A new namespace inherits IPv4 forwarding from the host, and a host that runs Docker usually leaves it on. With it on, the peer answers a packet to an address outside the network with an ICMP error, and the `network` suite expects silence. So the station turns forwarding off in the namespace before creating the interface, and does not come up when it cannot.

`kernel-tool` creates the namespace in three ways, in this order: directly, when it already runs as root; in an unprivileged user namespace, when the host allows it and `/dev/net/tun` is accessible; with `sudo -n`, when sudo does not ask for a password. The `ubuntu-24.04` runner has passwordless sudo, so the third case is available even when the image restricts user namespaces. If none of the three works, the step ends with status 3 and the annotation `Infrastructure unavailable`.

The two sockets that connect the emulator to the station live in a temporary directory of their own for each link, and not in the build directory. A socket address holds 107 bytes, and below `/home/runner/work/Kernel/Kernel` the build path left no room for a scenario name of 27 characters or more.

sudo only starts the station. Build, QEMU and the rest of `kernel-tool` carry on as the runner user. The workflow installs no packages for this and does not change the permissions of the job.

## How to read the result

| Result | Signal |
| --- | --- |
| Success | Every step ends with status 0 |
| Failure | A step ends with a status other than 0; in the `kernel-tool` steps, the annotation is `Check failed` |
| Infrastructure unavailable | A `kernel-tool` step ends with status 3 and the annotation is `Infrastructure unavailable` |

`kernel-tool` uses status 3 when it cannot obtain or run a pinned tool, for example a download that fails. The script `.github/scripts/classify-exit.sh` turns the status into an annotation and into a line of the run summary, and returns the same status. The job goes red in both cases: unavailable infrastructure does not count as a pass.

The formatting, lint, types and pytest steps do not go through the script, because those tools give status 3 another meaning.

## Pinned environment

| Item | Version |
| --- | --- |
| Runner | `ubuntu-24.04` |
| uv | 0.13.5 |
| Python | 3.13, from `.python-version` |
| Guest toolchain | `toolchain.lock.toml`, checked by hash. The cache key is the hash of that file |

The actions are referenced by commit SHA:

| Action | Version | Commit |
| --- | --- | --- |
| `actions/checkout` | v4.2.2 | `11bd71901bbe5b1630ceea73d27597364c9af683` |
| `astral-sh/setup-uv` | v6.8.0 | `d0cc045d04ccac9d8b7881df0226f9e82c39688e` |
| `actions/cache` | v4.2.4 | `0400d5f644dc74513175e3cd8d07132dd4860809` |
| `actions/upload-artifact` | v4.6.2 | `ea165f8d65b6e75b540449e92b4886f43607fa02` |

The workflow asks only for `contents: read`.
