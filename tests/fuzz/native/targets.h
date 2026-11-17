#ifndef TESTS_FUZZ_NATIVE_TARGETS_H
#define TESTS_FUZZ_NATIVE_TARGETS_H

#include <stddef.h>
#include <stdint.h>

typedef int64_t (*fuzz_entry)(const uint8_t *data, size_t length);

int64_t fuzz_device_tree(const uint8_t *data, size_t length);
int64_t fuzz_user_image(const uint8_t *data, size_t length);
int64_t fuzz_ipc_message(const uint8_t *data, size_t length);
int64_t fuzz_spawn_request(const uint8_t *data, size_t length);

fuzz_entry fuzz_target_entry(unsigned long index);
_Noreturn void fuzz_invariant_violated(const char *invariant);

#define FUZZ_REQUIRE(condition) ((condition) ? (void)0 : fuzz_invariant_violated(#condition))

#endif
