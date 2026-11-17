# Compatibility policy

[Português](compatibility.md)

Five system interfaces are frozen at version 1.0. This page defines their scope, compatible changes and the process for changing them.

## Frozen interfaces

| Interface | Scope | Version stored in data | Specification |
| --- | --- | --- | --- |
| `abi` | Syscall numbers, error codes, rights, handles, process status, device layout, message header and process creation request | `VERSION = 1` in message headers and `REQUEST_VERSION = 1` in creation requests | `specs/abi/` |
| `service-protocol` | Console, entropy, block, file, network, control, launch and power operations and payloads | Message-header version | `specs/abi/device-services.en.md`, `specs/filesystem/file-service.en.md`, `specs/network/socket-service.en.md`, `specs/system/control-service.en.md` |
| `image-manifest` | Boot image and user-image header | `FORMAT_VERSION = 1` and `ABI_VERSION = 1` in boot images; `VERSION = 2` in user-image headers | `specs/filesystem/boot-image.en.md`, `specs/abi/user-image.en.md` |
| `configuration` | System-configuration syntax, fields, limits and errors | `version = 1` in `[system]` | `specs/system/configuration.en.md` |
| `persistent-format` | Volume superblocks, indices, directories and names | `FORMAT_VERSION = 1` in superblocks | `specs/filesystem/volume-format.en.md` |

`specs/frozen-interfaces.toml` lists each interface's source files and their combined SHA-256. `kernel-tool verify-interfaces` recalculates digests and fails if one changed. It runs in CI, `kernel-tool verify --all` and `kernel-tool release-check`.

A digest is an alarm, not proof of compatibility. It also changes for behavior-preserving edits such as constant renames. Whoever changes a frozen file must classify the change under this policy.

## Compatible changes

Allowed within 1.x, incrementing the interface minor version:

- New syscall, service operation, error code or counter using a previously unused number.
- New configuration field whose default preserves earlier behavior.
- New flag bit in a currently zero-required field, when an unaware implementation rejects it with a defined error.

A 1.x component returns `UNSUPPORTED` for unknown input. It neither ignores nor reinterprets it.

## Incompatible changes

Require an interface major-version increment and an updated version in serialized data:

- Removing or renumbering syscalls, operations, errors, rights or counters.
- Changing a field's size, order or meaning.
- Changing volume, boot-image or user-image-header layout.
- Accepting input previously rejected for security reasons.

An incompatible change requires an ADR, updated specifications and conformance tests in the same change, and a new system major version.

## Data volume

- A release reads and writes only formats declared in its bundle's `manifest.json` `volume_formats`.
- Unknown formats are not mounted. Boot proceeds without the volume and nothing is written: `unknown-format-is-not-mounted` in `release-journey` and `unknown-format-version` in `storage`.
- Updates replace images, never the volume. `kernel-tool update` rejects bundles that cannot read the installed volume format.
- Rollback is allowed only when the previous release reads the current volume format. `kernel-tool rollback` checks this before changing images.
- A new format arrives with a release that reads both formats. Conversion is separate, requires a volume copy and an explicit operator request. Series 1.x has no conversion.

## Changing a frozen interface

1. Classify the change under this policy.
2. Update the specification, interface version in `specs/frozen-interfaces.toml` and, where applicable, serialized version.
3. Update conformance tests and scenarios exercising the interface.
4. Run `uv run kernel-tool verify-interfaces --freeze` and include the rewritten file in the same change.
5. Record an ADR for an incompatible change.

## Not frozen

Console lines are diagnostics. The same-version `kernel-tool` is the supported reader, and text may change between minor versions. Shell commands may gain options. Reports under `build/` are not interfaces.
