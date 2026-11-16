#include <stdint.h>
#include <string.h>

#include "check.h"
#include "kernel/abi/errors.h"
#include "kernel/abi/rights.h"
#include "kernel/capabilities/capability_space.h"

#define SPACES 3u
#define SLOTS 24u
#define OBJECTS 8u
#define ENDPOINT_RIGHTS (RIGHT_SEND | RIGHT_RECEIVE | RIGHT_DELEGATE)

static struct capability_space spaces[SPACES];
static struct slot_record records[SPACES][SLOTS];
static struct capability entries[SPACES][SLOTS];
static struct capability_registry registry;
static int references[OBJECTS];
static uint32_t released_rights[OBJECTS];

static void retain(void *context, uint64_t object)
{
    (void)context;
    references[object]++;
}

static void release(void *context, uint64_t object, uint32_t rights)
{
    (void)context;
    references[object]--;
    released_rights[object] = rights;
}

static void fresh_registry(uint32_t limit)
{
    memset(references, 0, sizeof(references));
    memset(released_rights, 0, sizeof(released_rights));
    capability_registry_init(&registry, spaces, SPACES, retain, release, NULL);
    for (uint32_t space = 0; space < SPACES; space++) {
        capability_space_attach(&registry, space, records[space], entries[space], SLOTS);
        CHECK(capability_space_open(&registry, space, limit));
    }
}

static uint64_t install(uint32_t space, uint64_t object, uint32_t rights)
{
    int64_t handle = capability_install(&registry, space, object, rights);

    CHECK(handle > 0);
    references[object]++;
    return (uint64_t)handle;
}

static uint64_t derive(uint32_t space, uint64_t handle, uint32_t rights, uint32_t destination)
{
    int64_t derived = capability_derive(&registry, space, handle, rights, destination);

    CHECK(derived > 0);
    return (uint64_t)derived;
}

static bool exists(uint32_t space, uint64_t handle)
{
    struct capability found;

    return capability_find(&registry, space, handle, &found);
}

