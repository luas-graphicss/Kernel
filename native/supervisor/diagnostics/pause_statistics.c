#include "kernel/diagnostics/pause_statistics.h"

#define PERCENTILE_EXCLUDED_FRACTION 100u

static uint64_t saturating_add(uint64_t total, uint64_t amount)
{
    return amount > UINT64_MAX - total ? UINT64_MAX : total + amount;
}

void pause_histogram_record(struct pause_histogram *histogram, uint64_t nanoseconds)
{
    uint64_t bucket = nanoseconds / PAUSE_BUCKET_NANOSECONDS;

    histogram->count = saturating_add(histogram->count, 1);
    histogram->total_nanoseconds = saturating_add(histogram->total_nanoseconds, nanoseconds);
    if (nanoseconds > histogram->longest_nanoseconds) {
        histogram->longest_nanoseconds = nanoseconds;
    }
    if (bucket < PAUSE_BUCKETS) {
        histogram->buckets[bucket] = saturating_add(histogram->buckets[bucket], 1);
    } else {
        histogram->beyond_buckets = saturating_add(histogram->beyond_buckets, 1);
    }
}

struct pause_summary pause_histogram_summary(const struct pause_histogram *histogram)
{
    struct pause_summary summary = {
        .count = histogram->count,
        .total_nanoseconds = histogram->total_nanoseconds,
        .longest_nanoseconds = histogram->longest_nanoseconds,
        .percentile_99_nanoseconds = histogram->longest_nanoseconds,
    };
    uint64_t needed = histogram->count - histogram->count / PERCENTILE_EXCLUDED_FRACTION;
    uint64_t covered = 0;

    for (uint64_t bucket = 0; bucket < PAUSE_BUCKETS && histogram->count != 0; bucket++) {
        uint64_t upper_edge = (bucket + 1) * PAUSE_BUCKET_NANOSECONDS;

        covered = saturating_add(covered, histogram->buckets[bucket]);
        if (covered >= needed) {
            if (upper_edge < histogram->longest_nanoseconds) {
                summary.percentile_99_nanoseconds = upper_edge;
            }
            break;
        }
    }
    return summary;
}
