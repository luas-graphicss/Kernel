# Qualifying and assembling a release

[Português](release-procedure.md)

A release comes out of a build whose evidence was all produced for the same images. Each command below writes a report with the SHA-256 of `kernel.elf`, `init.img` and `boot.img`. `release-check` only accepts reports of those images: after any change that alters one of them, the earlier evidence no longer counts. The hashes do not change with the location of the tree, of the build directory or of the toolchain cache.

## Sequence

```sh
uv run kernel-tool build --profile qemu-riscv64
uv run kernel-tool verify --all --profile qemu-riscv64
uv run kernel-tool repeat-boot --profile qemu-riscv64 --count 1000
uv run kernel-tool benchmark --profile qemu-riscv64
uv run kernel-tool reproduce-build --profile qemu-riscv64
uv run kernel-tool fuzz --all --budget-hours 24
uv run kernel-tool soak --profile qemu-riscv64 --hours 24
uv run kernel-tool release-check --profile qemu-riscv64
```

| Command | What it does | Report |
| --- | --- | --- |
| `verify --all` | Runs the whole matrix: formatting, lint, types, host tests, frozen interfaces, native tests, fuzzing corpus, build, image inspection, every suite on QEMU, the fault suites and the volume corpus. A verification that could not run stays `incomplete`, and the command ends with status 3 | `build/qemu-riscv64/qualification/verification.json` |
| `repeat-boot` | Starts the release image up to the shell and shuts down in order, as many times as requested. It keeps the duration, the hash of the transcript and, on failure, the transcript of each boot | `qualification/boots.json` |
| `benchmark` | Measures boot, memory, IPC, ready-task response, pauses of the supervisor collector and release after exit, and compares them with the budgets | `qualification/measurements.json` |
| `reproduce-build` | Builds twice in empty directories and requires images equal to each other and equal to those of the current build | `qualification/reproduction.json` |
| `fuzz` | Mutates inputs of each family for the time requested. The time is for each family, not split among them | `build/fuzz/ledger.json` and `build/fuzz/report.json` |
| `soak` | Keeps a single boot under mixed load for the time requested | `qualification/soak.json` |
| `release-check` | Evaluates the gates, assembles the bundle and ends with a non-zero status while any gate is open | `release/kernel-<version>-qemu-riscv64/release-report.json` |

`verify --area <area>` runs part of the matrix. A partial run does not satisfy the correctness gate.

Run one command at a time over a build directory. Those that start QEMU use the same scenario volumes, and two at the same time compete for those files: one of them ends with status 3, and its report stays incomplete.

## Fuzzing

The families are `boot`, `interface`, `storage` and `network`. The native targets are built for the host with AddressSanitizer, UndefinedBehaviorSanitizer and block coverage; the Python targets run the guest code on CPython with line coverage. A target fails by crashing, by hanging or by breaking an invariant the target itself checks.

Time accumulates across sessions in `build/fuzz/ledger.json`, per target and per version of the code the target exercises. When that code changes, the time of the target goes back to zero.

- `uv run kernel-tool replay-corpus --all` runs the seeds, the corpus in `tests/fuzz/corpus/` and the regressions in `tests/fuzz/regressions/`, without mutating.
- `uv run kernel-tool promote-corpus --all` copies to `tests/fuzz/corpus/` the inputs of the last campaign that reach new code.
- A failure is kept in `build/fuzz/findings/<family>/<target>/`, with the minimized input in hexadecimal and the diagnostic. After the fix, the input goes to `tests/fuzz/regressions/<family>/<target>.hex`, one per line.

## Soak

One boot only, with a new volume, and rounds until the time runs out. Each round writes a file, counts its words in an application, downloads a file from the peer over TCP, runs `ping`, exhausts the heap of an application, kills an application stuck in a loop and another stuck on files, synchronizes the volume and reads the system counters.

The soak fails when a command does not end as expected, when `trap:`, `panic:`, a leak or a deadlock appears, when the shutdown is not clean, when the volume does not mount afterwards, or when free frames, objects, capabilities, endpoints, buffers or the duration of a round get persistently worse after the first 8 rounds. The worsening is persistent when the median and the extreme of the second half of the samples are worse than those of the first half.

`--without-network` leaves the network out. Such a run serves development and does not satisfy the gate.

## Gates

| Gate | Requirement | Where it comes from |
| --- | --- | --- |
| `correctness` | The whole matrix, without a failure and without an incomplete verification | `verify --all` |
| `boot` | 1,000 boots without a failure | `repeat-boot` |
| `lifecycle` | 10,000 process and IPC cycles without growth | `processes` suite in `verify --all` |
| `stability` | 24 hours in one boot, with the network, without a failure and without persistent worsening | `soak --hours 24` |
| `fuzzing` | 24 hours accumulated in each family and no open failure | `fuzz` |
| `isolation` | The `memory`, `capabilities`, `ipc` and `devices` suites and the `device-reset` faults | `verify --all` |
| `durability` | The `storage` suite, the `storage-crash` faults and the volume corpus | `verify --all` |
| `network` | The `network` and `network-interop` suites and the `network-faults` faults | `verify --all` |
| `dependencies` | A review of security advisories for the pinned version of each component and accepted licenses | `config/release/advisories.toml` and the license inventory |
| `distribution` | Identical clean builds and the `release-journey` and `system-journey` suites | `reproduce-build` and `verify --all` |
| `interfaces` | Frozen interfaces equal to the recorded digests | `specs/frozen-interfaces.toml` |
| `budgets` | Every budget measured and met | `benchmark` |

`release-check` does not publish, create a tag or use a key. Publishing, tagging the version and signing with the release key depend on authorization from whoever answers for the project.

## Signing

The release key stays outside the repository. `release-sign` refuses a key that is inside it.

```sh
ssh-keygen -t ed25519 -f <outside the repository>/kernel-release -C <identity>
uv run kernel-tool release-sign <bundle> --key <outside the repository>/kernel-release
```

The command checks the checksums and writes `SHA256SUMS.sig`, an OpenSSH signature of `SHA256SUMS` in the `kernel-release` namespace. Only a bundle with `"qualified": true` is signed. `--rehearsal` allows signing an unqualified bundle to rehearse the procedure; the manifest still says it is not a release.

Whoever verifies uses a signers file with one line per public key:

```
<identity> namespaces="kernel-release" ssh-ed25519 AAAA...
```

```sh
uv run kernel-tool release-verify <bundle> --allowed-signers <file> --identity <identity>
```

What stays recorded for audit: `release-report.json`, with each gate and the version; `manifest.json`, with the hashes of the images; and `SHA256SUMS`, which covers both and is what the signature protects.

The signature says the bundle is what the owner of the key assembled. It is not secure boot and does not protect a compromised host.

## Dependencies

`config/release/advisories.toml` records, for each component of `toolchain.lock.toml`, the version reviewed, the sources consulted and each advisory found, with its severity and the reason it applies or not. The gate fails when the pinned version changes without a new review and when a high or critical advisory applies and has no treatment. The review is redone before each release and whenever a pinned version changes.
