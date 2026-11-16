#ifndef KERNEL_OBJECTS_KERNEL_OBJECTS_H
#define KERNEL_OBJECTS_KERNEL_OBJECTS_H

#include <stdint.h>

#include "kernel/capabilities/capability_space.h"
#include "kernel/objects/object_table.h"

void kernel_objects_init(void);
struct object_table *kernel_object_table(void);
struct capability_registry *kernel_capabilities(void);
uint64_t kernel_system_object(void);
int64_t capability_require(uint32_t space, uint64_t handle, uint32_t kind, uint32_t rights,
                           struct capability *capability, struct kernel_object **object);
int64_t capability_transferable_rights(uint32_t space, uint64_t handle, uint32_t *rights);
int64_t capability_delegate(uint32_t space, uint64_t handle, uint32_t rights,
                            uint32_t destination);

#endif
