#ifndef KERNEL_IPC_CALL_H
#define KERNEL_IPC_CALL_H

#include <stdint.h>

#include "kernel/objects/object_table.h"
#include "kernel/processes/process.h"

uint64_t call_reply_create(const struct process *caller, uint32_t endpoint);
void call_reply_discard(uint64_t reply);
void call_reply_dispatched(uint64_t reply);
void call_reply_finished(uint64_t reply);
void call_reply_disposed(uint64_t reply, struct kernel_object object);
struct process *call_waiting_caller(uint64_t reply);
void call_abandon(struct process *caller);
void call_peer_closed(uint64_t reply);

#endif
