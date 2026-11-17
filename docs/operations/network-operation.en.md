# Operating the network

[Português](network-operation.md)

How the network interface is configured, what sits at the other end of the cable on QEMU, how to check connectivity from the shell and how to read failures. What the stack supports is in `specs/network/protocols.en.md`.

## The interface

The system has one interface, with a static address read from `[interface]` in the configuration. The image in the repository uses:

| Field | Value |
| --- | --- |
| Address | `10.0.2.15/24` |
| Gateway | `10.0.2.2` |
| MTU | 1500 |
| Hardware address | `52:54:00:12:34:56`, set by `kernel-tool` on QEMU |

There is no DHCP or DNS. Every destination is an IPv4 address written in decimal, such as `10.0.2.2`. To change the address, edit `config/system/system.conf`, build the image again and restart; `services-and-configuration.en.md` shows the path.

## The other side

`kernel-tool run` and the suites connect the interface to a test station that runs on the host. The station creates a network namespace of its own, with a TAP interface at the address `10.0.2.2`, and answers with the Linux TCP/IP stack. The namespace has no route to the host or to the internet: the guest reaches `10.0.2.2` and nothing else.

The station turns IPv4 forwarding off inside the namespace, which would otherwise inherit the value of the host. The peer is a station and not a router: a packet to an address outside the network vanishes without a reply, on any machine.

| Port on `10.0.2.2` | Service |
| --- | --- |
| 7, TCP and UDP | Returns what it receives |
| 9, TCP | Reads everything and reports the hash to `kernel-tool` |
| 13, TCP | Accepts the connection and sends nothing |
| 14, TCP | Reads slowly, 1 KiB every 20 ms |
| 17, TCP | Sends a text of 240 lines and closes |
| 19, TCP | Sends the test stream requested in the first 8 bytes: seed and size |
| 81, TCP | Closed: refuses the connection |

The station needs to create the namespace. It manages to when `kernel-tool` runs as root, when the host allows unprivileged user namespaces with access to `/dev/net/tun`, or when `sudo -n` works without a password. Without any of the three, `run` carries on without a network and the network suites end with status 3.

## Checking from the shell

```
kernel> net
net: address=10.0.2.15/24 gateway=10.0.2.2 mtu=1500 link=up hardware=52:54:00:12:34:56
net: sockets=0 connections=0 buffered-bytes=0 device-resets=0
shell: command=net status=ok
kernel> ping 10.0.2.2 2
ping: from=10.0.2.2 bytes=32 time-us=4540
ping: from=10.0.2.2 bytes=32 time-us=2022
ping: sent=2 received=2
shell: command=ping status=ok
kernel> net neighbors
net: neighbor=10.0.2.2 hardware=ba:91:17:70:ac:7b
net: neighbors=1
shell: command=net status=ok
```

`ping` waits 2 seconds for each reply and fails only when none arrives. `net counters` lists the counters that are not zero; the names are in `specs/network/protocols.en.md`.

A `ping` reply proves little: it shows that ARP, IPv4 and ICMP work. To check TCP, bring data over a connection:

```
kernel> run boot/apps/fetch.py 10.0.2.2 17 data/journey/greeting
system: application=2 state=running program=boot/apps/fetch.py
run: application=2 program=boot/apps/fetch.py
shell: command=run status=ok
kernel> wait 2 20
fetch: path=data/journey/greeting bytes=6240
system: application=2 state=exited reason=exit value=0
wait: application=2 reason=exit value=0
shell: command=wait status=ok
```

## Reading a failure

| What shows up | Cause | What to do |
| --- | --- | --- |
| `net` returns `BAD_STATE` | The network service is not ready | `ps`. If the service is `degraded`, the device is missing or it failed more times than the window allows |
| `link=down` in `net`, `network: link=down` on the console | The device reported the link down | Wait for `network: link=up`. Sends return `UNREACHABLE` meanwhile, and the open connections retransmit when the link comes back |
| `ping` with `error=UNREACHABLE` | A destination outside the subnet without a gateway, or a neighbor that did not answer three ARP requests | `net neighbors`; check address, prefix and gateway |
| `ping` with `error=TIMED_OUT` | The neighbor exists and did not answer the echo | Check the other side. `net counters` shows `icmp-rate-limited` if the local limit was reached |
| An application with `CONNECTION_REFUSED` | Nobody listens on the destination port | Check the port |
| An application with `CONNECTION_RESET` | The peer aborted the connection | Check the peer |
| An application with `TIMED_OUT` on an open connection | The peer stopped acknowledging for eight retransmissions | `net counters`: `tcp-segments-retransmitted` grows when there is loss |
| `network: device=recovered resets=N` | The device failed and the driver reset it | Nothing. `device-resets` in `net` shows how many times it happened |
| `system: service=network state=restarting` | The service process died and was restarted | Applications receive `INVALID_HANDLE` on the old sockets and need to enter the service again. No connection survives the restart |
| `*-malformed` or `*-bad-checksum` counters growing | Invalid traffic arriving | Capture the traffic, as below. Invalid packets are discarded and take no memory |

A network problem does not bring the rest down: with the `network` service degraded, the shell, the files and the applications without a network carry on.

## Captures

The station records everything that goes through the cable, in both directions, in pcap format.

| Origin | File |
| --- | --- |
| `kernel-tool run` | `build/qemu-riscv64/system/network/traffic.pcap` |
| Suites | `build/qemu-riscv64/reports/captures/<scenario>.pcap`, with the hash and the number of frames in the suite report |

Each frame is cut at 96 bytes, which keeps the headers and discards almost all of the payload. The captures hold only the test addresses on this page and data generated by the tests; no host traffic goes through the station.

```sh
tcpdump -n -r build/qemu-riscv64/reports/captures/interop-impaired-link.pcap | head
```

## Limits the operator feels

| Limit | Value | Effect when reached |
| --- | --- | --- |
| Sockets per process | 16 | Opening another returns `LIMIT_EXCEEDED` |
| Sockets in the service | 64 | The same, for any process |
| Buffer memory | 1 MiB | Writes accept fewer bytes and wait; new datagrams are discarded |
| Connections waiting on a listening socket | 8 | New requests are discarded and the peer tries again |

The others are in `specs/network/protocols.en.md`.
