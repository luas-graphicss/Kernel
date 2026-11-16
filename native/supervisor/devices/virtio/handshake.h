#ifndef KERNEL_SUPERVISOR_VIRTIO_HANDSHAKE_H
#define KERNEL_SUPERVISOR_VIRTIO_HANDSHAKE_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/devices/virtio_queue.h"

bool virtio_handshake_reset(uintptr_t device);
int64_t virtio_handshake_negotiate(uintptr_t device, uint64_t wanted, uint64_t *accepted);
int64_t virtio_handshake_attach_queue(uintptr_t device, const struct virtio_queue *queue);
void virtio_handshake_start(uintptr_t device);

#endif
