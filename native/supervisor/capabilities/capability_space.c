#include "kernel/capabilities/capability_space.h"

#include <stddef.h>

#include "kernel/abi/errors.h"
#include "kernel/abi/rights.h"

static const struct capability_link no_link = {.space = CAPABILITY_NO_SPACE};

static bool link_is_set(struct capability_link link)
{
    return link.space != CAPABILITY_NO_SPACE;
}

static bool links_match(struct capability_link first, struct capability_link second)
{
    return first.space == second.space && first.slot == second.slot &&
           first.generation == second.generation;
}

static struct capability_space *active_space(const struct capability_registry *registry,
                                             uint32_t space)
{
    if (space >= registry->space_count || !registry->spaces[space].active) {
        return NULL;
    }
    return &registry->spaces[space];
}

static struct capability *resolve_link(const struct capability_registry *registry,
                                       struct capability_link link)
{
    const struct capability_space *space;

    if (!link_is_set(link)) {
        return NULL;
    }
    space = active_space(registry, link.space);
    if (space == NULL || link.slot >= space->slots.capacity ||
        !space->slots.records[link.slot].occupied ||
        space->slots.records[link.slot].generation != link.generation) {
        return NULL;
    }
    return &space->entries[link.slot];
}

static struct capability_link link_to(const struct capability_space *space, uint32_t space_index,
                                      uint32_t slot)
{
    return (struct capability_link){
        .space = (uint16_t)space_index,
        .slot = (uint16_t)slot,
        .generation = space->slots.records[slot].generation,
    };
}

static bool slot_of(const struct capability_registry *registry, uint32_t space_index,
                    uint64_t handle, uint32_t *slot)
{
    const struct capability_space *space = active_space(registry, space_index);

    return space != NULL && slot_table_resolve(&space->slots, handle, slot);
}

static bool rights_are_valid(uint32_t rights)
{
    return rights != 0 && (rights & ~RIGHTS_ALL) == 0;
}

static int64_t place(struct capability_registry *registry, uint32_t space_index, uint64_t object,
                     uint32_t rights, struct capability_link parent, uint8_t depth)
{
    struct capability_space *space = active_space(registry, space_index);
    uint64_t handle;

    if (space == NULL) {
        return -KERNEL_ERROR_BAD_STATE;
    }
    if (space->slots.live >= space->limit) {
        return -KERNEL_ERROR_LIMIT_EXCEEDED;
    }
    handle = slot_table_allocate(&space->slots);
    if (handle == SLOT_INVALID_HANDLE) {
        return -KERNEL_ERROR_LIMIT_EXCEEDED;
    }
    space->entries[handle & SLOT_INDEX_MASK] = (struct capability){
        .object = object,
        .rights = rights,
        .depth = depth,
        .parent = parent,
    };
    registry->live++;
    return (int64_t)handle;
}

static void adopt_children(struct capability_registry *registry, struct capability_link removed,
                           struct capability_link heir)
{
    struct capability *parent = resolve_link(registry, heir);

    for (uint32_t index = 0; index < registry->space_count; index++) {
        struct capability_space *space = active_space(registry, index);

        if (space == NULL) {
            continue;
        }
        for (uint32_t slot = 0; slot < space->slots.capacity; slot++) {
            struct capability *entry = &space->entries[slot];

            if (!space->slots.records[slot].occupied || !links_match(entry->parent, removed)) {
                continue;
            }
            entry->parent = parent != NULL ? heir : no_link;
            if (parent != NULL) {
                parent->children++;
            }
        }
    }
}

static void remove_entry(struct capability_registry *registry, uint32_t space_index, uint32_t slot,
                         bool keep_children)
{
    struct capability_space *space = &registry->spaces[space_index];
    struct capability entry = space->entries[slot];
    struct capability_link self = link_to(space, space_index, slot);
    struct capability *parent = resolve_link(registry, entry.parent);

    if (parent != NULL) {
        parent->children--;
    }
    if (keep_children && entry.children > 0) {
        adopt_children(registry, self, entry.parent);
    }
    slot_table_release(&space->slots, slot_table_handle_at(&space->slots, slot));
    registry->live--;
    registry->release(registry->context, entry.object, entry.rights);
}

static bool descends_from(const struct capability_registry *registry,
                          const struct capability *entry, struct capability_link ancestor)
{
    struct capability_link link = entry->parent;

    for (uint32_t steps = 0; steps <= CAPABILITY_MAX_DEPTH && link_is_set(link); steps++) {
        const struct capability *parent;

        if (links_match(link, ancestor)) {
            return true;
        }
        parent = resolve_link(registry, link);
        if (parent == NULL) {
            return false;
        }
        link = parent->parent;
    }
    return false;
}

static void mark_descendants(struct capability_registry *registry, struct capability_link ancestor)
{
    for (uint32_t index = 0; index < registry->space_count; index++) {
        struct capability_space *space = active_space(registry, index);

        if (space == NULL) {
            continue;
        }
        for (uint32_t slot = 0; slot < space->slots.capacity; slot++) {
            struct capability *entry = &space->entries[slot];

            entry->marked = space->slots.records[slot].occupied &&
                            descends_from(registry, entry, ancestor);
        }
    }
}

