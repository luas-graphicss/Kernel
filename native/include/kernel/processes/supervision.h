#ifndef KERNEL_PROCESSES_SUPERVISION_H
#define KERNEL_PROCESSES_SUPERVISION_H

#include <stdint.h>

int64_t supervision_kill(uint64_t handle);
int64_t supervision_release(uint64_t handle);
uint32_t supervision_state(uint64_t handle);

#endif
