# System configuration

[Português](configuration.md)

The system reads one configuration, `system/config` in the boot image, before starting services other than storage. It is text interpreted strictly as data: sections, keys, numbers, strings and lists, never Python. The repository file is `config/system/system.conf`; implementation is `kernel_protocol.configuration`.

The whole document is read and validated before any part is applied. Any error rejects it entirely: no configured service starts, the system reports a reason and ends with `kernel: status=failed`.

## Syntax

```
[service.network]
needs = ["entropy"]
restarts = 3
window_seconds = 60
heap_bytes = 4194304
```

| Element | Rule |
| --- | --- |
| Section | `[name]`, lowercase letters, digits, `_`, `.` and `-`, beginning with a letter; unique names |
| Key | `key = value`, lowercase letters, digits and `_`, beginning with a letter, inside a section; unique within that section |
| Number | Unsigned decimal, up to 18 digits, no leading zero |
| String | Double-quoted, up to 128 bytes, without quotes or backslashes inside |
| List | `["a", "b"]`, up to 16 strings |
| Boolean | `true` or `false`; no current key uses it |
| Comment | Line starting with `#` |

| Limit | Value |
| --- | --- |
| Document | 16,384 bytes, 256 lines |
| Line | 256 bytes, printable ASCII only |
| Sections | 32 |
| Keys per section | 16 |

## Sections

Unknown sections or keys reject the document, as do missing required keys.

### `[system]`

| Key | Type | Rule |
| --- | --- | --- |
| `version` | Number | 1 |
| `name` | String | 1–32 bytes |

### `[interface]`

Required with `[service.network]`, rejected without it.

| Key | Type | Rule |
| --- | --- | --- |
| `address` | String | IPv4 host address, neither subnet network nor broadcast |
| `prefix` | Number | 8–30 |
| `gateway` | Optional string | Same-subnet host other than `address` |
| `mtu` | Number | 576–1500 |

### `[service.<name>]`

Accepted names: `console`, `entropy`, `storage`, `network`, `shell`. The first three are mandatory.

| Key | Type | Rule |
| --- | --- | --- |
| `needs` | Optional list | Services required to be ready first. `network` must declare `entropy`; `shell` must declare `console` and `storage` |
| `restarts` | Number | 0–16 restarts per window |
| `window_seconds` | Number | 1–3600 |
| `priority` | Optional number | 0–3, default 2 |
| `heap_bytes` | Optional number | 4096–4,194,304, multiple of 4096; default 1,048,576 |

### `[access.shell]` and `[access.application]`

These define shell and application grants. Anything not listed is not granted.

| Key | Type | Rule |
| --- | --- | --- |
| `network` | Optional list | Rights from `specs/network/socket-service.en.md`: `connect`, `listen`, `datagram`, `echo`, `inspect`, `delegate` |
| `files` | Optional string | `none`, `read`, `read-write`; default `none` |
| `control` | Optional list, shell only | `observe`, `launch`, `signal`, `power`, from `control-service.en.md` |
| `limit` | Optional number, application only | 0–8 concurrent applications; default 0 |
| `heap_bytes` | Optional number, application only | Same as services |
| `priority` | Optional number, application only | Same as services |

## Validation

After parsing, the validator checks:

- Dependencies form a startup order; cycles reject the document.
- Service processes plus application limit plus the manager fit the profile process budget. Storage counts as three processes; other services count as one.

| Reason | Reported subject | Cause |
| --- | --- | --- |
| `missing-document` | `boot/system/config` | File absent |
| `unreadable` | Error name | File read failed |
| `storage-unavailable` | `boot` | Boot image not mounted |
| `syntax` | `line-N` | Not a section, assignment or comment, or malformed value |
| `too-large` | `document`, `lines`, `line-N` | Syntax limit exceeded |
| `duplicate` | Section or key | Repeated name |
| `unknown-section`, `unknown-key` | Section or `section.key` | Unknown name |
| `missing-section`, `missing-key` | Section or `section.key` | Required but absent |
| `wrong-type` | `section.key` | Wrong value type |
| `out-of-range` | `section.key` | Out of range, non-page-aligned heap or duplicate list item |
| `unsupported-version` | `system.version` | Version other than 1 |
| `unknown-service`, `missing-service` | Service | Unknown service or missing required service |
| `unknown-dependency`, `missing-dependency` | `service.dependency` | Undeclared dependency or absent mandatory dependency |
| `self-dependency`, `dependency-cycle` | Service | Self-dependency or cycle |
| `invalid-address` | `section.key` | Not an IPv4 host address |
| `gateway-off-link` | `interface.gateway` | Off-subnet gateway or gateway equal to address |
| `unknown-right` | `section.key` | Unknown right |
| `process-budget` | Requested count | Exceeds profile allowance |

Rejection is a single console line:

```
system: configuration=rejected reason=out-of-range subject=service.network.heap_bytes
```

Accepted configuration prints `system: configuration=accepted name=kernel services=5`.

## What configuration does not do

It is not reloaded at runtime and there is no live-update command. Changes require a new boot image and restart. The boot image is read-only, so guest processes cannot modify the file.

## Evidence

`tests/conformance/test_configuration.py` covers syntax, limits, every rejection reason, startup order and non-evaluation of values. The `supervision` suite boots four invalid images: missing file, circular dependency, excessive heap and off-subnet gateway. Each scenario requires the rejection line and forbids service-started, system-state and shell lines.
