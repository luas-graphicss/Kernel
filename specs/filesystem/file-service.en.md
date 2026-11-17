# File service

[Português](file-service.md)

`kernel_services.filesystem.main` is a U-mode process. It mounts volumes, resolves paths and exposes files and directories through IPC. A client can reach only descendants of its granted namespace root.

Messages follow `specs/abi/messages.en.md`. Operation numbers and formats are in `kernel_protocol.services.files`; the client library is `kernel_client.files`.

## Mounts

| Name | Source | Mode |
| --- | --- | --- |
| `tmp` | 64-block in-memory volume recreated at service startup | Read-write, nonpersistent |
| `boot` | `kernel-boot` disk, in `boot-image.en.md` format | Read-only |
| `data` | `kernel-data` disk, in `volume-format.en.md` format | Determined by recovery |

`init` identifies disks by their device-reported serial numbers and supplies the corresponding block-service endpoints. Missing disks are not mounted. A mount failure is recorded with its error; the service starts with its other mounts.

The service root lists mounts only. Creation, renaming and removal there return `READ_ONLY`.

## Namespaces and sessions

A namespace consists of a root directory and rights, delivered as an endpoint capability.

| Bit | Right | Permits |
| --- | --- | --- |
| `0x1` | `NAMESPACE_READ` | Opening for reading, listing and querying |
| `0x2` | `NAMESPACE_WRITE` | Creating, writing, truncating, renaming and removing |
| `0x4` | `NAMESPACE_DELEGATE` | Creating narrower namespaces |

To use a namespace, the client sends `ENTER` through its capability, then calls `ENTER` on the service endpoint. Supervisor-provided sender identity links the two. The response contains service instance, session token and rights. Subsequent operations carry the instance and token or an open-file handle.

`SUBSPACE` creates a namespace rooted below the current root with a subset of current rights. Requesting more returns `ACCESS_DENIED`. The new namespace arrives as a capability that may be granted to another process. `DROP` destroys it and all descendant namespaces, sessions and their open files. `LEAVE` ends a session.

Only the service supervisor receives the full-rights root namespace, through `ROOT`.

| Limit | Value |
| --- | --- |
| Namespaces | 16 |
| Sessions | 16 |
| Open files and directories | 64 |
| Pending entry requests | 16 |

Exhaustion returns `LIMIT_EXCEEDED`.

## Paths

Paths are `/`-separated names resolved from the namespace root.

- Empty components and `.` are ignored.
- `..` removes the preceding component. Escaping the namespace root returns `ACCESS_DENIED` without consulting the volume.
- Names follow `volume-format.en.md`: up to 255 bytes of valid UTF-8, no zero byte. Invalid names return `INVALID_ARGUMENT`.
- Paths allow 1024 bytes and 32 resolved components; excess returns `LIMIT_EXCEEDED`.

There is no current directory, symlink or hard link.

## Operations

| Number | Operation | Subject | Request | Response |
| --- | --- | --- | --- | --- |
| 16 | `ROOT` | None | Empty | Root namespace capability; supervisor only |
| 17 | `EVICT` | None | Process identity | Ends its sessions; supervisor only |
| 18 | `ENTER` | None | Empty | Instance, session and rights |
| 19 | `LEAVE` | Session | Empty | Empty |
| 20 | `SUBSPACE` | Session | Rights and path | Namespace number and capability |
| 21 | `DROP` | Session | Namespace number | Empty |
| 22 | `STATUS` | Session | Empty | State of every mount |
| 23 | `OPEN` | Session | Flags and path | Handle, type and size |
| 24 | `CLOSE` | File | Empty | Empty |
| 25 | `READ` | File | Offset and count | Bytes read |
| 26 | `WRITE` | File | Offset and data | Accepted bytes |
| 27 | `TRUNCATE` | File | Size | Empty |
| 28 | `SYNC` | File | Empty | Empty |
| 29 | `STAT` | Session | Path | Type and size |
| 30 | `LIST` | File | Cursor | Next cursor and entries |
| 31 | `MAKE_DIRECTORY` | Session | Path | Empty |
| 32 | `REMOVE` | Session | Path | Empty |
| 33 | `RENAME` | Session | Two paths | Empty |

Requests with a subject start with the service instance and token or handle, 8 bytes each. Error replies set the error flag and carry a 4-byte code.

### Opening

| Flag | Value | Effect |
| --- | --- | --- |
| `OPEN_READ` | `0x01` | Reading |
| `OPEN_WRITE` | `0x02` | Writing and truncating |
| `OPEN_CREATE` | `0x04` | Create if absent |
| `OPEN_EXCLUSIVE` | `0x08` | With `OPEN_CREATE`, return `ALREADY_EXISTS` if present |
| `OPEN_TRUNCATE` | `0x10` | Empty on open; requires `OPEN_WRITE` |
| `OPEN_DIRECTORY` | `0x20` | Open a directory for listing |

