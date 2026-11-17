# Applications

[Português](applications.md)

An application is a Python program read from a file and executed in its own U-mode process, with a private interpreter, heap and capabilities. The manager launches it on behalf of the shell through `LAUNCH`, described in `control-service.en.md`.

## Startup

1. The manager validates the running-application limit and command line.
2. It creates a `kernel_apps.runner.main` process with the heap and priority from `[access.application]`.
3. It grants only policy-authorized capabilities:

| Policy | Grants |
| --- | --- |
| `files` other than `none` | File-service endpoint and namespace with configured mode |
| Nonempty `network` rights | Network-service endpoint and access with configured rights |
| Always | Registration endpoint to notify the manager of startup |

4. The runner reads the command's first-word path through its granted namespace and executes the file.

Applications receive no system capability, control endpoint, device or shell capabilities. Memory is not inherited: a new interpreter starts without the launcher's modules, variables or buffers.

## Program

| Rule | Value |
| --- | --- |
| Path | Command's first word, resolved in the application namespace, such as `boot/apps/sysinfo.py` |
| Size | Up to 65,536 bytes |
| Format | Python source, compiled by the process interpreter on load |
| Arguments | Space-separated command words; complete command fits in 63 bytes |
| Execution | File executes with `__name__ == "__main__"`; if it defines `main`, it is called afterward |
| Status | 0 if the file completes and optional `main` does not return `False`; 1 for `False`, an uncaught exception or a read failure |

Uncaught exceptions print a traceback on the diagnostic console. Missing files produce `application: program=<path> error=NOT_FOUND`.

Programs import frozen modules: `kernel_apps.runtime`, `kernel_client`, `kernel_protocol` and utilities from `kernel_services.network.ipv4.address`. Importing modules from volume files is unsupported and raises `ImportError`. CPython differences are documented in `docs/architecture/runtime-differences.en.md`.

## Program API

`kernel_apps.runtime.current()` returns the running application:

| Attribute | Contents |
| --- | --- |
| `arguments` | String list; first item is the program path |
| `files` | `kernel_client.files.Namespace`, or `None` without file access |
| `network` | `kernel_client.sockets.Network`, or `None` without network access |

```python
from kernel_apps import runtime


def main() -> bool:
    application = runtime.current()
    if len(application.arguments) != 2 or application.files is None:
        print("usage: count.py <path>")
        return False
    ...
    return True
```

Files follow `specs/filesystem/file-service.en.md`; networking follows `specs/network/socket-service.en.md`. `print` uses `debug_write` on the diagnostic console.

## Limits and termination

| Limit | Value |
| --- | --- |
| Running applications | `[access.application]` `limit`, up to 8; repository image uses 4 |
| Heap | `[access.application]` `heap_bytes`; repository image uses 2 MiB |
| Sockets and files | Each service's per-process limits |

Heap exhaustion raises `MemoryError` and exits with status 1 without affecting other processes. A noncooperative application is timer-preempted and may be terminated through `SIGNAL`.

On any application exit, the manager asks file and network services to evict its sessions, closing sockets, connections and files. The supervisor releases process memory and capabilities.

## Evidence

The `applications` suite starts programs from `tests/guest/apps` through the shell:

| Program | Demonstrates |
| --- | --- |
| `counter.py`, twice | Arguments delivered; second execution cannot see first-run variables |
| `authority.py` | Enumerates five capabilities, all `SEND`-only endpoints. Neither they nor guessed handles permit process creation, device listing/claiming, shutdown or control operations. Shell modules are not loaded, and file/network grants match policy |
| `failing.py`, `broken.txt`, `missing.py` | Exception, syntax error and absent file exit with status 1 and diagnostics |
| `spin.py` | Noncooperative loop: timed `wait` returns `TIMED_OUT`, `ps` reports running, `kill` terminates it |
| `hog.py` | Heap exhaustion ends the application with `MemoryError` |
| `idle.py`, five times | Fifth rejected with `LIMIT_EXCEEDED`; shutdown stops the other four |
