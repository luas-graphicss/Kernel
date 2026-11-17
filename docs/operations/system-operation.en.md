# Operating the system

[Português](system-operation.md)

How to start the system on QEMU, use the shell, run programs from the volume and power off. The console excerpts on this page are the output of the `system-journey` suite.

## Starting

```sh
uv run kernel-tool build
uv run kernel-tool run
```

`run` starts QEMU with the serial port connected to the terminal and passes `init=kernel_services.manager.main` to the kernel. It attaches:

- the boot image `build/qemu-riscv64/boot.img`, read-only;
- the data volume `build/qemu-riscv64/system/data.img`, of 1 MiB, created empty on the first run and kept on the following ones;
- the entropy source;
- the network interface, connected to an isolated test station on the host. Without permission to create the isolated network, `run` warns `booting without a network` and carries on without it. `--without-network` asks for that on purpose. The details are in `network-operation.en.md`.

The boot ends at the prompt:

```
system: manager=started runtime=micropython privilege=user
system: devices serial=1 entropy=1 network=1 block=2
system: configuration=accepted name=kernel services=5
system: service=console state=ready
system: service=entropy state=ready
network: interface=10.0.2.15/24 mtu=1500
system: service=network state=ready
system: service=shell state=ready
system: state=running
shell: ready
kernel>
```

`system: state=degraded` in place of `running` means some service did not start. The shell remains available when the console and the storage are ready; `services-and-configuration.en.md` explains what to do.

`run` ends when the system powers off, with status 0. `--deadline SECONDS` closes the session after that time, with status 1. Ctrl-C kills the emulator without an orderly shutdown: what did not go through `sync` may be lost.

When standard input is not a terminal, `run` holds what arrives on it and only relays it to the console after `shell: ready`. A command sent through a pipe or redirected from a file arrives whole:

```sh
printf 'ls boot\nshutdown\n' | uv run kernel-tool run --without-network
```

On a terminal the input goes straight to the emulator. Type after the prompt: a byte sent before the firmware sets up the serial port is lost.

## The shell

A line is a command and its arguments, separated by spaces. Double quotes join words into one argument. There are no pipes, redirection, variables, wildcards or history, and no command is a shortcut to a host program.

| Limit | Value |
| --- | --- |
| Line | 255 bytes |
| Words | 16 |
| Complete lines waiting for the shell | 4 |
| Received bytes waiting for the console | 256 |

What goes past 255 bytes does not enter the line and rings the bell. A line that overflowed is not run: on Enter the shell answers `shell: command=none status=failed error=MESSAGE_TOO_LARGE`. Ctrl-U erases the line and lets you start again.

The console keeps up to four complete lines while the shell runs a command. Each line beyond that is dropped, and the console warns with `console: dropped-lines=N`, where N is the total dropped since the console service started. A script should wait for the status line of a command before sending the next one. A burst with more than 256 bytes not yet read loses the excess before it reaches the console, without a warning.

TAB counts as a space. An escape sequence, such as those of the arrow and function keys, is discarded whole.

Every command ends with a status line, and that is what a script should check:

```
shell: command=mkdir status=ok
shell: command=cat status=failed error=NOT_FOUND
```

| Command | What it does | Output |
| --- | --- | --- |
| `help` | Lists the commands | One `help:` line per command |
| `run <path> [arguments]` | Starts the program from the volume as an application | `run: application=N program=<path>` |
| `ps` | Lists the state of the system, the services and the applications | `ps: system=`, `ps: service=`, `ps: application=` |
| `kill <application>` | Ends an application | `kill: application=N` |
| `wait <application> [seconds]` | Waits for the application to end. Without a time, waits without a limit | `wait: application=N reason=<reason> value=<value>` |
| `mem` | Shows memory frames and kernel objects | Two `mem:` lines |
| `ls [path]` | Lists a directory. Without a path, lists the mounts | `ls: name= kind= size=` per entry and `ls: entries=N` |
| `cat <path>` | Prints a file of up to 65,536 bytes | The content and `cat: bytes=N` |
| `mkdir <path>` | Creates a directory | Only the status |
| `write <path> <text>` | Replaces the file with one line holding the text | `write: bytes=N` |
| `rm <path>` | Removes a file or an empty directory | Only the status |
| `sync` | Makes the writable volumes durable | `sync: mount=<name> durable=1` per volume and `sync: volumes=N` |
| `net [counters\|neighbors]` | Shows the interface, the counters or the neighbors | `net:` lines |
| `ping <address> [count]` | Sends echo requests. The default is 3 and the maximum is 16 | `ping: from=`, and `ping: sent=N received=M` |
| `shutdown [restart]` | Stops the system in order and powers off, or restarts | `shutdown: action=` |

A name that is not in the table returns `status=failed error=UNSUPPORTED`.

## Files

Paths start with the name of a mount and have no leading slash.

| Mount | Content | Writable | Survives power off |
| --- | --- | --- | --- |
| `boot` | The boot image: `system/config`, `system/release`, `system/license` and the programs in `apps/` | No | Yes, it is the same image |
| `data` | The persistent volume | Yes | Yes, from `sync` on |
| `tmp` | Files in memory | Yes | No |

