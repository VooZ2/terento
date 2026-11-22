#ifndef TERENTO_SAMPLE_COVERAGE_H
#define TERENTO_SAMPLE_COVERAGE_H
#include <stddef.h>
#include <stdint.h>

#define TERENTO_MAX_MAP_SAMPLES 32

typedef struct {
    uint64_t offset;
    uint32_t length;
} TerentoSampleRegion;

/* Garmin's split data phase can end at an exact USB packet boundary.
 * An odd payload length ends in a short packet for USB bulk packet sizes,
 * avoiding libmtp's separate zero-length terminator read. The next request
 * still reads the remaining byte; sample coverage is never shortened. */
static uint32_t terento_sample_read_request_within(uint32_t remaining, int short_packet, uint32_t limit) {
    uint32_t requested = remaining > limit ? limit : remaining;
    if (short_packet && requested > 0 && (requested % 2) == 0) requested--;
    return requested;
}

#define TERENTO_SAMPLE_READ_DEFAULT_LIMIT (64u * 1024u)
#define TERENTO_SAMPLE_READ_LARGE_LIMIT (1024u * 1024u)

static uint32_t terento_sample_read_request(uint32_t remaining, int short_packet) {
    return terento_sample_read_request_within(remaining, short_packet, TERENTO_SAMPLE_READ_DEFAULT_LIMIT);
}

/* Request size for sampled checks (post-install read-back, recorded samples).
 * Owner's fenix 8 AMOLED (091e:51b8), firmware 24.20, read-only probe
 * 2026-11-22: every GetPartialObject of 64 KiB or 256 KiB took ~0.5 s
 * (0.14 / 0.57 MB/s), 1 MiB requests ~0.14 s (6.8-7.8 MB/s), same bytes.
 * On firmware 23.39 (2026-10-10) all sizes read ~1.7 MB/s. Owner decision
 * 2026-11-22: 1 MiB for every Garmin. Only the request size changes: every
 * sampled byte is still read and compared. */
static uint32_t terento_sample_read_limit(uint16_t vendor_id, uint16_t product_id) {
    (void)product_id;
    return vendor_id == 0x091e ? TERENTO_SAMPLE_READ_LARGE_LIMIT : TERENTO_SAMPLE_READ_DEFAULT_LIMIT;
}

/* Keep every requested byte, reading overlaps only once. Each output entry
   still represents one original sample; length zero means earlier entries
   cover it completely. Callers must verify entries in this sorted order. */
static int terento_plan_sample_coverage(
    uint64_t file_size, const uint64_t *offsets, size_t count,
    uint32_t sample_length, TerentoSampleRegion *regions, uint64_t *total
) {
    if (file_size == 0 || offsets == NULL || regions == NULL || total == NULL
        || count == 0 || count > TERENTO_MAX_MAP_SAMPLES || sample_length == 0) return -1;
    *total = 0;
    for (size_t i = 0; i < count; i++) {
        if (offsets[i] >= file_size) return -1;
        regions[i].offset = offsets[i];
        size_t j = i;
        while (j > 0 && regions[j].offset < regions[j - 1].offset) {
            uint64_t swap = regions[j - 1].offset;
            regions[j - 1].offset = regions[j].offset;
            regions[j].offset = swap;
            j--;
        }
    }
    uint64_t covered_end = 0;
    for (size_t i = 0; i < count; i++) {
        uint64_t start = regions[i].offset;
        uint64_t available = file_size - start;
        uint64_t length = available < sample_length ? available : sample_length;
        uint64_t end = start + length; /* bounded by file_size, cannot overflow */
        if (start < covered_end) start = covered_end;
        regions[i].offset = start;
        regions[i].length = start < end ? (uint32_t)(end - start) : 0;
        *total += regions[i].length; /* disjoint ranges, bounded by file_size */
        if (end > covered_end) covered_end = end;
    }
    return 0;
}
#endif
