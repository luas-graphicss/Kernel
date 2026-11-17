# Network protocols

[Português](protocols.md)

`kernel_services.network.main` is a U-mode process containing the `virtio-net` driver, IPv4 stack and sockets. It speaks Ethernet, ARP, IPv4, ICMP, UDP and TCP through one statically addressed interface. This page defines accepted and rejected inputs and limits. The process-facing API is in `socket-service.en.md`.

The profile is a local-network station: no IPv6, DHCP, DNS or forwarding. Anything not explicitly supported here is unsupported.

## Matrix

| Layer | Supported | Rejected or absent |
| --- | --- | --- |
| Device | Modern `virtio-net` over VirtIO-MMIO, `MAC` and optional `STATUS`. Queue 0 receives, queue 1 transmits. Frames up to 1514 bytes | Checksum/segmentation offload, mergeable buffers, control queue, multiple queue pairs |
| Ethernet | Ethernet II addressed to the interface or broadcast. Short outgoing payloads padded to 46 bytes | VLAN, foreign destination, multicast or zero source, types other than ARP and IPv4 |
| ARP | Ethernet/IPv4 requests and replies. Replies for own address. Learns senders when addressed to the interface or when already known | Other hardware/protocol types, unknown operation, frame/source mismatch, off-subnet source, claims of the interface's own address |
| IPv4 | Checksum-validated 20-byte header. Interface and subnet-broadcast delivery. TTL 64, direct subnet route and optional gateway. Outgoing fragmentation and incoming reassembly. Local delivery to own address and `127.0.0.0/8` | Options, forwarding, multicast, non-host or own-interface source |
| ICMP | Echo both ways. Received destination-unreachable: host, protocol, port and fragmentation-needed codes. Outgoing port/protocol unreachable | Redirect, time exceeded, timestamp and other types are counted and dropped |
| UDP | Checksum validation when supplied. Ports 1–65535 | Destination port zero, inconsistent packet length |
| TCP | Active/passive open, bidirectional data, windows, timeout/three-duplicate-ACK retransmission, congestion control, half-close, reset and `TIME_WAIT`. Maximum-segment-size option | Window scaling, SACK, timestamps, urgent data, keepalive |

## Device and link

`kernel_drivers.virtio_network.driver` runs inside the service. It requests `VIRTIO_NET_F_MAC` and `VIRTIO_NET_F_STATUS`, rejecting devices without an address or second queue with `UNSUPPORTED`. No offload is negotiated: each frame's 12-byte header is zero, and the stack calculates and validates every checksum.

One service-owned 16 KiB buffer holds four receive and four transmit slots, 2048 bytes each. Slots are named by handle and offset as in `specs/abi/devices.en.md`; the driver never sees a physical address. No other process receives the device capability.

| Situation | Behavior |
| --- | --- |
| No transmit slot | Frame waits in a 64-frame queue; overflow is dropped and counted |
| Device reports link down | `network: link=down`; sends return `UNREACHABLE` until `network: link=up` |
| Failed device | Up to three reset/session-reopen attempts, one per second; `network: device=recovered resets=N`. Queued frames are dropped; connectivity returns after reset |

## ARP

| Limit | Value |
| --- | --- |
| Known neighbors | 32, each for 60 s; evict the nearest expiry when full |
| Pending resolutions | 8 destinations, up to 4 queued datagrams per destination |
| Attempts | 3 requests, one per second; then `UNREACHABLE` |

ARP learns a neighbor only if its declared hardware address matches the enclosing frame and its IPv4 address names a subnet host other than the interface.

## IPv4

| Rule | Violation |
| --- | --- |
| Version 4; header and total length within frame | Drop, `ipv4-malformed` |
| Exactly 20-byte header | Drop, `ipv4-options-refused` |
| Valid header checksum | Drop, `ipv4-bad-checksum` |
| Source names a host other than the interface | Drop, `ipv4-bad-source` |
| Destination is interface or broadcast | Drop, `ipv4-foreign` |
| Protocol 1, 6 or 17 | Send protocol-unreachable, `ipv4-protocol-unsupported` |

Configured MTU is 576–1500 bytes. Off-subnet destinations use the gateway; without one, they immediately return `UNREACHABLE`, without ARP.

Datagrams exceeding MTU are fragmented into 8-byte-multiple pieces. The stack does not set `DF`. Receive reassembly limits:

| Limit | Value |
| --- | --- |
| Incomplete datagrams | 16 |
| Reassembly bytes | 1 MiB, separate from socket budget |
| Assembly lifetime | 30 s |

Duplicate fragments with identical bytes are tolerated. Conflicting overlap, inconsistent endings, invalid 8-byte boundaries, empty fragments or data beyond 65,535 bytes invalidate the whole assembly with `fragments-invalid`. Memory pressure evicts the oldest assembly with `fragments-evicted`; expiry increments `fragments-expired`. One assembly cannot consume the entire budget.

## ICMP

