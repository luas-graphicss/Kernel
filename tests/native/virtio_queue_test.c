#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "check.h"
#include "kernel/abi/errors.h"
#include "kernel/devices/virtio_queue.h"
#include "virtqueue_peer.h"

#define DIRTY_BYTE 0xa5
#define WRAPPING_REQUESTS 70000u
#define REQUEST_ADDRESS 0x80200000ull
#define HEADER_BYTES 16u
#define SECTOR_BYTES 512u
#define STATUS_BYTES 1u
#define DESCRIPTOR_BYTES 16u
#define RING_HEADER_BYTES 6u
#define AVAILABLE_ENTRY_BYTES 2u
#define USED_ENTRY_BYTES 8u

static _Alignas(VIRTIO_QUEUE_BYTES) uint8_t memory[VIRTIO_QUEUE_BYTES];
static struct virtio_queue queue;
static struct virtqueue_peer peer;

static void open_queue(void)
{
    memset(memory, DIRTY_BYTE, sizeof(memory));
    virtio_queue_init(&queue, memory);
    virtqueue_peer_attach(&peer, virtio_queue_descriptor_area(&queue),
                          virtio_queue_driver_area(&queue), virtio_queue_device_area(&queue));
}

static bool memory_is_clear(void)
{
    for (size_t index = 0; index < sizeof(memory); index++) {
        if (memory[index] != 0) {
            return false;
        }
    }
    return true;
}

static int64_t add_readable(uint32_t length)
{
    const struct virtio_segment segment = {REQUEST_ADDRESS, length, false};

    return virtio_queue_add(&queue, &segment, 1);
}

static int64_t add_block_read(void)
{
    const struct virtio_segment segments[] = {
        {REQUEST_ADDRESS, HEADER_BYTES, false},
        {REQUEST_ADDRESS + HEADER_BYTES, SECTOR_BYTES, true},
        {REQUEST_ADDRESS + HEADER_BYTES + SECTOR_BYTES, STATUS_BYTES, true},
    };

    return virtio_queue_add(&queue, segments, 3);
}

static int64_t add_longest_chain(void)
{
    struct virtio_segment segments[DEVICE_SEGMENTS];

    for (uint32_t index = 0; index < DEVICE_SEGMENTS; index++) {
        segments[index] = (struct virtio_segment){REQUEST_ADDRESS, HEADER_BYTES, false};
    }
    return virtio_queue_add(&queue, segments, DEVICE_SEGMENTS);
}

static enum virtio_used take_used(uint32_t *chain, uint32_t *written)
{
    return virtio_queue_take_used(&queue, chain, written);
}

static bool next_is_violation(void)
{
    uint32_t chain = 0;
    uint32_t written = 0;

    return take_used(&chain, &written) == VIRTIO_USED_VIOLATION;
}

static uint32_t mark_chain(uint16_t head, bool *marked)
{
    uint32_t fresh = 0;
    uint16_t index = head;

    for (uint32_t position = 0; position < DEVICE_SEGMENTS; position++) {
        struct virtqueue_descriptor descriptor = virtqueue_peer_descriptor(&peer, index);

        if (!marked[index]) {
            marked[index] = true;
            fresh++;
        }
        if ((descriptor.flags & VIRTQUEUE_DESCRIPTOR_CONTINUES) == 0) {
            break;
        }
        index = descriptor.next;
    }
    return fresh;
}

static void test_a_new_queue_is_clear_and_split_into_three_areas(void)
{
    uint32_t chain = 0;
    uint32_t written = 0;
    uint64_t base = (uint64_t)(uintptr_t)memory;
    uint64_t descriptors;
    uint64_t driver_ring;
    uint64_t device_ring;

    open_queue();
    descriptors = virtio_queue_descriptor_area(&queue);
    driver_ring = virtio_queue_driver_area(&queue);
    device_ring = virtio_queue_device_area(&queue);
    CHECK(memory_is_clear());
    CHECK(virtio_queue_in_flight(&queue) == 0);
    CHECK(take_used(&chain, &written) == VIRTIO_USED_EMPTY);
    CHECK(descriptors == base);
    CHECK(driver_ring >= descriptors + VIRTIO_QUEUE_SIZE * DESCRIPTOR_BYTES);
    CHECK(device_ring >= driver_ring + RING_HEADER_BYTES + VIRTIO_QUEUE_SIZE * AVAILABLE_ENTRY_BYTES);
    CHECK(device_ring + RING_HEADER_BYTES + VIRTIO_QUEUE_SIZE * USED_ENTRY_BYTES <=
          base + VIRTIO_QUEUE_BYTES);
}

