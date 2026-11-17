# Socket service

[Português](socket-service.md)

The network service provides sockets through IPC. A process may open one only with a granted access capability, carrying explicit rights. Names, environment variables and file paths confer no socket access. Messages follow `specs/abi/messages.en.md`; formats are in `kernel_protocol.services.network`, the client library is `kernel_client.sockets`, and underlying protocols are in `protocols.en.md`.

## Access and session

Clients need two `SEND` capabilities: the service endpoint and an access endpoint created by that service. Access endpoints prove possession; they do not accept ordinary requests.

To enter, send a one-way `ENTER` to the access endpoint, then call `ENTER` on the service endpoint. Supervisor-provided message identity must match both senders. The resulting 20-byte session response contains service instance in 8 bytes, session token in 8 and access rights in 4.

Calling `ENTER` without the access message, or sending it to an endpoint not created by the service, returns `ACCESS_DENIED`.

| Bit | Right | Permits |
| --- | --- | --- |
| `0x01` | `connect` | Opening stream sockets and connecting |
| `0x02` | `listen` | Opening stream sockets and listening |
| `0x04` | `datagram` | Opening datagram sockets |
| `0x08` | `echo` | Sending echo requests |
| `0x10` | `inspect` | Reading interface state, counters and neighbors |
| `0x20` | `delegate` | Creating restricted accesses |

`RESTRICT` creates access with a subset of session rights and returns a capability grantable to another process. Excess rights return `ACCESS_DENIED`; empty or unknown rights return `INVALID_ARGUMENT`. `REVOKE` destroys access created by the same session, its descendants and all dependent sessions; sockets close and waits end with `CANCELLED`. `LEAVE` terminates the caller's session the same way.

Only the supervising process may use `ROOT`, which returns full access, or `EVICT`, which ends a process's sessions on application exit. Other callers receive `ACCESS_DENIED`.

## Requests

Except `ENTER`, `ROOT` and `EVICT`, requests start with 16 bytes: service instance in 8 and subject in 8. The subject is a session token or socket handle. Integers are little-endian.

| Condition | Error |
| --- | --- |
| Pre-restart instance, unknown token/handle or another process's handle | `INVALID_HANDLE` |
| Body size differs from operation format | `INVALID_ARGUMENT` |
| Request carries a capability | `INVALID_ARGUMENT`, capability closed |
| Unknown operation | `UNSUPPORTED` |
| Missing operation right | `ACCESS_DENIED` |
| Stream operation on datagram socket, or reverse | `NOT_FOUND` |

| Number | Operation | Subject | Body | Response |
| --- | --- | --- | --- | --- |
| 16 | `ROOT` | None | Empty | Empty, full-access capability |
| 17 | `EVICT` | None | Process identity, 8 bytes | Empty |
| 18 | `ENTER` | None | Empty | 20-byte session |
| 19 | `LEAVE` | Session | Empty | Empty |
| 20 | `RESTRICT` | Session | Rights, 4 bytes | Access identity, 4 bytes, and capability |
| 21 | `STATUS` | Session | Empty | Interface |
| 22 | `NEIGHBORS` | Session | Empty | 10 bytes per neighbor: IPv4 and hardware address |
| 23 | `ECHO` | Session | Address in 4, wait in 8, data-byte count in 2 | Round-trip nanoseconds in 8 |
| 24 | `OPEN` | Session | Type in 4: 1 stream, 2 datagram | Socket handle in 8 |
| 25 | `BIND` | Socket | Port in 2; zero requests an ephemeral datagram port | Assigned port in 2 |
| 26 | `LISTEN` | Socket | Backlog in 2, 1–8 | Empty |
| 27 | `ACCEPT` | Socket | Wait in 8 | New handle in 8, address in 4, port in 2 |
| 28 | `CONNECT` | Socket | Address in 4, port in 2, wait in 8 | Empty |
| 29 | `SEND` | Socket | Wait in 8, then data | Accepted bytes in 4 |
| 30 | `RECEIVE` | Socket | Wait in 8, limit in 4 | Data; empty at stream EOF |
| 31 | `SEND_TO` | Socket | Address in 4, port in 2, then data | Sent bytes in 4 |
| 32 | `RECEIVE_FROM` | Socket | Wait in 8, limit in 4 | Address in 4, port in 2, datagram size in 4, then data |
| 33 | `FINISH` | Socket | Empty | Empty |
| 34 | `CLOSE` | Socket | Empty | Empty |
| 35 | `DESCRIBE` | Socket | Empty | 22-byte description |
| 36 | `REVOKE` | Session | Access identity in 4 | Empty |

Interface, 32 bytes plus 8 per counter:

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 6 | Hardware address |
| 6 | 4 | IPv4 address |
| 10 | 4 | Gateway or zero |
| 14 | 2 | MTU |
| 16 | 1 | Prefix |
| 17 | 1 | Link: 1 means up |
| 18 | 2 | Open sockets |
| 20 | 2 | TCP connections |
| 22 | 4 | Buffered bytes |
| 26 | 4 | Device resets |
| 30 | 2 | Counter count, in `protocols.en.md` order |

Socket description: type in 1 byte, state in 1, local port in 2, remote address in 4, remote port in 2, readable bytes in 4, writable capacity in 4 and last error in 4.