Directories require `OPEN_DIRECTORY` and no modifying flags. Opening a file as a directory returns `NOT_A_DIRECTORY`; the reverse returns `IS_A_DIRECTORY`. Read flags require `NAMESPACE_READ`, modifying flags require `NAMESPACE_WRITE`. Modification on read-only mounts returns `READ_ONLY`.

### Reading, writing and listing

Messages carry up to 4032 data bytes. `READ` returns fewer bytes at EOF and none beyond it. `WRITE` returns accepted bytes, possibly fewer than sent when the volume fills; accepting none returns `NO_SPACE`. Writing beyond EOF extends the file; unwritten gaps read as zeros. Zero-byte reads and writes are valid.

`LIST` returns entries in name order with type and size, starting at the cursor. The response supplies the next-page cursor or `0xFFFFFFFF` at the end.

### Handle guarantees

A handle is valid only for its opening process and issuing service instance. Other uses return `INVALID_HANDLE`. Handles name files, not paths: renaming does not affect open handles.

Removing an open file immediately removes its directory entry. Existing readers retain its contents until closing; writing or truncating returns `NOT_FOUND`. Blocks are freed when the last handle closes.

Clients may open the same file concurrently. The service processes one request at a time, so each operation observes the complete results of earlier ones.

## Atomicity and durability

Accepted operations change the in-memory volume. They are not durable until commit; `CLOSE` does not commit.

`SYNC` on any open file or directory commits the entire mount as described in `volume-format.en.md`, replying only after the flush following root publication. This is the system's `fsync`: everything accepted on that mount before the response survives power loss. An orderly service stop also commits, and commits may occur earlier to reclaim blocks.

After a crash, mounting exposes a whole commit: every operation through that commit and none after it.

| Operation | Between commits | Specific errors |
| --- | --- | --- |
| Create file or directory | Name immediately visible to every client | `ALREADY_EXISTS`, `LIMIT_EXCEEDED` for full or overly deep directory, `NO_SPACE` |
| Write | Data immediately visible; old modified-block contents remain on the device until commit | `LIMIT_EXCEEDED` above maximum file size, `NO_SPACE` |
| Truncate | Shrinking discards the tail; extending creates a hole | `LIMIT_EXCEEDED`, `NO_SPACE` |
| Rename | Old name disappears and new name appears atomically. Same-type targets are replaced; directory targets must be empty | `NOT_FOUND`, `IS_A_DIRECTORY`, `NOT_A_DIRECTORY`, `NOT_EMPTY`, `LIMIT_EXCEEDED` for full or overly deep destination, `INVALID_ARGUMENT` for moving a directory into itself, `UNSUPPORTED` across mounts |
| Remove | Name disappears immediately; directories must be empty | `NOT_FOUND`, `NOT_EMPTY` |

Rejection for validation, rights, limits or lack of space changes nothing. Renames are never partially visible to clients or after a crash: either their commit is published or the old name remains.

For `tmp`, `SYNC` performs the same commit in memory and nothing survives service termination. For `boot`, it does nothing.

## Failures

| Situation | Client result |
| --- | --- |
| Read-only mount | `READ_ONLY` for every change |
| Block checksum mismatch | `CORRUPTED` on the reading operation |
| Device error while writing file data | Error on `WRITE` or `TRUNCATE`. A write retains blocks written before the error and the size they cover; a failed truncate leaves the file unchanged. The volume remains usable |
| Device error before root publication | `IO_ERROR` on `SYNC`; previous commit remains durable |
| Device error during root publication | `UNKNOWN_OUTCOME` on `SYNC`; commit may or may not have been published |
| Any operation after either commit failure | `IO_ERROR` until service restart |
| Unresponsive block service | `IO_ERROR` for reads, `UNKNOWN_OUTCOME` for writes and flushes |

`UNKNOWN_OUTCOME` is not permission to retry blindly. After remounting, clients read the state they need to determine what happened.

## Restart

`init` supervises the service: only it may request `ROOT`, `EVICT` and shutdown. Restart stops the old file-service instance, asks each block service to evict the old client, and starts a new instance that mounts volumes through normal recovery.

The new instance has a different identity. Old sessions, handles and namespace capabilities return `INVALID_HANDLE` or `PEER_CLOSED`; no old request is replayed. Clients must enter a namespace again and reopen files.

The `vfs` suite covers paths, files, directories, handles, namespaces, rights, boot image, concurrent clients and service restart. `storage` covers `SYNC` durability, full volumes, block-service restart and rejected or read-only volumes.
