#ifndef TERENTO_MUTATION_AUTHORIZATION_H
#define TERENTO_MUTATION_AUTHORIZATION_H
#include "MTPBridge.h"
#include <pthread.h>
#include <string.h>
#include <ctype.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <stdio.h>
#include <limits.h>

/* This context is created only after native live-device and destination checks.
 * Handles are meaningful only during this open native session. */
typedef struct {
    uint64_t session_id;
    uint32_t storage_id;
    uint32_t parent_id;
    int device_verified;
    const char *physical_identifier;
    uint32_t physical_identifier_source;
    const char *target_directory;
} TerentoMutationSession;

typedef int (*TerentoMutationCall)(void *context, uint32_t *resulting_object_id);

/* Bounded, process-lifetime replay protection. Exhaustion refuses new grants.
 * Cross-worker/restart replay is additionally denied by the parent durable ledger. */
static pthread_mutex_t terento_mutation_lock = PTHREAD_MUTEX_INITIALIZER;
static struct { char operation_id[65]; uint32_t sequence; } terento_consumed_grants[4096];
static size_t terento_consumed_count;
static uint64_t terento_session_counter;

static uint64_t terento_new_mutation_session_id(void) {
    pthread_mutex_lock(&terento_mutation_lock);
    uint64_t value = ++terento_session_counter;
    pthread_mutex_unlock(&terento_mutation_lock);
    return value;
}

static int terento_claim_mutation(const TerentoMTPMutationAuthorization *authorization) {
    pthread_mutex_lock(&terento_mutation_lock);
    int allowed = terento_consumed_count < 4096;
    for (size_t i = 0; allowed && i < terento_consumed_count; ++i) {
        if (!strcmp(terento_consumed_grants[i].operation_id, authorization->operation_id)
            && terento_consumed_grants[i].sequence == authorization->sequence) allowed = 0;
    }
    if (allowed) {
        strcpy(terento_consumed_grants[terento_consumed_count].operation_id, authorization->operation_id);
        terento_consumed_grants[terento_consumed_count++].sequence = authorization->sequence;
    }
    pthread_mutex_unlock(&terento_mutation_lock);
    return allowed;
}

static int terento_private_record_matches(int directory, const char *name, const char *expected) {
    int file = openat(directory, name, O_RDONLY | O_NOFOLLOW);
    if (file < 0) return 0;
    struct stat status;
    char bytes[160];
    size_t length = strlen(expected);
    int okay = fstat(file, &status) == 0 && S_ISREG(status.st_mode)
        && status.st_uid == getuid() && (status.st_mode & 077) == 0
        && status.st_size == (off_t)length && length < sizeof(bytes)
        && read(file, bytes, length) == (ssize_t)length && !memcmp(bytes, expected, length);
    close(file);
    return okay;
}