| Message | Handling |
| --- | --- |
| Incoming echo request | Reply only for interface address and at most 1472 bytes. Burst of 8, replenished every 100 ms; excess increments `icmp-rate-limited` |
| Incoming echo reply | Deliver to the waiting request identified by session and sequence |
| Incoming destination-unreachable | Accept only if it quotes a datagram sent by this station; otherwise `icmp-malformed`. Port/protocol unreachable terminates a connecting TCP flow and marks the originating UDP socket. Fragmentation-needed reduces the cited connection's segment size to no less than 64 bytes |
| Outgoing destination-unreachable | Port-unreachable for UDP without a socket; protocol-unreachable for unknown protocol. Same burst limit as echo |

## UDP

Each datagram socket stores at most 16 datagrams and 64 KiB. Queue overflow drops and counts `udp-queue-full`. An unbound destination counts `udp-no-listener` and generates port-unreachable. Ephemeral ports span 49152–65535, starting at a random candidate.

Through the socket service, outgoing datagrams carry up to 4026 bytes and incoming delivery up to 4022. Datagrams above MTU are fragmented.

## TCP

The explicit state machine has `closed`, `syn-sent`, `syn-received`, `established`, `fin-wait-1`, `fin-wait-2`, `close-wait`, `closing`, `last-ack` and `time-wait`. Sequence arithmetic is modulo 32 bits.

| Mechanism | Behavior |
| --- | --- |
| Initial sequence and ephemeral port | Randomized from entropy-service bytes. Network startup requires entropy |
| Segment size | MTU minus 40, advertised in `SYN`. Respects peer MSS; defaults to 536 when absent |
| Window | 16 KiB send and receive buffers per connection. Timer probes zero windows; reads reopen the window with an ACK |
| Out of order | Up to 16 queued segments per connection; excess counts `tcp-out-of-order-refused` |
| Retransmission timeout | RTT estimate bounded to 200 ms–60 s, initially 1 s, doubled on expiry |
| Giving up | 8 data retransmissions or 4 opening retransmissions. Ends with `TIMED_OUT`, or `UNREACHABLE` after a path error |
| Congestion | Slow start, congestion avoidance, fast retransmit on the third duplicate ACK and fast recovery with partial ACKs. Initial window 2–4 segments |
| Reset | Unbound destination receives `RST`, burst-limited to 16 and replenished every 50 ms. Acceptable `RST` ends established flows with `CONNECTION_RESET`, opening flows with `CONNECTION_REFUSED` |
| Invalid ACK | Acknowledging unsent bytes changes no state and counts `tcp-unacceptable` |
| Closing | Independent `FIN` in each direction, supporting half-close. Active closer remains in `time-wait` for 60 s |
| Accept backlog | Up to 8 connections per listener; excess requests dropped with `tcp-backlog-full`, leaving peer to retransmit |

Closing a socket with unacknowledged data continues delivery in the background. If the peer acknowledges nothing for 3 s, the connection is aborted with `RST`.

## Service limits

| Limit | Value |
| --- | --- |
| Sockets | 64 total, 16 per process |
| TCP connections | 96, including opening, closing and `time-wait` |
| Socket-buffer bytes | 1 MiB across all sockets |
| Outgoing frame queue | 64 |
| Local-delivery datagrams | 32 |

When the byte budget is exhausted, TCP writes accept fewer bytes or none, and new datagrams are dropped. Opening more sockets does not bypass the shared budget.

## Counters

`net counters` and `STATUS` expose service counters. Rejected packets increment their rejecting rule's counter:

`frames-received`, `frames-sent`, `frames-malformed`, `frames-foreign`, `frames-unsupported`, `frames-unsent`, `arp-malformed`, `arp-requests-answered`, `arp-unresolved`, `arp-queue-refused`, `ipv4-malformed`, `ipv4-bad-checksum`, `ipv4-options-refused`, `ipv4-foreign`, `ipv4-bad-source`, `ipv4-protocol-unsupported`, `ipv4-unroutable`, `ipv4-too-large`, `fragments-received`, `fragments-invalid`, `fragments-expired`, `fragments-evicted`, `datagrams-reassembled`, `icmp-malformed`, `icmp-echo-answered`, `icmp-rate-limited`, `icmp-unsupported`, `udp-malformed`, `udp-bad-checksum`, `udp-no-listener`, `udp-queue-full`, `udp-delivered`, `tcp-malformed`, `tcp-bad-checksum`, `tcp-no-socket`, `tcp-backlog-full`, `tcp-resets-sent`, `tcp-resets-received`, `tcp-segments-retransmitted`, `tcp-out-of-order`, `tcp-out-of-order-refused`, `tcp-unacceptable`, `tcp-connections-opened` and `tcp-connections-failed`.

## Evidence

Limits are in `kernel_services.network.limits`. The pure-Python stack runs unchanged on CPython. `tests/conformance/test_network_link.py`, `test_network_reassembly.py`, `test_network_tcp.py` and `test_network_malformed.py` exercise two peers over a simulated wire with controlled time, loss, duplication and reordering.

In QEMU, `network` covers interface, echo, datagrams, connections, listening, quotas and rights. `network-interop` exchanges hash-verified data with Linux TCP/IP over clean links and links with 3% loss, 2% duplication and 10% reordering. `kernel-tool fault-test --suite network-faults` injects 31 malformed Ethernet-through-TCP specimens, 32 forged connection requests, 1.5 s of link outage and device reset. Recorded results are in `docs/acceptance/network-and-operational-environment.en.md`.
