#ifndef KERNEL_DIAGNOSTICS_PAUSE_STATISTICS_H
#define KERNEL_DIAGNOSTICS_PAUSE_STATISTICS_H

#include <stdint.h>

#define PAUSE_BUCKETS 400u
#define PAUSE_BUCKET_NANOSECONDS 250000ull

struct pause_histogram {
    uint64_t count;
    uint64_t total_nanoseconds;
    uint64_t longest_nanoseconds;
    uint64_t beyond_buckets;
    uint64_t buckets[PAUSE_BUCKETS];
};

struct pause_summary {
    uint64_t count;
    uint64_t total_nanoseconds;
    uint64_t longest_nanoseconds;
    uint64_t percentile_99_nanoseconds;
};

void pause_histogram_record(struct pause_histogram *histogram, uint64_t nanoseconds);
struct pause_summary pause_histogram_summary(const struct pause_histogram *histogram);

#endif
