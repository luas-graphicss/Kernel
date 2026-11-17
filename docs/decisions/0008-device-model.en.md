# ADR 0008: Devices and mediated DMA

[Português](0008-device-model.md)

Status: accepted.

## Context

The reference profile has no IOMMU. Whoever writes a physical address into a device queue makes the device read or write that memory, whoever it belongs to. A driver in U-mode with the registers and the queue mapped would have, in practice, the privilege of the supervisor.

At the same time the project wants the drivers in Python, outside the TCB, with the behavior of the device where it can be read and tested.

## Decision

The transport is native and the driver is Python.

The supervisor discovers the devices in the DTB, maps the registers only for itself, negotiates with the device and owns the queue. The driver receives a capability of the device and asks for transfers naming buffers by handle, offset and length. The supervisor checks the capability of each buffer, pins the memory, writes the descriptors and notifies the device. The driver never gives or receives a physical address, and the queue is not mapped in any process.

On the way back, the supervisor checks what the device says: a completion needs to name a request in flight and cannot declare more bytes than the request allowed. The supervisor keeps the chain of each request in memory of its own and never rereads the descriptor table. A device that violates the protocol is stopped, with the memory still pinned.

What stays on each side:

| Native | Python, in U-mode |
| --- | --- |
| Discovery in the DTB and ownership by capability | Which devices the system uses and who receives each one |
| VirtIO negotiation, queue addresses, descriptors, barriers and notification | Features of the device itself, format of each request |
| Validation of the completion queue | Deadline of each request, reset after the deadline, classification of the error |
| Pinning of buffers, reset and quarantine | Protocol offered to the clients |
| Transmission and reception of UART bytes; emergency console | Line discipline and behavior of the console |
| Interrupt controller and handlers | Nothing: Python does not run in an interrupt |

Rules that follow:

- Only VirtIO-MMIO version 2 with `VIRTIO_F_VERSION_1`. A legacy device is not registered.
- The driver negotiates only the feature bits of the device type, from 0 to 23. The transport features are the choice of the supervisor, and today it only accepts `VIRTIO_F_VERSION_1`.
- One queue per device, with 16 descriptors, four requests in flight and four segments per request. The numbers are small on purpose: the whole state of the queue fits in fixed tables of the supervisor.
- A device has one owner at a time. `init` claims each one with the system capability and grants it to the service the manifest names.
- A reset the device does not confirm leads to quarantine: the pinned frames do not return to the allocator and the device is not reopened until the next boot.
- The process that loses the capability of the device, including by dying, causes the same reset. The memory of a dead driver is not used again while the device can reach it.
- External interrupts are served by native code, only when a process runs in U-mode or when the supervisor waits with no process ready.

The interface is in `specs/abi/devices.en.md`, the transport in `native/supervisor/devices/` and the drivers in `src/kernel_drivers/`.

## Consequences

Each transfer costs two syscalls and the copy of the metadata of the request. With four requests in flight per device, throughput is limited; no measurement has shown yet that this matters.

A defective driver spoils the data of its own device and denies service to its clients. It does not reach memory outside the buffers it has.

The protection holds for the devices of the profile: `virtio-blk`, `virtio-rng` and the UART of QEMU. A physical device that accesses memory on its own is outside the threat model.

## Assumptions to confirm

- One queue was enough until the network arrived. `virtio-net` uses two, and since ADR 0009 the supervisor programs up to two queues per device, with the limit of four requests applying to each one.
- The limit of reads waiting for the reset confirmation works outside QEMU. It is a count, not a time.
- Four requests in flight do not limit the file service, which today makes one request at a time.
