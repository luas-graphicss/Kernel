# ADR 0009: Network and operational environment in user space

[Português](0009-network-and-operational-environment.md)

Status: accepted.

## Context

The system lacked the network and what an operator uses: a shell, programs loaded from disk, a configuration and someone to keep the services up. All of that deals with untrusted input: packets from any peer, typed text, program files, a configuration file.

ADR 0002 already says that protocols, drivers and applications stay in Python. What needed a decision was where each piece runs, who has authority over what and what changes in native code.

## Decision

The network stack is a single user process. `kernel_services.network.main` contains the `virtio-net` driver, Ethernet, ARP, IPv4, ICMP, UDP, TCP and the sockets. The driver is not a separate process: each frame would cost one more message exchange, and the driver alone serves no one besides the stack. The capability of the device stays in that process and is handed to no one else.

A socket is reached by capability. The service issues accesses, which are endpoints of its own with a set of rights, and only creates a session for whoever proves to hold one. Accesses are restricted and revoked by the service itself, because the network rights, such as connect, listen and inspect, do not fit in the generic rights of an endpoint capability.

All network memory is counted. Each connection has fixed buffers, the service has a single byte budget, and queues, tables and reassemblies have a maximum size. A packet that does not fit is dropped and counted; it never raises a limit.

The supervisor now programs up to two queues per VirtIO device, and the `device_submit` request names the queue. It is the only change in the transport: `virtio-net` receives through one queue and transmits through another.

The system is kept by a manager in U-mode, `kernel_services.manager.main`, which replaces the verification `init` when the boot asks for it. It is the only process with the system capability. It reads the configuration, starts the services in dependency order, restarts whoever dies within a budget per window and conducts the shutdown.

The configuration is a data document, with sections, keys, numbers, strings and lists. It is not Python. An executable configuration file would run with the authority of the manager, and validating a whole document before applying any part of it requires it to be data only.

System control authorizes by the identity of the caller, which the supervisor records in each message, and not by possession of the endpoint. The manager knows which processes it admitted and with what rights. An application that obtained the control endpoint would still not be served.

An application is a Python source file, read from the volume and executed in a new process. For that the `user` profile of the runtime gains the MicroPython compiler, which changes ADR 0003 on that point. The `supervisor` profile stays without a compiler. Imports stay restricted to the frozen modules: a program is a single file.

Powering off and restarting go through a new syscall, `system_power`, which requires `ADMIN` on the system capability and only records the action. The supervisor executes it when the last process ends, after checking the resources, as in any ending.

The interfaces are in `specs/network/`, `specs/system/` and `specs/abi/`.

## Consequences

A defect in the network stack brings down one process, and the manager restarts it. The open connections are lost and the clients need to enter again; nothing is repeated on their behalf. Storage and the shell do not depend on the network and stay in use.

The stack runs the same on CPython, because it has no dependency on the kernel besides the driver. The conformance tests exercise the state machines with two sides and a simulated wire, with a controlled clock, and that is where loss, reordering, zero window and sequence wraparound are covered with precision. QEMU covers the integration with a real peer.

The compiler enters every user process, including the services, which do not use it. This enlarges the user image and the surface of each process, but not the TCB: the compiler runs in U-mode, on code the process itself chose to load.

The manager concentrates authority. It is small, does not interpret network input or programs, and handles the configuration only after it is validated.

Network throughput is limited by four requests per queue and by one copy of each frame between the driver buffer and the stack. No measurement has shown yet that this matters for the profile.

## Assumptions to confirm

- Buffers of 16 KiB per connection and 1 MiB in the service are enough for the loads of the profile. The transfers measured go up to 128 KiB per connection.
- Congestion control behaves well with loss above 3% and with long delays. Only moderate loss, duplication and reordering were exercised against a real peer.
- One interface and one default route are enough. There is no forwarding and no more than one interface.
- The cost of compiling a program on load fits interactive use. The programs measured have up to 44 lines.
