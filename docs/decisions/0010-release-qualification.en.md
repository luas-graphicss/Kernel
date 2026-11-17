# ADR 0010: Qualification and distribution

[Português](0010-release-qualification.md)

Status: accepted.

## Context

The system had every planned function and a per-change verification in CI. What was missing is what says whether a build can be distributed: long evidence, such as fuzzing and soak, measurements against the budgets, versioned interfaces, a verifiable bundle and an installation procedure.

Part of that evidence takes days of machine time. It was necessary to decide how it is tied to a build, what happens when it is missing, and which tools the project brings instead of depending on external services.

## Decision

The evidence belongs to images, not to a commit. Each qualification command records the SHA-256 of `kernel.elf`, `init.img` and `boot.img`, and `release-check` refuses a report of other images. The images do not depend on where the tree, the build directory, the MicroPython source and the compiler are: the compilation replaces the four paths with fixed names, and `verify-artifacts` fails an image that carries any of them. That is why the evidence produced on one machine holds for the same images compiled on another.

An open gate fails the release. `release-check` assembles the bundle anyway, so that the installation can be rehearsed, but writes `"qualified": false` in the manifest and ends with a non-zero status. `release-sign` does not sign such a bundle without `--rehearsal`. There is no option to waive a gate.

The version is `1.0.0rc1` while the 24-hour gates have no evidence. The number `1.0.0` is assigned to the build that passes `release-check`.

Fuzzing is done by an engine of `kernel-tool` itself: deterministic mutation by seed, line coverage for the Python code of the guest and block coverage for the native parsers, reduction of the failing input and a time ledger per target. The GCC of the host does not ship libFuzzer, and the protocol code is Python, which a C fuzzer does not instrument. The time ledger is reset when the code of a target changes, so that hours spent on an earlier version do not count.

The soak is a single boot, operated through the console as an operator would. Restarting the system every few minutes would hide resource growth, which is what a soak looks for.

The pauses of the supervisor collector are measured in native code, by a fixed-size histogram fed by the timer, and read by the policy. The measurement does not allocate and does not change the collection path.

The frozen interfaces are watched by a digest of the files that define them. The digest does not prove compatibility; it forces whoever changes one of those files to decide, by the compatibility policy, what kind of change was made.

The bundle is signed with OpenSSH signatures, by the `ssh-keygen` of the host, over the checksums file. The key stays outside the repository, and the tool refuses a key inside it. There is no dependency on a signing service or on a certificate chain.

Installing, updating and rolling back are operations on a directory with the images and the volume. The compatibility between a release and a volume is decided by the format the release declares it reads, checked against the superblock before swapping the images.

## Consequences

- Any change in code that enters the images invalidates the long evidence. Fixing a failure found at the end of the qualification costs the qualification again.
- The full qualification does not fit in a GitHub-hosted runner, which ends a job in six hours. Fuzzing can accumulate over several sessions, on the machine of whoever prepares the release; the 24-hour soak asks for a machine that stays on for that time.
- The fuzzing engine is simpler than a dedicated fuzzer: it has no per-format dictionaries and no edge coverage. Absence of failures with it says less than it would with a mature tool.
- The dependencies gate depends on a manual review recorded in a file. It guarantees that the review follows the pinned version, not that the review is right.

## Assumptions to confirm

- The budgets were measured on QEMU with TCG in a virtual machine with two processors. The numbers do not hold for physical hardware.
- The persistent-worsening criterion of the soak was exercised with a simulated guest that leaks one frame per round and with short runs of the real system. It has not been observed in a 24-hour run yet.
