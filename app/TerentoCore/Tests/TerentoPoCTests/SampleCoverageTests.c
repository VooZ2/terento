#include "SampleCoverage.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

/* Independent byte bitmap checks exact original coverage, not the planner's
   algorithm. The output emulates production's bounded 64 KiB read requests. */
static void check_bytes(uint64_t size, const uint64_t *offsets, size_t count,
                        uint32_t length, uint64_t expected_total) {
    unsigned char *requested = calloc((size_t)size, 1);
    unsigned char *read = calloc((size_t)size, 1);
    assert(requested && read);
    for (size_t i = 0; i < count; i++) {
        for (uint64_t j = offsets[i]; j < size && j - offsets[i] < length; j++)
            requested[j] = 1;
    }
    TerentoSampleRegion regions[TERENTO_MAX_MAP_SAMPLES];
    uint64_t total = 0, actual = 0;
    assert(terento_plan_sample_coverage(size, offsets, count, length, regions, &total) == 0);
    for (size_t i = 0; i < count; i++) {
        for (uint32_t consumed = 0; consumed < regions[i].length;) {
            uint32_t chunk = regions[i].length - consumed;
            if (chunk > 65536) chunk = 65536;
            uint64_t start = regions[i].offset + consumed;
            assert(start < size && chunk <= size - start);
            for (uint64_t j = start; j < start + chunk; j++) {
                assert(read[j] == 0); /* no repeated device byte reads */
                read[j] = 1;
            }
            consumed += chunk;
            actual += chunk;
        }
    }
    uint64_t requested_total = 0;
    for (uint64_t j = 0; j < size; j++) {
        assert(requested[j] == read[j]); /* no omitted or added byte */
        requested_total += requested[j];
    }
    assert(total == requested_total && actual == total && total <= size);
    if (expected_total != UINT64_MAX) assert(total == expected_total);
    free(requested);
    free(read);
}

int main(void) {
    uint64_t single[] = {0};
    check_bytes(1, single, 1, 4194304, 1);
    check_bytes(4096, single, 1, 4194304, 4096);
    check_bytes(4194304, single, 1, 4194304, 4194304);
    uint64_t andorra[] = {397312, 0, 310000, 75000, 180000, 230000, 370000};
    check_bytes(4591616, andorra, 7, 4194304, 4591616);
    uint64_t large[] = {0, 8 * 1024 * 1024, 16 * 1024 * 1024};
    check_bytes(20 * 1024 * 1024, large, 3, 4194304, 12 * 1024 * 1024);
    uint64_t tail[] = {999, 0, 990, 0};
    check_bytes(1000, tail, 4, 64, 74);
    /* Exhaustive unordered/duplicate/overlapping/disjoint small intervals. */
    for (uint64_t size = 1; size <= 17; size++) {
        for (uint64_t a = 0; a < size; a++) {
            for (uint64_t b = 0; b < size; b++) {
                uint64_t offsets[] = {a, b, size - 1};
                for (uint32_t length = 1; length <= 20; length++)
                    check_bytes(size, offsets, 3, length, UINT64_MAX);
            }
        }
    }
    TerentoSampleRegion regions[TERENTO_MAX_MAP_SAMPLES];
    uint64_t total, offsets[33] = {0};
    assert(terento_plan_sample_coverage(0, offsets, 1, 1, regions, &total) != 0);
    assert(terento_plan_sample_coverage(1, offsets, 0, 1, regions, &total) != 0);
    assert(terento_plan_sample_coverage(1, offsets, 33, 1, regions, &total) != 0);
    assert(terento_plan_sample_coverage(1, offsets, 1, 0, regions, &total) != 0);
    offsets[0] = 1;
    assert(terento_plan_sample_coverage(1, offsets, 1, 1, regions, &total) != 0);
    offsets[0] = UINT64_MAX - 3;
    assert(terento_plan_sample_coverage(UINT64_MAX, offsets, 1, UINT32_MAX, regions, &total) == 0);
    assert(total == 3 && regions[0].length == 3);
    puts("PASS: native sample coverage preserves every requested byte, without overlap or out-of-range reads");
    puts("PASS: Andorra 7 x 4 MiB verification reads 4,591,616 unique bytes; minimum, tail, large, and overflow bounds pass");
    return 0;
}
