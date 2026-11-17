#include <stdint.h>

#include "check.h"
#include "kernel/diagnostics/pause_statistics.h"

#define MILLISECOND 1000000ull

static void record_many(struct pause_histogram *histogram, uint64_t nanoseconds, unsigned count)
{
    for (unsigned index = 0; index < count; index++) {
        pause_histogram_record(histogram, nanoseconds);
    }
}

static void test_an_empty_histogram_reports_nothing(void)
{
    struct pause_histogram histogram = {0};
    struct pause_summary summary = pause_histogram_summary(&histogram);

    CHECK(summary.count == 0);
    CHECK(summary.total_nanoseconds == 0);
    CHECK(summary.longest_nanoseconds == 0);
    CHECK(summary.percentile_99_nanoseconds == 0);
}

static void test_a_single_pause_is_its_own_percentile(void)
{
    struct pause_histogram histogram = {0};
    struct pause_summary summary;

    pause_histogram_record(&histogram, 3 * MILLISECOND + 1);
    summary = pause_histogram_summary(&histogram);
    CHECK(summary.count == 1);
    CHECK(summary.total_nanoseconds == 3 * MILLISECOND + 1);
    CHECK(summary.longest_nanoseconds == 3 * MILLISECOND + 1);
    CHECK(summary.percentile_99_nanoseconds == 3 * MILLISECOND + 1);
}

static void test_one_outlier_in_a_hundred_stays_out_of_the_percentile(void)
{
    struct pause_histogram histogram = {0};
    struct pause_summary summary;

    record_many(&histogram, MILLISECOND, 99);
    pause_histogram_record(&histogram, 80 * MILLISECOND);
    summary = pause_histogram_summary(&histogram);
    CHECK(summary.count == 100);
    CHECK(summary.longest_nanoseconds == 80 * MILLISECOND);
    CHECK(summary.percentile_99_nanoseconds == MILLISECOND + PAUSE_BUCKET_NANOSECONDS);
}

static void test_two_outliers_in_a_hundred_reach_the_percentile(void)
{
    struct pause_histogram histogram = {0};
    struct pause_summary summary;

    record_many(&histogram, MILLISECOND, 98);
    record_many(&histogram, 40 * MILLISECOND, 2);
    summary = pause_histogram_summary(&histogram);
    CHECK(summary.percentile_99_nanoseconds == 40 * MILLISECOND);
}

static void test_pauses_beyond_the_buckets_report_the_longest(void)
{
    struct pause_histogram histogram = {0};
    struct pause_summary summary;
    uint64_t beyond = PAUSE_BUCKETS * PAUSE_BUCKET_NANOSECONDS + 7;

    record_many(&histogram, beyond, 3);
    summary = pause_histogram_summary(&histogram);
    CHECK(histogram.beyond_buckets == 3);
    CHECK(summary.longest_nanoseconds == beyond);
    CHECK(summary.percentile_99_nanoseconds == beyond);
}

static void test_the_total_saturates_instead_of_wrapping(void)
{
    struct pause_histogram histogram = {0};
    struct pause_summary summary;

    pause_histogram_record(&histogram, UINT64_MAX);
    pause_histogram_record(&histogram, UINT64_MAX);
    summary = pause_histogram_summary(&histogram);
    CHECK(summary.count == 2);
    CHECK(summary.total_nanoseconds == UINT64_MAX);
    CHECK(summary.longest_nanoseconds == UINT64_MAX);
}

int main(void)
{
    test_an_empty_histogram_reports_nothing();
    test_a_single_pause_is_its_own_percentile();
    test_one_outlier_in_a_hundred_stays_out_of_the_percentile();
    test_two_outliers_in_a_hundred_reach_the_percentile();
    test_pauses_beyond_the_buckets_report_the_longest();
    test_the_total_saturates_instead_of_wrapping();
    return check_finish("pause-statistics");
}