```
kernel> mkdir data/journey
shell: command=mkdir status=ok
kernel> write data/journey/note written before the restart
write: bytes=27
shell: command=write status=ok
kernel> cat data/journey/note
written before the restart
cat: bytes=27
shell: command=cat status=ok
kernel> sync
sync: mount=data durable=1
sync: mount=tmp durable=1
sync: volumes=2
shell: command=sync status=ok
```

A written file is only guaranteed to be on the disk after `sync` answers or after an orderly shutdown. `rm boot/system/release` returns `READ_ONLY`.

A refused `write`, for example with `NO_SPACE`, removes the file it had just created. A file that already existed stays listed, empty: the command empties it before writing.

## Programs

`run` starts a Python file from the volume in its own process and returns the prompt right away. The application receives a number, which the other commands use.

```
kernel> run boot/apps/wordcount.py data/journey/note
system: application=1 state=running program=boot/apps/wordcount.py
run: application=1 program=boot/apps/wordcount.py
shell: command=run status=ok
kernel> wait 1 10
wordcount: path=data/journey/note lines=1 words=4 bytes=27
system: application=1 state=exited reason=exit value=0
wait: application=1 reason=exit value=0
shell: command=wait status=ok
```

The output of an application goes straight to the diagnostic console, without passing through the shell. An application that writes while the shell is also writing may show up in the middle of one of its lines; `wait` avoids that, because the shell only writes again when the application ends.

The boot image carries three programs: `boot/apps/wordcount.py <path>`, `boot/apps/sysinfo.py` and `boot/apps/fetch.py <address> <port> <path>`, which writes to a file what a TCP connection delivers. To run a program of your own, put the file in the boot image, through `config/boot/manifest.toml`, and build the image again. The format of a program and what it may use are in `specs/system/applications.en.md`.

| Situation | What shows up |
| --- | --- |
| The application ended well | `reason=exit value=0` |
| The program raised an exception, has a syntax error or does not exist | The diagnostic and `reason=exit value=1` |
| `wait` with a time limit and the application still runs | `status=failed error=TIMED_OUT`. The application carries on |
| `kill` | `wait: application=N reason=killed value=0` |
| More applications running than the configuration limit, which is 4 | `run` returns `LIMIT_EXCEEDED` |
| Unknown number | `NOT_FOUND`. The system keeps the eight most recently ended applications |

`ps` shows the applications along with the services:

```
kernel> ps
ps: system=running
ps: service=console state=ready restarts=0/2 starts=1
ps: service=entropy state=ready restarts=0/2 starts=1
ps: service=storage state=ready restarts=0/2 starts=1
ps: service=network state=ready restarts=0/3 starts=1
ps: service=shell state=ready restarts=0/3 starts=1
ps: application=1 state=exited reason=exit value=0 command="boot/apps/wordcount.py data/journey/note"
shell: command=ps status=ok
```

## Powering off and restarting

```
kernel> shutdown restart
system: shutdown=started action=restart
system: application=5 state=exited reason=killed value=0
system: shutdown=applications stopped=1
system: service=shell state=stopped clean=1
system: service=network state=stopped clean=1
system: service=storage state=stopped clean=1
system: service=entropy state=stopped clean=1
system: service=console state=stopped clean=1
system: shutdown=complete clean=1
kernel: power=restart
kernel: status=ok
```

`shutdown` ends the applications, stops the services in the reverse order of their start and synchronizes the volumes before powering off. There is no need to run `sync` first. With `restart`, `kernel-tool run` starts the system again with the same data volume; without it, `run` ends.

The shell's own lines for this command, `shutdown: action=` and the status, do not always appear. The shell is the first service to stop, and the shutdown can reach it before it writes. The manager's `system: shutdown=` lines always appear.

`clean=0` on a service or on the last line means some service did not answer the stop within 20 seconds and was ended by force. Check the data after the next boot.

## Common errors

| Code | Likely cause | What to do |
| --- | --- | --- |
| `UNSUPPORTED` | A command that does not exist | `help` |
| `INVALID_ARGUMENT` | Missing argument, number out of range, unclosed quotes or more than 16 words | Check the syntax in the table |
| `MESSAGE_TOO_LARGE` | A line with more than 255 bytes | Shorten the line. Ctrl-U erases the one being edited |
| `NOT_FOUND` | A path or an application that does not exist | `ls`, `ps` |
| `READ_ONLY` | A write to `boot`, or to a volume mounted read-only | Use `data` or `tmp` |
| `NO_SPACE` | Data volume full | Remove files and run `sync` |
| `TIMED_OUT` | The wait ran out | Repeat, or `kill` |
| `LIMIT_EXCEEDED` | Application or socket limit reached | Wait for an application to end |
| `BAD_STATE` | The service that handles the command is not ready | `ps`, and then `services-and-configuration.en.md` |
| `ACCESS_DENIED` | The configuration does not grant the operation to the shell | Review `[access.shell]` |