static int terento_persist_mutation_claim(const TerentoMTPMutationAuthorization *authorization) {
    if (!authorization->claim_path) return 0;
    size_t length = strnlen(authorization->claim_path, PATH_MAX);
    if (!length || length >= PATH_MAX || authorization->claim_path[0] != '/') return 0;
    char directory[PATH_MAX];
    memcpy(directory, authorization->claim_path, length + 1);
    char *leaf = strrchr(directory, '/');
    if (!leaf || leaf == directory) return 0;
    *leaf++ = 0;
    char expected[96];
    snprintf(expected, sizeof(expected), "%s-%u.claim", authorization->operation_id, authorization->sequence);
    if (strcmp(leaf, expected)) return 0;
    int dir = open(directory, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (dir < 0) return 0;
    struct stat status;
    if (fstat(dir, &status) || status.st_uid != getuid() || (status.st_mode & 077) != 0) {
        close(dir); return 0;
    }
    if (authorization->purpose == TERENTO_MUTATION_UPDATE_OLD) {
        char predecessor[96], predecessor_contents[112], verified[96];
        snprintf(predecessor, sizeof(predecessor), "%s-1.claim", authorization->operation_id);
        snprintf(predecessor_contents, sizeof(predecessor_contents), "%s|2|1", predecessor);
        snprintf(verified, sizeof(verified), "%s-verified-new", authorization->operation_id);
        if (!terento_private_record_matches(dir, predecessor, predecessor_contents)
            || !terento_private_record_matches(dir, verified, authorization->operation_id)) {
            close(dir); return 0;
        }
    }
    int file = openat(dir, leaf, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
    int okay = 0;
    if (file >= 0) {
        char contents[128];
        snprintf(contents, sizeof(contents), "%s|%u|%u", expected, authorization->purpose, authorization->mutation_kind);
        size_t bytes = strlen(contents);
        okay = write(file, contents, bytes) == (ssize_t)bytes && fsync(file) == 0;
        if (close(file) != 0) okay = 0;
        if (fsync(dir) != 0) okay = 0;
        /* Failed persistence leaves the claim consumed: never retry a mutation. */
    }
    close(dir);
    return okay;
}

/* The only mutation dispatcher. Tests inject the actual callback, not a parallel
 * imitation of these rules. All caller target checks precede this final gate. */
static int terento_dispatch_mutation(
    const TerentoMTPMutationAuthorization *authorization, TerentoMTPMutationRecord *record,
    const TerentoMutationSession *session, uint32_t kind, uint32_t storage_id,
    uint32_t parent_id, const char *filename, uint64_t size, uint32_t object_id,
    int content_verified, TerentoMutationCall call, void *context
) {
    if (!record) return TERENTO_MTP_MUTATION_REFUSED;
    memset(record, 0, sizeof(*record));
    record->native_result = TERENTO_MTP_MUTATION_REFUSED;
    if (!authorization || !session || !call) return TERENTO_MTP_MUTATION_REFUSED;
    record->sequence = authorization->sequence;
    record->purpose = authorization->purpose;
    record->mutation_kind = kind;
    record->session_id = session->session_id;
    size_t id_length = authorization->operation_id ? strnlen(authorization->operation_id, 65) : 0;
    if (authorization->version != 1 || id_length == 0 || id_length > 64
        || authorization->sequence == 0 || !session->device_verified || !session->session_id
        || !storage_id || !parent_id || storage_id != session->storage_id
        || authorization->expected_storage_id != storage_id
        || !authorization->expected_physical_identifier || !session->physical_identifier
        || !authorization->expected_physical_identifier[0]
        || strcmp(authorization->expected_physical_identifier, session->physical_identifier)
        || authorization->expected_physical_identifier_source != session->physical_identifier_source
        || (authorization->expected_physical_identifier_source != 1 && authorization->expected_physical_identifier_source != 2)
        || !authorization->expected_target_directory || !session->target_directory
        || strcmp(authorization->expected_target_directory, "/GARMIN")
        || strcmp(authorization->expected_target_directory, session->target_directory)
        || parent_id != session->parent_id || kind != authorization->mutation_kind
        || !filename || !authorization->expected_filename
        || strcmp(filename, authorization->expected_filename) || !size
        || size != authorization->expected_size) return TERENTO_MTP_MUTATION_REFUSED;
    for (size_t i = 0; i < id_length; ++i) {
        unsigned char c = (unsigned char)authorization->operation_id[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
            || (c >= '0' && c <= '9') || c == '-')) return TERENTO_MTP_MUTATION_REFUSED;
    }
    int purpose_allowed = kind == TERENTO_MUTATION_SEND
        ? (authorization->purpose == TERENTO_MUTATION_INSTALL || authorization->purpose == TERENTO_MUTATION_UPDATE_NEW)
        : (kind == TERENTO_MUTATION_DELETE && content_verified && object_id != 0
            && (authorization->purpose == TERENTO_MUTATION_UPDATE_OLD
                || authorization->purpose == TERENTO_MUTATION_REMOVE_MANAGED
                || authorization->purpose == TERENTO_MUTATION_REMOVE_EXTERNAL));
    /* Cleanup cannot establish creation provenance in these fresh-session APIs. */
    uint32_t required_sequence = authorization->purpose == TERENTO_MUTATION_UPDATE_OLD ? 2 : 1;
    if (!purpose_allowed || authorization->sequence != required_sequence
        || !terento_persist_mutation_claim(authorization) || !terento_claim_mutation(authorization)) return TERENTO_MTP_MUTATION_REFUSED;
    record->authorized = 1;
    record->attempted = 1;
    record->native_result = call(context, &record->resulting_object_id);
    record->completed = 1;
    return record->native_result;
}
#endif
