#ifndef KERNEL_CAPABILITIES_CAPABILITY_SPACE_H
#define KERNEL_CAPABILITIES_CAPABILITY_SPACE_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/objects/slot_table.h"

#define CAPABILITY_NO_SPACE UINT16_MAX

struct capability_link {
    uint16_t space;
    uint16_t slot;
    uint32_t generation;
};

struct capability {
    uint64_t object;
    uint32_t rights;
    uint16_t children;
    uint8_t depth;
    bool marked;
    struct capability_link parent;
};

struct capability_space {
    struct slot_table slots;
    struct capability *entries;
    uint32_t limit;
    bool active;
};

typedef void (*capability_retain)(void *context, uint64_t object);
typedef void (*capability_release)(void *context, uint64_t object, uint32_t rights);

struct capability_registry {
    struct capability_space *spaces;
    uint32_t space_count;
    capability_retain retain;
    capability_release release;
    void *context;
    uint64_t live;
};

void capability_registry_init(struct capability_registry *registry, struct capability_space *spaces,
                              uint32_t space_count, capability_retain retain,
                              capability_release release, void *context);
void capability_space_attach(struct capability_registry *registry, uint32_t space,
                             struct slot_record *records, struct capability *entries,
                             uint32_t capacity);
bool capability_space_open(struct capability_registry *registry, uint32_t space, uint32_t limit);
void capability_space_close(struct capability_registry *registry, uint32_t space);
uint32_t capability_space_live(const struct capability_registry *registry, uint32_t space);
int64_t capability_install(struct capability_registry *registry, uint32_t space, uint64_t object,
                           uint32_t rights);
int64_t capability_derive(struct capability_registry *registry, uint32_t space, uint64_t handle,
                          uint32_t rights, uint32_t destination);
bool capability_find(const struct capability_registry *registry, uint32_t space, uint64_t handle,
                     struct capability *found);
int64_t capability_close(struct capability_registry *registry, uint32_t space, uint64_t handle);
int64_t capability_revoke(struct capability_registry *registry, uint32_t space, uint64_t handle);

#endif