static void test_installed_capability_names_its_object(void)
{
    struct capability found;
    uint64_t handle;

    fresh_registry(SLOTS);
    handle = install(0, 5, ENDPOINT_RIGHTS);
    CHECK(capability_find(&registry, 0, handle, &found));
    CHECK(found.object == 5 && found.rights == ENDPOINT_RIGHTS && found.depth == 0);
    CHECK(!capability_find(&registry, 1, handle, &found));
    CHECK(capability_install(&registry, 0, 5, 0) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(capability_install(&registry, 0, 5, RIGHTS_ALL + 1u) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(capability_install(&registry, SPACES, 5, RIGHT_SEND) == -KERNEL_ERROR_BAD_STATE);
    CHECK(registry.live == 1);
}

static void test_forged_handles_do_not_resolve(void)
{
    uint64_t handle;

    fresh_registry(SLOTS);
    handle = install(0, 1, ENDPOINT_RIGHTS);
    CHECK(!exists(0, 0));
    CHECK(!exists(0, handle + 1u));
    CHECK(!exists(0, handle + (1ull << SLOT_INDEX_BITS)));
    CHECK(!exists(0, handle | (1ull << 56)));
    CHECK(!exists(0, (1ull << SLOT_INDEX_BITS) | SLOTS));
    CHECK(!exists(0, UINT64_MAX));
    CHECK(capability_close(&registry, 0, handle + 1u) == -KERNEL_ERROR_INVALID_HANDLE);
    CHECK(capability_revoke(&registry, 0, UINT64_MAX) == -KERNEL_ERROR_INVALID_HANDLE);
    CHECK(capability_derive(&registry, 0, 0, RIGHT_SEND, 1) == -KERNEL_ERROR_INVALID_HANDLE);
    CHECK(exists(0, handle));
}

static void test_delegation_only_reduces_rights(void)
{
    struct capability found;
    uint64_t root;
    uint64_t sender;

    fresh_registry(SLOTS);
    root = install(0, 2, ENDPOINT_RIGHTS);
    sender = derive(0, root, RIGHT_SEND, 1);
    CHECK(capability_find(&registry, 1, sender, &found));
    CHECK(found.object == 2 && found.rights == RIGHT_SEND && found.depth == 1);
    CHECK(references[2] == 2);

    CHECK(capability_derive(&registry, 0, root, RIGHT_SEND | RIGHT_ADMIN, 1) ==
          -KERNEL_ERROR_ACCESS_DENIED);
    CHECK(capability_derive(&registry, 0, root, RIGHT_MAP, 1) == -KERNEL_ERROR_ACCESS_DENIED);
    CHECK(capability_derive(&registry, 1, sender, RIGHT_SEND, 2) == -KERNEL_ERROR_ACCESS_DENIED);
    CHECK(capability_derive(&registry, 0, root, 0, 1) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(capability_derive(&registry, 0, root, RIGHTS_ALL + 1u, 1) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(capability_derive(&registry, 0, root, RIGHT_SEND, SPACES) == -KERNEL_ERROR_BAD_STATE);
    CHECK(references[2] == 2 && registry.live == 2);
}

static void test_delegation_depth_is_bounded(void)
{
    uint64_t handle;

    fresh_registry(SLOTS);
    handle = install(0, 3, ENDPOINT_RIGHTS);
    for (uint32_t depth = 1; depth <= CAPABILITY_MAX_DEPTH; depth++) {
        struct capability found;

        handle = derive(0, handle, RIGHT_SEND | RIGHT_DELEGATE, 0);
        CHECK(capability_find(&registry, 0, handle, &found) && found.depth == depth);
    }
    CHECK(capability_derive(&registry, 0, handle, RIGHT_SEND, 0) == -KERNEL_ERROR_LIMIT_EXCEEDED);
    CHECK(references[3] == (int)CAPABILITY_MAX_DEPTH + 1);
}

static void test_quota_failure_changes_nothing(void)
{
    uint64_t root;

    fresh_registry(4);
    root = install(0, 4, ENDPOINT_RIGHTS);
    derive(0, root, RIGHT_SEND, 0);
    derive(0, root, RIGHT_SEND, 0);
    derive(0, root, RIGHT_SEND, 0);
    CHECK(capability_space_live(&registry, 0) == 4);
    CHECK(capability_derive(&registry, 0, root, RIGHT_SEND, 0) == -KERNEL_ERROR_LIMIT_EXCEEDED);
    CHECK(capability_install(&registry, 0, 4, RIGHT_SEND) == -KERNEL_ERROR_LIMIT_EXCEEDED);
    CHECK(capability_space_live(&registry, 0) == 4 && registry.live == 4);
    CHECK(references[4] == 4);
    CHECK(capability_derive(&registry, 0, root, RIGHT_SEND, 1) > 0);
}

static void test_closed_handle_stays_invalid_after_reuse(void)
{
    uint64_t old;
    uint64_t current;

    fresh_registry(SLOTS);
    old = install(0, 1, ENDPOINT_RIGHTS);
    CHECK(capability_close(&registry, 0, old) == KERNEL_OK);
    CHECK(references[1] == 0 && released_rights[1] == ENDPOINT_RIGHTS);
    CHECK(capability_close(&registry, 0, old) == -KERNEL_ERROR_INVALID_HANDLE);
    CHECK(references[1] == 0);
    current = install(0, 6, RIGHT_READ);
    CHECK((current & SLOT_INDEX_MASK) == (old & SLOT_INDEX_MASK) && current != old);
    CHECK(!exists(0, old) && exists(0, current));
    CHECK(capability_derive(&registry, 0, old, RIGHT_SEND, 0) == -KERNEL_ERROR_INVALID_HANDLE);
}

static void test_revocation_reaches_every_descendant(void)
{
    uint64_t root;
    uint64_t local;
    uint64_t remote;
    uint64_t grandchild;
    uint64_t unrelated;

    fresh_registry(SLOTS);
    root = install(0, 1, ENDPOINT_RIGHTS);
    unrelated = install(1, 2, ENDPOINT_RIGHTS);
    local = derive(0, root, RIGHT_SEND, 0);
    remote = derive(0, root, RIGHT_SEND | RIGHT_DELEGATE, 1);
    grandchild = derive(1, remote, RIGHT_SEND, 2);
    CHECK(references[1] == 4);

    CHECK(capability_revoke(&registry, 1, unrelated) == 0);
    CHECK(capability_revoke(&registry, 2, grandchild) == 0);
    CHECK(capability_revoke(&registry, 0, root) == 3);
    CHECK(exists(0, root) && exists(1, unrelated));
    CHECK(!exists(0, local) && !exists(1, remote) && !exists(2, grandchild));
    CHECK(references[1] == 1 && references[2] == 1);
    CHECK(registry.live == 2);
    CHECK(capability_revoke(&registry, 0, root) == 0);
    CHECK(derive(0, root, RIGHT_SEND, 1) != remote);
}

static void test_closing_a_link_keeps_descendants_revocable(void)
{
    uint64_t root;
    uint64_t middle;
    uint64_t leaf;

    fresh_registry(SLOTS);
    root = install(0, 1, ENDPOINT_RIGHTS);
    middle = derive(0, root, RIGHT_SEND | RIGHT_DELEGATE, 1);
    leaf = derive(1, middle, RIGHT_SEND, 2);

    CHECK(capability_close(&registry, 1, middle) == KERNEL_OK);
    CHECK(exists(2, leaf));
    CHECK(capability_revoke(&registry, 0, root) == 1);
    CHECK(!exists(2, leaf));
    CHECK(references[1] == 1);
}

static void test_orphaned_descendants_outlive_the_root(void)
{
    uint64_t root;
    uint64_t child;

    fresh_registry(SLOTS);
    root = install(0, 1, ENDPOINT_RIGHTS);
    child = derive(0, root, RIGHT_SEND | RIGHT_DELEGATE, 1);
    CHECK(capability_close(&registry, 0, root) == KERNEL_OK);
    CHECK(exists(1, child));
    CHECK(capability_revoke(&registry, 1, child) == 0);
    CHECK(references[1] == 1);
}

static void test_closing_a_space_releases_everything_it_held(void)
{
    uint64_t root;
    uint64_t exported;
    uint64_t stale;

    fresh_registry(SLOTS);
    root = install(0, 1, ENDPOINT_RIGHTS);
    stale = install(1, 2, RIGHT_READ);
    exported = derive(0, root, RIGHT_SEND | RIGHT_DELEGATE, 1);
    derive(1, exported, RIGHT_SEND, 2);

    capability_space_close(&registry, 1);
    CHECK(capability_space_live(&registry, 1) == 0);
    CHECK(references[2] == 0 && references[1] == 2);
    CHECK(capability_install(&registry, 1, 2, RIGHT_READ) == -KERNEL_ERROR_BAD_STATE);
    CHECK(capability_revoke(&registry, 0, root) == 1);

    CHECK(capability_space_open(&registry, 1, SLOTS));
    CHECK(!capability_space_open(&registry, 1, SLOTS));
    CHECK(!exists(1, stale) && !exists(1, exported));
    CHECK(install(1, 3, RIGHT_READ) != stale);
    CHECK(!exists(1, stale));
}

int main(void)
{
    test_installed_capability_names_its_object();
    test_forged_handles_do_not_resolve();
    test_delegation_only_reduces_rights();
    test_delegation_depth_is_bounded();
    test_quota_failure_changes_nothing();
    test_closed_handle_stays_invalid_after_reuse();
    test_revocation_reaches_every_descendant();
    test_closing_a_link_keeps_descendants_revocable();
    test_orphaned_descendants_outlive_the_root();
    test_closing_a_space_releases_everything_it_held();
    return check_finish("capability");
}