static int64_t sweep_marked(struct capability_registry *registry)
{
    int64_t removed = 0;

    for (uint32_t index = 0; index < registry->space_count; index++) {
        struct capability_space *space = active_space(registry, index);

        if (space == NULL) {
            continue;
        }
        for (uint32_t slot = 0; slot < space->slots.capacity; slot++) {
            if (space->slots.records[slot].occupied && space->entries[slot].marked) {
                space->entries[slot].marked = false;
                remove_entry(registry, index, slot, false);
                removed++;
            }
        }
    }
    return removed;
}

void capability_registry_init(struct capability_registry *registry, struct capability_space *spaces,
                              uint32_t space_count, capability_retain retain,
                              capability_release release, void *context)
{
    *registry = (struct capability_registry){
        .spaces = spaces,
        .space_count = space_count,
        .retain = retain,
        .release = release,
        .context = context,
    };
    for (uint32_t index = 0; index < space_count; index++) {
        spaces[index] = (struct capability_space){0};
    }
}

void capability_space_attach(struct capability_registry *registry, uint32_t space,
                             struct slot_record *records, struct capability *entries,
                             uint32_t capacity)
{
    slot_table_init(&registry->spaces[space].slots, records, capacity, SLOT_MAX_GENERATION);
    registry->spaces[space].entries = entries;
}

bool capability_space_open(struct capability_registry *registry, uint32_t space, uint32_t limit)
{
    struct capability_space *opened;

    if (space >= registry->space_count || registry->spaces[space].active ||
        registry->spaces[space].entries == NULL) {
        return false;
    }
    opened = &registry->spaces[space];
    opened->limit = limit < opened->slots.capacity ? limit : opened->slots.capacity;
    opened->active = true;
    return true;
}

void capability_space_close(struct capability_registry *registry, uint32_t space)
{
    struct capability_space *closed = active_space(registry, space);

    if (closed == NULL) {
        return;
    }
    for (uint32_t slot = 0; slot < closed->slots.capacity; slot++) {
        if (closed->slots.records[slot].occupied) {
            remove_entry(registry, space, slot, true);
        }
    }
    closed->active = false;
}

uint32_t capability_space_live(const struct capability_registry *registry, uint32_t space)
{
    const struct capability_space *counted = active_space(registry, space);

    return counted == NULL ? 0 : counted->slots.live;
}

int64_t capability_install(struct capability_registry *registry, uint32_t space, uint64_t object,
                           uint32_t rights)
{
    if (!rights_are_valid(rights)) {
        return -KERNEL_ERROR_INVALID_ARGUMENT;
    }
    return place(registry, space, object, rights, no_link, 0);
}

int64_t capability_derive(struct capability_registry *registry, uint32_t space, uint64_t handle,
                          uint32_t rights, uint32_t destination)
{
    struct capability *source;
    uint32_t slot;
    int64_t derived;

    if (!slot_of(registry, space, handle, &slot)) {
        return -KERNEL_ERROR_INVALID_HANDLE;
    }
    source = &registry->spaces[space].entries[slot];
    if (!rights_are_valid(rights)) {
        return -KERNEL_ERROR_INVALID_ARGUMENT;
    }
    if ((source->rights & RIGHT_DELEGATE) == 0 || (rights & ~source->rights) != 0) {
        return -KERNEL_ERROR_ACCESS_DENIED;
    }
    if (source->depth >= CAPABILITY_MAX_DEPTH) {
        return -KERNEL_ERROR_LIMIT_EXCEEDED;
    }
    derived = place(registry, destination, source->object, rights,
                    link_to(&registry->spaces[space], space, slot), (uint8_t)(source->depth + 1u));
    if (derived > 0) {
        source->children++;
        registry->retain(registry->context, source->object);
    }
    return derived;
}

bool capability_find(const struct capability_registry *registry, uint32_t space, uint64_t handle,
                     struct capability *found)
{
    uint32_t slot;

    if (!slot_of(registry, space, handle, &slot)) {
        return false;
    }
    *found = registry->spaces[space].entries[slot];
    return true;
}

int64_t capability_close(struct capability_registry *registry, uint32_t space, uint64_t handle)
{
    uint32_t slot;

    if (!slot_of(registry, space, handle, &slot)) {
        return -KERNEL_ERROR_INVALID_HANDLE;
    }
    remove_entry(registry, space, slot, true);
    return KERNEL_OK;
}

int64_t capability_revoke(struct capability_registry *registry, uint32_t space, uint64_t handle)
{
    uint32_t slot;

    if (!slot_of(registry, space, handle, &slot)) {
        return -KERNEL_ERROR_INVALID_HANDLE;
    }
    if (registry->spaces[space].entries[slot].children == 0) {
        return 0;
    }
    mark_descendants(registry, link_to(&registry->spaces[space], space, slot));
    return sweep_marked(registry);
}
