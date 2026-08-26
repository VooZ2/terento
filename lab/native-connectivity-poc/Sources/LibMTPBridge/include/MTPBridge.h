#ifndef TERENTO_MTP_BRIDGE_H
#define TERENTO_MTP_BRIDGE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint32_t storage_id;
    uint64_t max_capacity;
    uint64_t free_space_in_bytes;
    char *storage_description;
    char *volume_identifier;
} TerentoMTPStorage;

typedef struct {
    uint16_t vendor_id;
    uint16_t product_id;
    char *manufacturer;
    char *model;
    char *device_version;
    char *serial_number;
    uint8_t garmin_device_xml_status;
    size_t garmin_device_xml_size;
    unsigned char *garmin_device_xml;
    size_t storage_count;
    TerentoMTPStorage *storages;
} TerentoMTPDeviceSnapshot;

enum {
    TERENTO_GARMIN_DEVICE_XML_UNAVAILABLE = 0,
    TERENTO_GARMIN_DEVICE_XML_AVAILABLE = 1,
    TERENTO_GARMIN_DEVICE_XML_AMBIGUOUS = 2,
    TERENTO_GARMIN_DEVICE_XML_OVERSIZED = 3,
    TERENTO_GARMIN_DEVICE_XML_READ_FAILED = 4
};

typedef struct {
    uint32_t item_id;
    uint32_t parent_id;
    uint32_t storage_id;
    uint64_t size_bytes;
    uint8_t is_folder;
    char *path;
    char *filename;
} TerentoMTPFile;

typedef struct {
    size_t file_count;
    TerentoMTPFile *files;
} TerentoMTPFileInventory;

typedef struct {
    size_t byte_count;
    unsigned char *bytes;
} TerentoMTPByteBuffer;

/*
 * Per-operation production authorization prepared from the same live snapshot
 * Swift used for its reviewed map-capability decision. C compares only these
 * directly observable values with the device it opens itself.
 */
typedef struct {
    uint32_t version;
    uint16_t vendor_id;
    uint16_t product_id;
    const char *manufacturer;
    const char *model;
    const char *target_directory;
} TerentoMTPMapOperationProfile;

/* A real transfer callback. Returning non-zero cancels the transfer. */
typedef int (*TerentoMTPProgressCallback)(
    uint64_t sent,
    uint64_t total,
    const void *context
);

enum {
    TERENTO_MTP_MAP_TARGET_EXISTS = -20,
    TERENTO_MTP_MAP_REMOTE_FILE_MISSING = -21,
    TERENTO_MTP_MAP_OBJECT_ID_MISMATCH = -22,
    TERENTO_MTP_MAP_UNSUPPORTED_DEVICE = -23,
    TERENTO_MTP_MAP_IDENTITY_MISMATCH = -24
};

/* Read-only USB presence probe. Returns the number of connected Garmin USB devices. */
int terento_mtp_probe_garmin_presence(void);

/* Read-only operation: detect one Garmin MTP device and read its metadata. */
int terento_mtp_read_snapshot(
    TerentoMTPDeviceSnapshot *snapshot,
    char *error_message,
    size_t error_message_capacity
);

void terento_mtp_free_snapshot(TerentoMTPDeviceSnapshot *snapshot);

/* Read-only operation: enumerate device files and folders. */
int terento_mtp_read_file_inventory(
    TerentoMTPFileInventory *inventory,
    char *error_message,
    size_t error_message_capacity
);

void terento_mtp_free_file_inventory(TerentoMTPFileInventory *inventory);

/* Read-only operation: read a bounded prefix of one existing device file. */
int terento_mtp_read_file_prefix(
    uint32_t item_id,
    uint64_t offset,
    uint32_t max_length,
    TerentoMTPByteBuffer *buffer,
    char *error_message,
    size_t error_message_capacity
);