| Value | State |
| --- | --- |
| 0 | `new` |
| 1 | `bound` |
| 2 | `listening` |
| 3 | `connecting` |
| 4 | `connected` |
| 5 | `peer-finished`: peer ended sending |
| 6 | `finished`: this side ended sending |
| 7 | `closed` |

## Operation rules

| Operation | Condition | Error |
| --- | --- | --- |
| `OPEN` | 16 process sockets or 64 service sockets | `LIMIT_EXCEEDED` |
| `BIND` | Stream socket with zero port, or already bound/listening/connected | `INVALID_ARGUMENT` |
| `BIND` | Datagram socket already bound | `BAD_STATE` |
| Datagram `BIND`, `LISTEN` | Port already used | `ALREADY_EXISTS` |
| `LISTEN` | Unbound, already listening or connected socket | `BAD_STATE` |
| `LISTEN` | Backlog outside 1–8 | `INVALID_ARGUMENT` |
| `ACCEPT` | Socket not listening | `BAD_STATE` |
| `CONNECT` | Socket already listening or connected | `BAD_STATE` |
| `CONNECT`, `SEND_TO`, `ECHO` | Non-host address or zero port | `INVALID_ARGUMENT` |
| `CONNECT` | Peer reset | `CONNECTION_REFUSED` |
| `CONNECT`, `SEND_TO`, `ECHO` | No route, down link, unanswered neighbor resolution or path error | `UNREACHABLE` |
| `SEND` | Empty request or more than 4032 bytes | `INVALID_ARGUMENT` |
| `SEND` | After `FINISH` or without established connection | `BAD_STATE` |
| `SEND`, `RECEIVE` | Connection reset | `CONNECTION_RESET` |
| `SEND`, `RECEIVE` | Retransmissions exhausted without acknowledgment | `TIMED_OUT` |
| `SEND_TO` | More than 4026 bytes | `MESSAGE_TOO_LARGE` |
| `RECEIVE_FROM` | Earlier datagram received port-unreachable | `CONNECTION_REFUSED`, once |
| `ECHO` | More than 1024 data bytes | `INVALID_ARGUMENT` |

Unbound datagram sockets receive an ephemeral port on first `SEND_TO` or `RECEIVE_FROM`. Each receive consumes one datagram. If it exceeds the requested limit, data is truncated, the size field reports its original length and the remainder is discarded.

`FINISH` ends sending only. Receiving continues until the peer finishes. `CLOSE` releases the socket immediately; accepted but unacknowledged bytes continue delivery in the background.

## Waiting, deadlines, cancellation and backpressure

Waits are relative nanosecond durations. Zero does not wait: without a ready result it returns `TIMED_OUT`. `0xFFFFFFFFFFFFFFFF` waits indefinitely.

`ACCEPT`, `CONNECT`, `SEND`, `RECEIVE`, `RECEIVE_FROM` and `ECHO` may wait. The service retains requests until a result, timeout or cancellation while serving other clients.

| Situation | Waiting caller result |
| --- | --- |
| Wait expires | `TIMED_OUT`; connecting flow abandoned |
| Same process repeats the operation on the same socket | Earlier request gets `CANCELLED` |
| Socket closed, session ended or access revoked | `CANCELLED` |
| Service receives `STOP` | `CANCELLED` |
| 64 service requests already pending | `LIMIT_EXCEEDED` |
| Client died before delivery | Effect undone: accepted connection closed; received bytes remain buffered |

`SEND` returns bytes admitted to the connection's send buffer, possibly fewer than requested. It waits only when none fit. Each connection has 16 KiB within the service's 1 MiB budget: a nonreading peer backpressures its sender without consuming other sockets' memory. `RECEIVE` removes bytes only after successful reply delivery.

## Service restart

Each instance has its own identity. Old tokens and handles return `INVALID_HANDLE` after restart, and old access disappears; the library reports `ACCESS_DENIED` when entering through it. No connection survives and no operation is automatically repeated. Pending callers receive `PEER_CLOSED`.

## Client library

`kernel_client.sockets.Network(service, access)` enters the service and exposes `status`, `neighbors`, `echo`, `restrict`, `revoke`, `stream`, `datagram` and `leave`. `StreamSocket` provides `bind`, `listen`, `accept`, `connect`, `send`, `send_all`, `receive`, `finish`, `describe` and `close`. `DatagramSocket` provides `bind`, `send_to`, `receive_from`, `describe` and `close`. Failures raise `KernelError`.

```python
from kernel_apps import runtime
from kernel_services.network.ipv4.address import parse_address

network = runtime.current().network
stream = network.stream()
stream.connect(parse_address("10.0.2.2"), 17, 10_000_000_000)
data = stream.receive(2048, 10_000_000_000)
stream.close()
```

## Evidence

The QEMU `network` suite exercises this contract against a real peer: `interface-and-echo`, `datagrams`, `streams`, `listening`, `deadlines-cancellation-and-backpressure`, `socket-quota` and `access-rights`. The last verifies restriction, revocation, forged and old-instance handles, and a process holding the service endpoint without access: it can neither open a socket nor reach the device. `service-restart-with-a-waiting-client` in `network-faults` covers restart.
