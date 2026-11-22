#ifndef TERENTO_FINISHING_TRACE_H
#define TERENTO_FINISHING_TRACE_H
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <fcntl.h>

/* Fixed numeric diagnostics only. The parent supplies a private worker file. */
typedef struct {
    int enabled;
    int fd;
    double last_checkpoint;
    uint64_t last_verified_end;
    uint64_t verified_bytes;
} TerentoFinishingTrace;

static double terento_trace_time(void) {
    struct timespec time;
    clock_gettime(CLOCK_MONOTONIC, &time);
    return (double)time.tv_sec + (double)time.tv_nsec / 1000000000.0;
}

static TerentoFinishingTrace terento_trace_start(void) {
    TerentoFinishingTrace trace = {0};
    trace.fd = -1;
    const char *path = getenv("TERENTO_FINISHING_TRACE_FILE");
    if (path != NULL) {
        trace.fd = open(path, O_WRONLY | O_APPEND | O_CREAT | O_NOFOLLOW, 0600);
        trace.enabled = trace.fd >= 0;
    }
#if defined(DEBUG) && DEBUG
    const char *flag = getenv("TERENTO_FINISHING_TRACE");
    if (!trace.enabled && flag != NULL && strcmp(flag, "1") == 0) {
        trace.fd = STDERR_FILENO;
        trace.enabled = 1;
    }
#endif
    return trace;
}

static void terento_trace_event(TerentoFinishingTrace *trace, const char *event,
                               uint64_t offset, int rc, uint64_t detail) {
    if (!trace->enabled) return;
    char line[384];
    int length = snprintf(line, sizeof(line),
        "FINISH_TRACE native t=%.6f pid=%d event=%s offset=%llu rc=%d detail=%llu last_verified_end=%llu verified_bytes=%llu\n",
        terento_trace_time(), getpid(), event, (unsigned long long)offset, rc,
        (unsigned long long)detail, (unsigned long long)trace->last_verified_end,
        (unsigned long long)trace->verified_bytes);
    if (length > 0 && length < (int)sizeof(line)) {
        /* One bounded local write; failure must never affect verification. */
        (void)write(trace->fd, line, (size_t)length);
    }
}

static void terento_trace_finish(TerentoFinishingTrace *trace) {
    if (trace->fd >= 0 && trace->fd != STDERR_FILENO) close(trace->fd);
}

static void terento_trace_verified(TerentoFinishingTrace *trace,
                                  uint64_t end, uint64_t bytes) {
    if (!trace->enabled) return;
    trace->last_verified_end = end;
    trace->verified_bytes = bytes;
    double now = terento_trace_time();
    if (now - trace->last_checkpoint >= 0.25) {
        trace->last_checkpoint = now;
        terento_trace_event(trace, "read_checkpoint", end, 0, bytes);
    }
}

/* Per-chunk read timing of one sampled read-back: how many chunks, their
   bytes, the summed watch read time, the slowest watch read with its file
   offset, and the summed local source read and compare time. Numbers only.
   Timing never changes which bytes are read or compared. */
typedef struct {
    uint32_t chunks;
    uint64_t bytes;
    double total_ms;
    double slowest_ms;
    uint64_t slowest_offset;
    double local_ms;
} TerentoReadTiming;

static void terento_read_timing_add(TerentoReadTiming *timing, double device_seconds,
                                    double local_seconds, uint64_t offset, uint32_t bytes) {
    double device_ms = device_seconds > 0 ? device_seconds * 1000.0 : 0;
    timing->chunks += 1;
    timing->bytes += bytes;
    timing->total_ms += device_ms;
    timing->local_ms += local_seconds > 0 ? local_seconds * 1000.0 : 0;
    if (timing->chunks == 1 || device_ms > timing->slowest_ms) {
        timing->slowest_ms = device_ms;
        timing->slowest_offset = offset;
    }
}

/* `region_timing` (with the sample index) after each sample region and
   `read_timing` once for the whole read-back. mbps = bytes / watch time. */
static void terento_trace_read_timing(TerentoFinishingTrace *trace, const char *event,
                                      int region, const TerentoReadTiming *timing) {
    if (!trace->enabled) return;
    char line[384];
    char region_field[32] = "";
    if (region >= 0) snprintf(region_field, sizeof(region_field), " region=%d", region);
    double seconds = timing->total_ms / 1000.0;
    double mbps = seconds > 0 ? (double)timing->bytes / seconds / 1000000.0 : 0;
    int length = snprintf(line, sizeof(line),
        "FINISH_TRACE native t=%.6f pid=%d event=%s%s chunks=%u bytes=%llu total_ms=%.0f slowest_ms=%.0f slowest_offset=%llu local_ms=%.0f mbps=%.2f\n",
        terento_trace_time(), getpid(), event, region_field, timing->chunks,
        (unsigned long long)timing->bytes, timing->total_ms, timing->slowest_ms,
        (unsigned long long)timing->slowest_offset, timing->local_ms, mbps);
    if (length > 0 && length < (int)sizeof(line)) {
        (void)write(trace->fd, line, (size_t)length);
    }
}
#endif
