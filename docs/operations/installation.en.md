# Installing, updating and recovering

[Português](installation.md)

The supported target is the QEMU `virt` machine for 64-bit RISC-V, with the OpenSBI firmware, described in `config/profiles/qemu-riscv64.toml`. A release bundle carries images for that target. It is not an ISO, does not boot on a PC and was not qualified on physical hardware.

## What is in a bundle

`kernel-tool release-check` assembles the bundle in `build/qemu-riscv64/release/kernel-<version>-qemu-riscv64/`.

| File | Content |
| --- | --- |
| `kernel.elf` | Kernel image: the project's own native code, the MicroPython runtime of the supervisor and the frozen Python policy |
| `init.img` | User runtime: MicroPython with the services, the drivers, the shell and the application runner frozen in |
| `boot.img` | Read-only boot volume: configuration, release identity, license and the programs in `apps/` |
| `manifest.json` | Version, profile, SHA-256 of each image, frozen interfaces, volume formats read, what is needed besides the bundle and the emulator command line |
| `sbom.spdx.json` | Bill of materials in SPDX 2.3 |
| `licenses.json` and `licenses/` | License inventory and the texts of what is distributed |
| `release-report.json` | Result of each release gate at the time the bundle was assembled |
| `toolchain.lock.toml` and `profile.toml` | Versions and hashes of the emulator, the firmware and the compiler, and the machine profile |
| `SHA256SUMS` | SHA-256 of all the files above |
| `SHA256SUMS.sig` | Signature of the checksums, when the bundle was signed |

The bundle does not carry QEMU or OpenSBI. `manifest.json` states the versions required, and `kernel-tool toolchain` downloads both and checks the hashes.

The binary is not only Python. `sbom.spdx.json` separates what is project code, MicroPython 1.29.0 and the `libgcc` members linked into the images. What each part can do is in `docs/security/trusted-computing-base.en.md`.

A bundle with `"qualified": false` in the manifest was assembled with some release gate open. `release-report.json` says which. It serves to rehearse the installation and is not a release.

## Preparing the host

```sh
uv sync --frozen
uv run kernel-tool toolchain
```

The host requirements are in `README.en.md`. For the network, the host must be able to create a network namespace with a TAP interface.

## Checking the bundle

```sh
uv run kernel-tool release-verify <bundle> --allowed-signers <file> --identity <signer>
```

The command checks the signature of `SHA256SUMS` and then each file against the checksums. Without `--allowed-signers` it checks only the checksums, which detects a corrupted file and does not say where the bundle came from. The signers file and the identity come from whoever publishes the release, through a channel separate from the bundle.

## First installation

```sh
uv run kernel-tool install <bundle> --target <directory>
uv run kernel-tool run --installation <directory>
```

`install` checks the bundle, copies it to `<directory>/releases/` and creates `<directory>/data.img`, an empty volume of 1 MiB. `--allowed-signers` and `--identity` apply here too. If the directory already has a `data.img`, it is kept as it is, as long as the release reads its format. A `data.img` that is not a volume stops the installation and is not changed.

`run --installation` starts the installed images with that volume. Shell usage is in `system-operation.en.md`. On the first boot, `cat boot/system/release` shows the installed version.

Without `kernel-tool`, the `launch` key of `manifest.json` carries the emulator arguments. `{emulator}` is the `qemu-system-riscv64` of the required version and `{firmware}` is OpenSBI. The file names are relative to a directory with the three images and `data.img`. This path does not connect the network.

## Updating

```sh
uv run kernel-tool update <new bundle> --target <directory>
```

The system must be stopped. `update` checks the new bundle, checks that it reads the format of the installed volume, copies it and starts using it. The previous release stays in `releases/`, and the volume is not touched. A bundle that does not read the volume format is refused, and the installation stays as it was. The switch is the replacement of one file, `installation.json`: if the command is interrupted before it, the installation stays on the previous release.

## Going back to the previous release

```sh
uv run kernel-tool rollback --target <directory>
```

`rollback` checks the checksums of the previous release and that it reads the format the volume is in now. If it does, the images are swapped and the volume stays the same, with everything the newer release wrote. If it does not, the command refuses and nothing changes. The format rules are in `specs/compatibility.en.md`.

## Recovering the volume

| Situation | What the system does | What the operator does |
| --- | --- | --- |
| Power loss in the middle of a write | Mounts the last whole commit. What had a confirmed `sync` is there | Nothing |
| Newest root damaged | Mounts the previous root, read-only. Writes answer `READ_ONLY` | Copy the data out and create a new volume |
| Unknown format | Does not mount the volume. The system starts without `data` | Use a release that reads the format, or keep the file and create a new volume |
| Unformatted or corrupted volume | Does not mount it and never formats on its own | Restore a copy or create a new volume |

With the system stopped, `uv run kernel-tool verify-filesystem --image <directory>/data.img` says which of these cases the volume is in, and `uv run kernel-tool inspect-volume <directory>/data.img` lists the superblocks and the tree. For a backup, copy `data.img` with the system stopped. For a new volume, move the old file away and run `uv run kernel-tool create-volume <directory>/data.img`.

## What was exercised

The `release-journey` suite runs on QEMU the first initialization, the update to a boot image of another version over the same volume, the return to the previous image with the data of both, the volume with the damaged root and the volume in an unknown format. `tests/host/test_release_installation.py` covers `install`, `update` and `rollback`, including the refusals. The recorded run is in `docs/acceptance/qualification-and-distribution.en.md`.

## Limits

- The signature checks origin and integrity in distribution. There is no secure boot: a compromised host or firmware is outside what the product guarantees.
- `update` and `rollback` swap the three images together. There is no update of one part.
- The volume has a fixed size, set at creation.
- A single hart, and no qualification outside QEMU with TCG.
