#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "targets.h"

#define COVERAGE_SLOTS 65536u
#define MAX_FRESH_SLOTS 1024u
#define MAX_INPUT_BYTES 131072u
#define LENGTH_BYTES 4u
#define RESULT_BYTES 8u
#define COUNT_BYTES 2u
#define SLOT_BYTES 4u
#define BITS_PER_BYTE 8u
#define EXIT_USAGE 2

static uint8_t coverage_seen[COVERAGE_SLOTS];
static uint32_t fresh_slots[MAX_FRESH_SLOTS];
static uint32_t fresh_count;

void __sanitizer_cov_trace_pc(void);

void __sanitizer_cov_trace_pc(void)
{
    uintptr_t location = (uintptr_t)__builtin_return_address(0);
    uint32_t slot = (uint32_t)((location ^ (location >> 16)) % COVERAGE_SLOTS);

    if (coverage_seen[slot] == 0 && fresh_count < MAX_FRESH_SLOTS) {
        coverage_seen[slot] = 1;
        fresh_slots[fresh_count++] = slot;
    }
}

static void put_unsigned(uint8_t *bytes, size_t width, uint64_t value)
{
    for (size_t index = 0; index < width; index++) {
        bytes[index] = (uint8_t)(value >> (index * BITS_PER_BYTE));
    }
}

static void respond(int64_t result)
{
    uint8_t header[RESULT_BYTES + COUNT_BYTES];
    uint8_t slot[SLOT_BYTES];

    put_unsigned(header, RESULT_BYTES, (uint64_t)result);
    put_unsigned(header + RESULT_BYTES, COUNT_BYTES, fresh_count);
    fwrite(header, 1, sizeof(header), stdout);
    for (uint32_t index = 0; index < fresh_count; index++) {
        put_unsigned(slot, SLOT_BYTES, fresh_slots[index]);
        fwrite(slot, 1, sizeof(slot), stdout);
    }
    if (fflush(stdout) != 0) {
        exit(EXIT_FAILURE);
    }
}

static int serve(fuzz_entry run)
{
    uint8_t prefix[LENGTH_BYTES];
    uint32_t length = 0;
    uint8_t *input;
    int64_t result;

    if (fread(prefix, 1, LENGTH_BYTES, stdin) != LENGTH_BYTES) {
        return 0;
    }
    for (size_t index = 0; index < LENGTH_BYTES; index++) {
        length |= (uint32_t)prefix[index] << (index * BITS_PER_BYTE);
    }
    if (length > MAX_INPUT_BYTES) {
        exit(EXIT_USAGE);
    }
    input = malloc(length);
    if (length != 0 && (input == NULL || fread(input, 1, length, stdin) != length)) {
        exit(EXIT_USAGE);
    }
    fresh_count = 0;
    result = run(input, length);
    free(input);
    respond(result);
    return 1;
}

int main(int argument_count, char **arguments)
{
    fuzz_entry run;

    if (argument_count != 2) {
        return EXIT_USAGE;
    }
    run = fuzz_target_entry(strtoul(arguments[1], NULL, 10));
    if (run == NULL) {
        return EXIT_USAGE;
    }
    while (serve(run)) {
    }
    return EXIT_SUCCESS;
}