/* Read-only operation: read bounded prefixes for multiple existing files in one session. */
int terento_mtp_read_file_prefixes(
    const uint32_t *item_ids,
    size_t item_count,
    uint32_t max_length,
    TerentoMTPByteBuffer *buffers,
    char *error_message,
    size_t error_message_capacity
);

void terento_mtp_free_byte_buffer(TerentoMTPByteBuffer *buffer);

/* Read-only operation: validate one exact existing object and read it locally. */
int terento_mtp_read_existing_file_to_local(
    const TerentoMTPMapOperationProfile *profile,
    uint32_t expected_item_id,
    const char *expected_path,
    uint64_t expected_size_bytes,
    const char *local_path,
    uint32_t *resolved_item_id,
    uint64_t *size_bytes,
    char *error_message,
    size_t error_message_capacity
);

/*
 * Explicit Stage 3 developer-only write test. This is not map installation.
 * The implementation accepts only the fixed test payload name and the
 * validated Garmin fēnix 8 profile, refuses an existing target, reads the
 * object back, and deletes only the exact object returned by the write.
 */
int terento_mtp_write_test_file(
    const char *local_path,
    uint32_t *item_id,
    uint64_t *size_bytes,
    char *error_message,
    size_t error_message_capacity
);

int terento_mtp_read_test_file_to_local(
    uint32_t expected_item_id,
    const char *local_path,
    uint64_t *size_bytes,
    char *error_message,
    size_t error_message_capacity
);

int terento_mtp_delete_test_file(
    uint32_t expected_item_id,
    char *error_message,
    size_t error_message_capacity
);

/*
 * Production write path. The Swift layer validates the exact catalog package;
 * the native layer independently enforces the Terento-managed filename
 * grammar and the live device facts in the per-operation production profile.
 */
int terento_mtp_install_map_file(
    const TerentoMTPMapOperationProfile *profile,
    const char *local_path,
    const char *target_filename,
    uint32_t *item_id,
    uint64_t *size_bytes,
    TerentoMTPProgressCallback progress_callback,
    const void *progress_context,
    char *error_message,
    size_t error_message_capacity
);

/*
 * Read bounded deterministic samples from the exact managed target and
 * compare them directly with the validated local source. The full map is
 * never copied back to the Mac.
 */
int terento_mtp_verify_managed_map_samples(
    const TerentoMTPMapOperationProfile *profile,
    const char *local_path,
    const char *target_filename,
    uint32_t expected_item_id,
    uint64_t expected_size_bytes,
    const uint64_t *sample_offsets,
    size_t sample_count,
    uint32_t sample_length,
    uint64_t *sampled_bytes,
    uint32_t *matched_samples,
    TerentoMTPProgressCallback progress_callback,
    const void *progress_context,
    char *error_message,
    size_t error_message_capacity
);

/* Delete only the exact manifest-authorized managed target object. */
int terento_mtp_delete_managed_map(
    const TerentoMTPMapOperationProfile *profile,
    const char *target_filename,
    uint32_t expected_item_id,
    uint64_t expected_size_bytes,
    char *error_message,
    size_t error_message_capacity
);

/*
 * Explicit Stage 3 developer-only interruption test. This uses a separate
 * temporary object name and never accepts a map file. The physical mode
 * pauses at the requested percentage so the operator can disconnect the
 * watch before the transfer resumes.
 */
int terento_mtp_interrupt_test_file(
    const char *local_path,
    uint8_t interrupt_after_percent,
    uint8_t pause_for_physical_disconnect,
    uint32_t *item_id,
    uint64_t *size_bytes,
    uint8_t *transfer_was_cancelled,
    char *error_message,
    size_t error_message_capacity
);

int terento_mtp_inspect_interrupt_test_file(
    uint32_t *item_id,
    uint64_t *size_bytes,
    size_t *match_count,
    char *error_message,
    size_t error_message_capacity
);

int terento_mtp_delete_interrupt_test_file(
    uint32_t expected_item_id,
    char *error_message,
    size_t error_message_capacity
);

#ifdef __cplusplus
}
#endif

#endif