static void test_a_chain_is_written_in_order_and_published(void)
{
    struct virtqueue_descriptor header;
    struct virtqueue_descriptor data;
    struct virtqueue_descriptor status;

    open_queue();
    CHECK(add_block_read() == 0);
    CHECK(virtqueue_peer_available(&peer) == 1);
    header = virtqueue_peer_descriptor(&peer, virtqueue_peer_newest_head(&peer));
    data = virtqueue_peer_descriptor(&peer, header.next);
    status = virtqueue_peer_descriptor(&peer, data.next);
    CHECK(header.address == REQUEST_ADDRESS && header.length == HEADER_BYTES);
    CHECK(header.flags == VIRTQUEUE_DESCRIPTOR_CONTINUES);
    CHECK(data.address == REQUEST_ADDRESS + HEADER_BYTES && data.length == SECTOR_BYTES);
    CHECK(data.flags == (VIRTQUEUE_DESCRIPTOR_CONTINUES | VIRTQUEUE_DESCRIPTOR_DEVICE_WRITES));
    CHECK(status.address == REQUEST_ADDRESS + HEADER_BYTES + SECTOR_BYTES);
    CHECK(status.length == STATUS_BYTES && status.flags == VIRTQUEUE_DESCRIPTOR_DEVICE_WRITES);
    CHECK(status.next == 0);
    CHECK(virtio_queue_in_flight(&queue) == 1);
}

static void test_malformed_chains_are_refused_before_reaching_the_ring(void)
{
    struct virtio_segment too_many[DEVICE_SEGMENTS + 1u];
    const struct virtio_segment empty_segment[] = {
        {REQUEST_ADDRESS, HEADER_BYTES, false},
        {REQUEST_ADDRESS + HEADER_BYTES, 0, true},
    };
    const struct virtio_segment readable_after_writable[] = {
        {REQUEST_ADDRESS, SECTOR_BYTES, true},
        {REQUEST_ADDRESS + SECTOR_BYTES, HEADER_BYTES, false},
    };

    for (uint32_t index = 0; index <= DEVICE_SEGMENTS; index++) {
        too_many[index] = (struct virtio_segment){REQUEST_ADDRESS, HEADER_BYTES, false};
    }
    open_queue();
    CHECK(virtio_queue_add(&queue, too_many, 0) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(virtio_queue_add(&queue, too_many, DEVICE_SEGMENTS + 1u) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(virtio_queue_add(&queue, empty_segment, 2) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(virtio_queue_add(&queue, readable_after_writable, 2) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(virtio_queue_in_flight(&queue) == 0);
    CHECK(memory_is_clear());
}

static void test_requests_in_flight_are_bounded(void)
{
    uint32_t chain = UINT32_MAX;
    uint32_t written = UINT32_MAX;

    open_queue();
    for (uint32_t slot = 0; slot < DEVICE_REQUESTS; slot++) {
        CHECK(add_longest_chain() == (int64_t)slot);
    }
    CHECK(add_readable(HEADER_BYTES) == -KERNEL_ERROR_LIMIT_EXCEEDED);
    CHECK(virtqueue_peer_available(&peer) == DEVICE_REQUESTS);
    CHECK(virtio_queue_in_flight(&queue) == DEVICE_REQUESTS);

    virtqueue_peer_complete(&peer, virtqueue_peer_head(&peer, 2), 0);
    CHECK(take_used(&chain, &written) == VIRTIO_USED_COMPLETED && chain == 2);
    CHECK(add_longest_chain() == 2);
    CHECK(add_readable(HEADER_BYTES) == -KERNEL_ERROR_LIMIT_EXCEEDED);
}

static void test_completions_name_the_chain_and_the_bytes_written(void)
{
    uint32_t chain = UINT32_MAX;
    uint32_t written = UINT32_MAX;
    uint16_t read_head;
    uint16_t flush_head;

    open_queue();
    CHECK(add_block_read() == 0);
    read_head = virtqueue_peer_newest_head(&peer);
    CHECK(add_readable(HEADER_BYTES) == 1);
    flush_head = virtqueue_peer_newest_head(&peer);

    virtqueue_peer_complete(&peer, flush_head, 0);
    virtqueue_peer_complete(&peer, read_head, SECTOR_BYTES + STATUS_BYTES);
    CHECK(take_used(&chain, &written) == VIRTIO_USED_COMPLETED);
    CHECK(chain == 1 && written == 0);
    CHECK(take_used(&chain, &written) == VIRTIO_USED_COMPLETED);
    CHECK(chain == 0 && written == SECTOR_BYTES + STATUS_BYTES);
    CHECK(take_used(&chain, &written) == VIRTIO_USED_EMPTY);
    CHECK(virtio_queue_in_flight(&queue) == 0);
}

static void test_a_completion_of_nothing_in_flight_is_a_violation(void)
{
    open_queue();
    virtqueue_peer_publish_used(&peer, 1);
    CHECK(next_is_violation());

    open_queue();
    CHECK(add_readable(HEADER_BYTES) == 0);
    virtqueue_peer_publish_used(&peer, 2);
    CHECK(next_is_violation());
    CHECK(virtio_queue_in_flight(&queue) == 1);
}

static void test_a_duplicated_completion_is_a_violation(void)
{
    uint32_t chain = UINT32_MAX;
    uint32_t written = UINT32_MAX;
    uint16_t first_head;

    open_queue();
    CHECK(add_readable(HEADER_BYTES) == 0);
    first_head = virtqueue_peer_newest_head(&peer);
    CHECK(add_readable(HEADER_BYTES) == 1);
    virtqueue_peer_complete(&peer, first_head, 0);
    virtqueue_peer_complete(&peer, first_head, 0);
    CHECK(take_used(&chain, &written) == VIRTIO_USED_COMPLETED && chain == 0);
    CHECK(next_is_violation());
    CHECK(virtio_queue_in_flight(&queue) == 1);
}

static void test_a_completion_must_name_the_head_of_a_chain(void)
{
    struct virtqueue_descriptor header;

    open_queue();
    CHECK(add_block_read() == 0);
    header = virtqueue_peer_descriptor(&peer, virtqueue_peer_newest_head(&peer));
    virtqueue_peer_complete(&peer, header.next, 0);
    CHECK(next_is_violation());

    open_queue();
    CHECK(add_block_read() == 0);
    virtqueue_peer_complete(&peer, VIRTIO_QUEUE_SIZE, 0);
    CHECK(next_is_violation());

    open_queue();
    CHECK(add_block_read() == 0);
    virtqueue_peer_complete(&peer, UINT32_MAX, 0);
    CHECK(next_is_violation());
    CHECK(virtio_queue_in_flight(&queue) == 1);
}

static void test_a_completion_cannot_write_more_than_the_chain_allows(void)
{
    open_queue();
    CHECK(add_block_read() == 0);
    virtqueue_peer_complete(&peer, virtqueue_peer_newest_head(&peer),
                            SECTOR_BYTES + STATUS_BYTES + 1u);
    CHECK(next_is_violation());

    open_queue();
    CHECK(add_readable(HEADER_BYTES) == 0);
    virtqueue_peer_complete(&peer, virtqueue_peer_newest_head(&peer), 1);
    CHECK(next_is_violation());
    CHECK(virtio_queue_in_flight(&queue) == 1);
}

static void test_a_rewritten_descriptor_table_does_not_change_what_is_released(void)
{
    bool marked[VIRTIO_QUEUE_SIZE] = {false};
    uint32_t chain = UINT32_MAX;
    uint32_t written = UINT32_MAX;
    uint32_t distinct = 0;
    uint16_t read_head;
    uint16_t flush_head;

    open_queue();
    CHECK(add_block_read() == 0);
    read_head = virtqueue_peer_newest_head(&peer);
    CHECK(add_readable(HEADER_BYTES) == 1);
    flush_head = virtqueue_peer_newest_head(&peer);
    for (uint16_t index = 0; index < VIRTIO_QUEUE_SIZE; index++) {
        virtqueue_peer_write_descriptor(&peer, index,
                                        (struct virtqueue_descriptor){
                                            .address = UINT64_MAX,
                                            .length = UINT32_MAX,
                                            .flags = VIRTQUEUE_DESCRIPTOR_CONTINUES,
                                            .next = index,
                                        });
    }

    virtqueue_peer_complete(&peer, read_head, STATUS_BYTES);
    CHECK(take_used(&chain, &written) == VIRTIO_USED_COMPLETED);
    CHECK(chain == 0 && written == STATUS_BYTES);
    CHECK(virtio_queue_in_flight(&queue) == 1);
    virtqueue_peer_complete(&peer, flush_head, 0);
    CHECK(take_used(&chain, &written) == VIRTIO_USED_COMPLETED && chain == 1);

    for (uint32_t slot = 0; slot < DEVICE_REQUESTS; slot++) {
        CHECK(add_longest_chain() == (int64_t)slot);
        distinct += mark_chain(virtqueue_peer_newest_head(&peer), marked);
    }
    CHECK(distinct == VIRTIO_QUEUE_SIZE);
}

static void test_ring_indices_wrap_without_losing_requests(void)
{
    uint32_t completed = 0;

    open_queue();
    for (uint32_t request = 0; request < WRAPPING_REQUESTS; request++) {
        bool reads = request % 2u == 0;
        uint32_t allowed = reads ? SECTOR_BYTES + STATUS_BYTES : 0;
        int64_t slot = reads ? add_block_read() : add_readable(HEADER_BYTES);
        uint32_t chain = UINT32_MAX;
        uint32_t written = UINT32_MAX;

        virtqueue_peer_complete(&peer, virtqueue_peer_newest_head(&peer), allowed);
        if (slot == 0 && take_used(&chain, &written) == VIRTIO_USED_COMPLETED && chain == 0 &&
            written == allowed) {
            completed++;
        }
    }
    CHECK(completed == WRAPPING_REQUESTS);
    CHECK(virtqueue_peer_available(&peer) == (uint16_t)WRAPPING_REQUESTS);
    CHECK(virtio_queue_in_flight(&queue) == 0);
}

static void test_reset_forgets_every_chain(void)
{
    uint32_t chain = 0;
    uint32_t written = 0;

    open_queue();
    CHECK(add_block_read() == 0);
    CHECK(add_readable(HEADER_BYTES) == 1);
    virtqueue_peer_complete(&peer, virtqueue_peer_newest_head(&peer), 0);
    virtio_queue_reset(&queue);
    CHECK(memory_is_clear());
    CHECK(virtio_queue_in_flight(&queue) == 0);
    CHECK(take_used(&chain, &written) == VIRTIO_USED_EMPTY);
    CHECK(add_readable(HEADER_BYTES) == 0);
    CHECK(virtqueue_peer_available(&peer) == 1);
}

int main(void)
{
    test_a_new_queue_is_clear_and_split_into_three_areas();
    test_a_chain_is_written_in_order_and_published();
    test_malformed_chains_are_refused_before_reaching_the_ring();
    test_requests_in_flight_are_bounded();
    test_completions_name_the_chain_and_the_bytes_written();
    test_a_completion_of_nothing_in_flight_is_a_violation();
    test_a_duplicated_completion_is_a_violation();
    test_a_completion_must_name_the_head_of_a_chain();
    test_a_completion_cannot_write_more_than_the_chain_allows();
    test_a_rewritten_descriptor_table_does_not_change_what_is_released();
    test_ring_indices_wrap_without_losing_requests();
    test_reset_forgets_every_chain();
    return check_finish("virtio-queue");
}
