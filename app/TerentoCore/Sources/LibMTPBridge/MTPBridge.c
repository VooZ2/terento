#include "MTPBridge.h"

#include <libusb.h>
#include <libmtp.h>
#include <ctype.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define GARMIN_VENDOR_ID 0x091e
#define TERENTO_WRITE_TEST_PRODUCT_ID 0x51b8
#define TERENTO_WRITE_TEST_FILENAME "terento-write-test.txt"
#define TERENTO_WRITE_TEST_MAX_BYTES (1024 * 1024)
#define TERENTO_INTERRUPT_TEST_FILENAME "terento-interrupt-test.bin"
#define TERENTO_INTERRUPT_TEST_MAX_BYTES (64 * 1024 * 1024)
#define MAX_SUPPORTED_STORAGES 64
#define MAX_SUPPORTED_FILES 16384
#define MAX_FILE_TREE_DEPTH 32
#define TERENTO_MAP_OPERATION_PROFILE_VERSION 1
#define TERENTO_PROFILE_TEXT_MAX_BYTES 255
#define TERENTO_GARMIN_DEVICE_XML_MAX_BYTES (2 * 1024 * 1024)

static int validate_map_operation_profile(
    const TerentoMTPMapOperationProfile *profile,
    char *error_message,
    size_t error_message_capacity
);

static int validate_live_map_operation_device(
    const TerentoMTPMapOperationProfile *profile,
    uint16_t vendor_id,
    uint16_t product_id,
    LIBMTP_mtpdevice_t *device,
    char *error_message,
    size_t error_message_capacity
);

static int map_live_validation_error(int validation_result) {
    return validation_result == -2 || validation_result == -3
        ? TERENTO_MTP_MAP_IDENTITY_MISMATCH
        : TERENTO_MTP_MAP_UNSUPPORTED_DEVICE;
}

static int device_error_is_present(LIBMTP_mtpdevice_t *device);

static int find_single_garmin_folder(
    LIBMTP_mtpdevice_t *device,
    uint32_t *storage_id,
    uint32_t *folder_id,
    char *error_message,
    size_t error_message_capacity
);

int terento_mtp_probe_garmin_presence(void) {
    libusb_context *context = NULL;
    if (libusb_init(&context) != 0) {
        return -1;
    }

    libusb_device **devices = NULL;
    ssize_t device_count = libusb_get_device_list(context, &devices);
    if (device_count < 0) {
        libusb_exit(context);
        return -1;
    }

    int garmin_count = 0;
    for (ssize_t index = 0; index < device_count; index += 1) {
        struct libusb_device_descriptor descriptor;
        if (libusb_get_device_descriptor(devices[index], &descriptor) != 0) {
            continue;
        }

        if (descriptor.idVendor == GARMIN_VENDOR_ID) {
            garmin_count += 1;
        }
    }

    libusb_free_device_list(devices, 1);
    libusb_exit(context);
    return garmin_count;
}

static void clear_snapshot(TerentoMTPDeviceSnapshot *snapshot) {
    if (snapshot == NULL) {
        return;
    }

    free(snapshot->manufacturer);
    free(snapshot->model);
    free(snapshot->device_version);
    free(snapshot->serial_number);
    free(snapshot->garmin_device_xml);

    if (snapshot->storages != NULL) {
        for (size_t index = 0; index < snapshot->storage_count; index += 1) {
            free(snapshot->storages[index].storage_description);
            free(snapshot->storages[index].volume_identifier);
        }
        free(snapshot->storages);
    }

    memset(snapshot, 0, sizeof(*snapshot));
}

void terento_mtp_free_snapshot(TerentoMTPDeviceSnapshot *snapshot) {
    clear_snapshot(snapshot);
}

static void clear_file_inventory(TerentoMTPFileInventory *inventory) {
    if (inventory == NULL) {
        return;
    }

    if (inventory->files != NULL) {
        for (size_t index = 0; index < inventory->file_count; index += 1) {
            free(inventory->files[index].path);
            free(inventory->files[index].filename);
        }
        free(inventory->files);
    }

    memset(inventory, 0, sizeof(*inventory));
}

void terento_mtp_free_file_inventory(TerentoMTPFileInventory *inventory) {
    clear_file_inventory(inventory);
}

void terento_mtp_free_byte_buffer(TerentoMTPByteBuffer *buffer) {
    if (buffer == NULL) {
        return;
    }

    free(buffer->bytes);
    memset(buffer, 0, sizeof(*buffer));
}

static void set_error(char *buffer, size_t capacity, const char *message) {
    if (buffer == NULL || capacity == 0) {
        return;
    }

    snprintf(buffer, capacity, "%s", message != NULL ? message : "Unknown MTP error");
}

static void set_device_error(
    char *buffer,
    size_t capacity,
    LIBMTP_mtpdevice_t *device,
    const char *fallback
) {
    if (device != NULL) {
        LIBMTP_error_t *error = LIBMTP_Get_Errorstack(device);
        if (error != NULL && error->error_text != NULL && error->error_text[0] != '\0') {
            set_error(buffer, capacity, error->error_text);
            return;
        }
    }

    set_error(buffer, capacity, fallback);
}

static int duplicate_text(char **destination, const char *source, const char *fallback) {
    if (destination == NULL) {
        return -1;
    }

    const char *value = (source != NULL && source[0] != '\0') ? source : fallback;
    *destination = strdup(value != NULL ? value : "Unknown");
    return *destination != NULL ? 0 : -1;
}

static int copy_libmtp_text(char **destination, char *value, const char *fallback) {
    int result = duplicate_text(destination, value, fallback);
    if (value != NULL) {
        LIBMTP_FreeMemory(value);
    }
    return result;
}

static int copy_storage(
    TerentoMTPStorage *destination,
    const LIBMTP_devicestorage_t *source,
    size_t index
) {
    if (destination == NULL || source == NULL) {
        return -1;
    }

    destination->storage_id = source->id;
    destination->max_capacity = source->MaxCapacity;
    destination->free_space_in_bytes = source->FreeSpaceInBytes;

    char fallback[64];
    snprintf(fallback, sizeof(fallback), "Storage %zu", index + 1);

    if (duplicate_text(
            &destination->storage_description,
            source->StorageDescription,
            fallback
        ) != 0) {
        return -1;
    }

    if (duplicate_text(
            &destination->volume_identifier,
            source->VolumeIdentifier,
            ""
        ) != 0) {
        free(destination->storage_description);
        destination->storage_description = NULL;
        return -1;
    }

    return 0;
}

static void read_garmin_device_xml(
    LIBMTP_mtpdevice_t *device,
    TerentoMTPDeviceSnapshot *snapshot
) {
    if (snapshot == NULL) {
        return;
    }
    snapshot->garmin_device_xml_status = TERENTO_GARMIN_DEVICE_XML_UNAVAILABLE;
    if (device == NULL || device->storage == NULL) {
        return;
    }

    uint32_t storage_id = 0;
    uint32_t garmin_folder_id = 0;
    size_t garmin_folder_count = 0;
    for (LIBMTP_devicestorage_t *storage = device->storage;
         storage != NULL;
         storage = storage->next) {
        LIBMTP_Clear_Errorstack(device);
        LIBMTP_file_t *root = LIBMTP_Get_Files_And_Folders(
            device,
            storage->id,
            LIBMTP_FILES_AND_FOLDERS_ROOT
        );
        if (root == NULL && device_error_is_present(device)) {
            snapshot->garmin_device_xml_status = TERENTO_GARMIN_DEVICE_XML_READ_FAILED;
            return;
        }
        for (LIBMTP_file_t *item = root; item != NULL; item = item->next) {
            if (item->filetype == LIBMTP_FILETYPE_FOLDER
                && item->filename != NULL
                && strcasecmp(item->filename, "GARMIN") == 0) {
                garmin_folder_count += 1;
                storage_id = storage->id;
                garmin_folder_id = item->item_id;
            }
        }
        if (root != NULL) {
            LIBMTP_destroy_file_t(root);
        }
    }

    if (garmin_folder_count != 1) {
        if (garmin_folder_count > 1) {
            snapshot->garmin_device_xml_status = TERENTO_GARMIN_DEVICE_XML_AMBIGUOUS;
        }
        return;
    }

    uint32_t xml_item_id = 0;
    uint64_t xml_size = 0;
    size_t xml_count = 0;
    LIBMTP_Clear_Errorstack(device);
    LIBMTP_file_t *children = LIBMTP_Get_Files_And_Folders(
        device,
        storage_id,
        garmin_folder_id
    );
    if (children == NULL && device_error_is_present(device)) {
        snapshot->garmin_device_xml_status = TERENTO_GARMIN_DEVICE_XML_READ_FAILED;
        return;
    }
    for (LIBMTP_file_t *item = children; item != NULL; item = item->next) {
        if (item->filetype != LIBMTP_FILETYPE_FOLDER
            && item->filename != NULL
            && strcasecmp(item->filename, "GarminDevice.xml") == 0) {
            xml_count += 1;
            xml_item_id = item->item_id;
            xml_size = item->filesize;
        }
    }
    if (children != NULL) {
        LIBMTP_destroy_file_t(children);
    }

    if (xml_count != 1) {
        if (xml_count > 1) {
            snapshot->garmin_device_xml_status = TERENTO_GARMIN_DEVICE_XML_AMBIGUOUS;
        }
        return;
    }
    if (xml_size == 0 || xml_size > TERENTO_GARMIN_DEVICE_XML_MAX_BYTES
        || xml_size > UINT32_MAX) {
        snapshot->garmin_device_xml_status = TERENTO_GARMIN_DEVICE_XML_OVERSIZED;
        return;
    }

    unsigned char *raw_bytes = NULL;
    unsigned int actual_length = 0;
    LIBMTP_Clear_Errorstack(device);
    int read_result = LIBMTP_GetPartialObject(
        device,
        xml_item_id,
        0,
        (uint32_t)xml_size,
        &raw_bytes,
        &actual_length
    );
    if (read_result != 0 || raw_bytes == NULL || actual_length != xml_size) {
        if (raw_bytes != NULL) {
            LIBMTP_FreeMemory(raw_bytes);
        }
        snapshot->garmin_device_xml_status = TERENTO_GARMIN_DEVICE_XML_READ_FAILED;
        return;
    }

    snapshot->garmin_device_xml = malloc(actual_length);
    if (snapshot->garmin_device_xml == NULL) {
        LIBMTP_FreeMemory(raw_bytes);
        snapshot->garmin_device_xml_status = TERENTO_GARMIN_DEVICE_XML_READ_FAILED;
        return;
    }
    memcpy(snapshot->garmin_device_xml, raw_bytes, actual_length);
    snapshot->garmin_device_xml_size = actual_length;
    snapshot->garmin_device_xml_status = TERENTO_GARMIN_DEVICE_XML_AVAILABLE;
    LIBMTP_FreeMemory(raw_bytes);
}

static LIBMTP_mtpdevice_t *open_single_garmin_device(
    uint16_t *vendor_id,
    uint16_t *product_id,
    char *error_message,
    size_t error_message_capacity,
    int uncached
) {
    LIBMTP_Init();
    LIBMTP_Set_Debug(0);

    LIBMTP_raw_device_t *raw_devices = NULL;
    int raw_device_count = 0;
    LIBMTP_error_number_t detect_result = LIBMTP_Detect_Raw_Devices(
        &raw_devices,
        &raw_device_count
    );

    if (detect_result != LIBMTP_ERROR_NONE || raw_device_count <= 0 || raw_devices == NULL) {
        free(raw_devices);
        set_error(error_message, error_message_capacity, "No MTP device connected");
        return NULL;
    }

    int garmin_count = 0;
    int selected_index = -1;
    for (int index = 0; index < raw_device_count; index += 1) {
        if (raw_devices[index].device_entry.vendor_id == GARMIN_VENDOR_ID) {
            garmin_count += 1;
            selected_index = index;
        }
    }

    if (garmin_count == 0) {
        free(raw_devices);
        set_error(error_message, error_message_capacity, "No Garmin MTP device detected");
        return NULL;
    }

    if (garmin_count != 1 || selected_index < 0) {
        free(raw_devices);
        set_error(error_message, error_message_capacity, "More than one Garmin MTP device detected");
        return NULL;
    }

    if (vendor_id != NULL) {
        *vendor_id = raw_devices[selected_index].device_entry.vendor_id;
    }
    if (product_id != NULL) {
        *product_id = raw_devices[selected_index].device_entry.product_id;
    }

    /*
     * libmtp's cached device mode is suitable for metadata, but it cannot be
     * used with file-tree operations such as Get_Files_And_Folders. Garmin
     * exposes the map files through those operations, so enumerate and read
     * files through an explicitly uncached session.
     */
    LIBMTP_mtpdevice_t *device = uncached
        ? LIBMTP_Open_Raw_Device_Uncached(&raw_devices[selected_index])
        : LIBMTP_Open_Raw_Device(&raw_devices[selected_index]);
    free(raw_devices);

    if (device == NULL) {
        set_error(error_message, error_message_capacity, "Garmin MTP device could not be opened");
    }

    return device;
}

static char *join_path(const char *parent_path, const char *filename) {
    if (filename == NULL || filename[0] == '\0') {
        return NULL;
    }

    const char *parent = parent_path != NULL ? parent_path : "";
    size_t parent_length = strlen(parent);
    size_t filename_length = strlen(filename);
    if (filename_length > SIZE_MAX - 2
        || parent_length > SIZE_MAX - filename_length - 2) {
        return NULL;
    }

    size_t total_length = parent_length + filename_length + 2;
    char *path = malloc(total_length);
    if (path == NULL) {
        return NULL;
    }

    if (parent_length == 0) {
        snprintf(path, total_length, "/%s", filename);
    } else {
        snprintf(path, total_length, "%s/%s", parent, filename);
    }

    return path;
}

static int append_file(
    TerentoMTPFileInventory *inventory,
    const LIBMTP_file_t *source,
    const char *path,
    char *error_message,
    size_t error_message_capacity
) {
    if (inventory == NULL || source == NULL || path == NULL) {
        set_error(error_message, error_message_capacity, "Device file metadata is unavailable");
        return -1;
    }

    if (inventory->file_count >= MAX_SUPPORTED_FILES
        || inventory->file_count == SIZE_MAX) {
        set_error(error_message, error_message_capacity, "Device file inventory is unexpectedly large");
        return -1;
    }

    size_t new_count = inventory->file_count + 1;
    if (new_count > SIZE_MAX / sizeof(*inventory->files)) {
        set_error(error_message, error_message_capacity, "Device file inventory is too large to allocate");
        return -1;
    }
    TerentoMTPFile *files = realloc(
        inventory->files,
        new_count * sizeof(*inventory->files)
    );
    if (files == NULL) {
        set_error(error_message, error_message_capacity, "Could not allocate device file inventory");
        return -1;
    }

    inventory->files = files;
    TerentoMTPFile *destination = &inventory->files[inventory->file_count];
    memset(destination, 0, sizeof(*destination));
    destination->item_id = source->item_id;
    destination->parent_id = source->parent_id;
    destination->storage_id = source->storage_id;
    destination->size_bytes = source->filesize;
    destination->is_folder = source->filetype == LIBMTP_FILETYPE_FOLDER ? 1 : 0;
    destination->path = strdup(path);
    destination->filename = strdup(source->filename != NULL ? source->filename : "Unknown");

    if (destination->path == NULL || destination->filename == NULL) {
        free(destination->path);
        free(destination->filename);
        memset(destination, 0, sizeof(*destination));
        set_error(error_message, error_message_capacity, "Could not copy device file metadata");
        return -1;
    }

    inventory->file_count = new_count;
    return 0;
}

static int walk_file_tree(
    LIBMTP_mtpdevice_t *device,
    uint32_t storage_id,
    uint32_t parent_id,
    const char *parent_path,
    size_t depth,
    TerentoMTPFileInventory *inventory,
    char *error_message,
    size_t error_message_capacity
) {
    if (depth > MAX_FILE_TREE_DEPTH) {
        set_error(error_message, error_message_capacity, "Device file tree is unexpectedly deep");
        return -1;
    }

    LIBMTP_Clear_Errorstack(device);
    LIBMTP_file_t *children = LIBMTP_Get_Files_And_Folders(device, storage_id, parent_id);
    if (children == NULL) {
        LIBMTP_error_t *error = LIBMTP_Get_Errorstack(device);
        if (error != NULL && error->error_text != NULL && error->error_text[0] != '\0') {
            set_error(error_message, error_message_capacity, error->error_text);
            return -1;
        }
        return 0;
    }

    int result = 0;
    for (LIBMTP_file_t *child = children; child != NULL; child = child->next) {
        char *path = join_path(parent_path, child->filename);
        if (path == NULL) {
            set_error(error_message, error_message_capacity, "Could not construct device file path");
            result = -1;
            break;
        }

        result = append_file(
            inventory,
            child,
            path,
            error_message,
            error_message_capacity
        );

        if (result == 0 && child->filetype == LIBMTP_FILETYPE_FOLDER) {
            result = walk_file_tree(
                device,
                storage_id,
                child->item_id,
                path,
                depth + 1,
                inventory,
                error_message,
                error_message_capacity
            );
        }

        free(path);
        if (result != 0) {
            break;
        }
    }

    LIBMTP_destroy_file_t(children);
    return result;
}

int terento_mtp_read_file_inventory(
    TerentoMTPFileInventory *inventory,
    char *error_message,
    size_t error_message_capacity
) {
    if (inventory == NULL) {
        set_error(error_message, error_message_capacity, "File inventory output is unavailable");
        return -1;
    }

    clear_file_inventory(inventory);
    set_error(error_message, error_message_capacity, "");

    LIBMTP_mtpdevice_t *device = open_single_garmin_device(
        NULL,
        NULL,
        error_message,
        error_message_capacity,
        1
    );
    if (device == NULL) {
        return -2;
    }

    int result = 0;
    LIBMTP_Clear_Errorstack(device);
    if (LIBMTP_Get_Storage(device, LIBMTP_STORAGE_SORTBY_NOTSORTED) != 0) {
        set_device_error(
            error_message,
            error_message_capacity,
            device,
            "Could not read storage information"
        );
        result = -3;
        goto cleanup;
    }

    for (LIBMTP_devicestorage_t *storage = device->storage;
         storage != NULL;
         storage = storage->next) {
        result = walk_file_tree(
            device,
            storage->id,
            LIBMTP_FILES_AND_FOLDERS_ROOT,
            "",
            0,
            inventory,
            error_message,
            error_message_capacity
        );
        if (result != 0) {
            break;
        }
    }

cleanup:
    LIBMTP_Release_Device(device);
    if (result != 0) {
        clear_file_inventory(inventory);
    }
    return result;
}

int terento_mtp_read_file_prefix(
    uint32_t item_id,
    uint64_t offset,
    uint32_t max_length,
    TerentoMTPByteBuffer *buffer,
    char *error_message,
    size_t error_message_capacity
) {
    if (buffer == NULL || max_length == 0) {
        set_error(error_message, error_message_capacity, "File prefix output is unavailable");
        return -1;
    }

    terento_mtp_free_byte_buffer(buffer);
    set_error(error_message, error_message_capacity, "");

    LIBMTP_mtpdevice_t *device = open_single_garmin_device(
        NULL,
        NULL,
        error_message,
        error_message_capacity,
        1
    );
    if (device == NULL) {
        return -2;
    }

    int result = 0;
    unsigned char *raw_bytes = NULL;
    unsigned int actual_length = 0;
    LIBMTP_Clear_Errorstack(device);
    result = LIBMTP_GetPartialObject(
        device,
        item_id,
        offset,
        max_length,
        &raw_bytes,
        &actual_length
    );

    if (result != 0) {
        set_device_error(
            error_message,
            error_message_capacity,
            device,
            "Could not read the device file prefix"
        );
        if (raw_bytes != NULL) {
            LIBMTP_FreeMemory(raw_bytes);
        }
        LIBMTP_Release_Device(device);
        return -3;
    }

    if (actual_length > 0) {
        buffer->bytes = malloc(actual_length);
        if (buffer->bytes == NULL) {
            LIBMTP_FreeMemory(raw_bytes);
            LIBMTP_Release_Device(device);
            set_error(error_message, error_message_capacity, "Could not allocate the device file prefix");
            return -4;
        }
        memcpy(buffer->bytes, raw_bytes, actual_length);
        buffer->byte_count = actual_length;
    }

    if (raw_bytes != NULL) {
        LIBMTP_FreeMemory(raw_bytes);
    }
    LIBMTP_Release_Device(device);
    return 0;
}

int terento_mtp_read_file_prefixes(
    const uint32_t *item_ids,
    size_t item_count,
    uint32_t max_length,
    TerentoMTPByteBuffer *buffers,
    char *error_message,
    size_t error_message_capacity
) {
    if ((item_count > 0 && (item_ids == NULL || buffers == NULL)) || max_length == 0) {
        set_error(error_message, error_message_capacity, "File prefix output is unavailable");
        return -1;
    }

    for (size_t index = 0; index < item_count; index += 1) {
        terento_mtp_free_byte_buffer(&buffers[index]);
    }
    set_error(error_message, error_message_capacity, "");

    if (item_count == 0) {
        return 0;
    }

    LIBMTP_mtpdevice_t *device = open_single_garmin_device(
        NULL,
        NULL,
        error_message,
        error_message_capacity,
        1
    );
    if (device == NULL) {
        return -2;
    }

    int result = 0;
    for (size_t index = 0; index < item_count; index += 1) {
        unsigned char *raw_bytes = NULL;
        unsigned int actual_length = 0;
        LIBMTP_Clear_Errorstack(device);
        int read_result = LIBMTP_GetPartialObject(
            device,
            item_ids[index],
            0,
            max_length,
            &raw_bytes,
            &actual_length
        );

        if (read_result != 0) {
            set_device_error(
                error_message,
                error_message_capacity,
                device,
                "Could not read the device file prefix"
            );
            if (raw_bytes != NULL) {
                LIBMTP_FreeMemory(raw_bytes);
            }
            result = -3;
            break;
        }

        if (actual_length > 0) {
            buffers[index].bytes = malloc(actual_length);
            if (buffers[index].bytes == NULL) {
                if (raw_bytes != NULL) {
                    LIBMTP_FreeMemory(raw_bytes);
                }
                set_error(error_message, error_message_capacity, "Could not allocate the device file prefix");
                result = -4;
                break;
            }
            memcpy(buffers[index].bytes, raw_bytes, actual_length);
            buffers[index].byte_count = actual_length;
        }

        if (raw_bytes != NULL) {
            LIBMTP_FreeMemory(raw_bytes);
        }
    }

    LIBMTP_Release_Device(device);
    if (result != 0) {
        for (size_t index = 0; index < item_count; index += 1) {
            terento_mtp_free_byte_buffer(&buffers[index]);
        }
    }
    return result;
}

static int find_existing_file_by_stable_identity(
    LIBMTP_mtpdevice_t *device,
    const char *expected_path,
    uint64_t expected_size_bytes,
    uint32_t *item_id,
    uint64_t *size_bytes,
    size_t *match_count,
    char *error_message,
    size_t error_message_capacity
) {
    if (device == NULL || expected_path == NULL || expected_size_bytes == 0
        || item_id == NULL || size_bytes == NULL || match_count == NULL) {
        set_error(error_message, error_message_capacity, "The exact map object identity is unavailable");
        return -1;
    }

    *item_id = 0;
    *size_bytes = 0;
    *match_count = 0;

    LIBMTP_Clear_Errorstack(device);
    if (LIBMTP_Get_Storage(device, LIBMTP_STORAGE_SORTBY_NOTSORTED) != 0) {
        set_device_error(
            error_message,
            error_message_capacity,
            device,
            "Could not read Garmin storage"
        );
        return -2;
    }

    TerentoMTPFileInventory inventory = {0};
    int result = 0;
    for (LIBMTP_devicestorage_t *storage = device->storage;
         storage != NULL;
         storage = storage->next) {
        result = walk_file_tree(
            device,
            storage->id,
            LIBMTP_FILES_AND_FOLDERS_ROOT,
            "",
            0,
            &inventory,
            error_message,
            error_message_capacity
        );
        if (result != 0) {
            break;
        }
    }

    if (result == 0) {
        for (size_t index = 0; index < inventory.file_count; index += 1) {
            const TerentoMTPFile *file = &inventory.files[index];
            if (file->is_folder != 0
                || file->path == NULL
                || strcmp(file->path, expected_path) != 0
                || file->size_bytes != expected_size_bytes) {
                continue;
            }

            *match_count += 1;
            *item_id = file->item_id;
            *size_bytes = file->size_bytes;
        }
    }

    clear_file_inventory(&inventory);
    if (result != 0) {
        return result;
    }
    if (*match_count == 0) {
        set_error(error_message, error_message_capacity, "The exact managed map object was not found on the Garmin watch");
        return -3;
    }
    if (*match_count != 1) {
        set_error(error_message, error_message_capacity, "The exact managed map object was not unique on the Garmin watch");
        return -4;
    }

    return 0;
}

int terento_mtp_read_existing_file_to_local(
    const TerentoMTPMapOperationProfile *profile,
    uint32_t expected_item_id,
    const char *expected_path,
    uint64_t expected_size_bytes,
    const char *local_path,
    uint32_t *resolved_item_id,
    uint64_t *size_bytes,
    TerentoMTPProgressCallback progress_callback,
    const void *progress_context,
    char *error_message,
    size_t error_message_capacity
) {
    if (validate_map_operation_profile(
            profile,
            error_message,
            error_message_capacity
        ) != 0) {
        return TERENTO_MTP_MAP_UNSUPPORTED_DEVICE;
    }
    if (expected_item_id == 0 || expected_path == NULL || expected_size_bytes == 0
        || local_path == NULL || resolved_item_id == NULL || size_bytes == NULL) {
        set_error(error_message, error_message_capacity, "The read-only map backup request is invalid");
        return -1;
    }

    *resolved_item_id = 0;
    *size_bytes = 0;
    set_error(error_message, error_message_capacity, "");

    struct stat destination_stat;
    if (stat(local_path, &destination_stat) == 0) {
        set_error(error_message, error_message_capacity, "The local backup destination already exists");
        return -2;
    }
    if (errno != ENOENT) {
        set_error(error_message, error_message_capacity, "The local backup destination is not available");
        return -3;
    }

    uint16_t vendor_id = 0;
    uint16_t product_id = 0;
    LIBMTP_mtpdevice_t *device = open_single_garmin_device(
        &vendor_id,
        &product_id,
        error_message,
        error_message_capacity,
        1
    );
    if (device == NULL) {
        return -4;
    }

    int result = validate_live_map_operation_device(
        profile,
        vendor_id,
        product_id,
        device,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        result = map_live_validation_error(result);
        goto cleanup;
    }

    uint32_t storage_id = 0;
    uint32_t folder_id = 0;
    result = find_single_garmin_folder(
        device,
        &storage_id,
        &folder_id,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        goto cleanup;
    }

    uint32_t live_item_id = 0;
    uint64_t remote_size = 0;
    size_t match_count = 0;
    result = find_existing_file_by_stable_identity(
        device,
        expected_path,
        expected_size_bytes,
        &live_item_id,
        &remote_size,
        &match_count,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        goto cleanup;
    }

    LIBMTP_Clear_Errorstack(device);
    if (LIBMTP_Get_File_To_File(
            device,
            live_item_id,
            local_path,
            progress_callback,
            (void *)progress_context
        ) != 0) {
        set_device_error(
            error_message,
            error_message_capacity,
            device,
            "The managed map could not be read from the Garmin watch"
        );
        result = -5;
        goto cleanup;
    }

    if (stat(local_path, &destination_stat) != 0
        || !S_ISREG(destination_stat.st_mode)
        || (uint64_t)destination_stat.st_size != remote_size) {
        unlink(local_path);
        set_error(error_message, error_message_capacity, "The local map backup size did not match the device object");
        result = -6;
        goto cleanup;
    }

    *resolved_item_id = live_item_id;
    *size_bytes = remote_size;
    result = 0;

cleanup:
    LIBMTP_Release_Device(device);
    return result;
}

static int device_error_is_present(LIBMTP_mtpdevice_t *device) {
    LIBMTP_error_t *error = device != NULL ? LIBMTP_Get_Errorstack(device) : NULL;
    return error != NULL && error->error_text != NULL && error->error_text[0] != '\0';
}

static void set_write_test_device_error(
    char *buffer,
    size_t capacity,
    LIBMTP_mtpdevice_t *device,
    const char *fallback
) {
    LIBMTP_error_t *error = device != NULL ? LIBMTP_Get_Errorstack(device) : NULL;
    const char *technical = error != NULL ? error->error_text : NULL;

    if (technical != NULL
        && (strstr(technical, "send_file_object_info") != NULL
            || strstr(technical, "PTP Layer error 2002") != NULL)) {
        char message[768];
        snprintf(
            message,
            sizeof(message),
            "The watch rejected the test file before transfer. No existing file was overwritten. "
            "Disconnect and reconnect the watch, close other Garmin or file-transfer apps, and try again. "
            "Technical detail: %s",
            technical
        );
        set_error(buffer, capacity, message);
        return;
    }

    set_device_error(buffer, capacity, device, fallback);
}

static int find_single_garmin_folder(
    LIBMTP_mtpdevice_t *device,
    uint32_t *storage_id,
    uint32_t *folder_id,
    char *error_message,
    size_t error_message_capacity
) {
    if (device == NULL || storage_id == NULL || folder_id == NULL) {
        set_error(error_message, error_message_capacity, "Garmin storage target is unavailable");
        return -1;
    }

    LIBMTP_Clear_Errorstack(device);
    if (LIBMTP_Get_Storage(device, LIBMTP_STORAGE_SORTBY_NOTSORTED) != 0) {
        set_device_error(
            error_message,
            error_message_capacity,
            device,
            "Could not read Garmin storage"
        );
        return -2;
    }

    size_t matches = 0;
    uint32_t matched_storage_id = 0;
    uint32_t matched_folder_id = 0;

    for (LIBMTP_devicestorage_t *storage = device->storage;
         storage != NULL;
         storage = storage->next) {
        LIBMTP_Clear_Errorstack(device);
        LIBMTP_file_t *children = LIBMTP_Get_Files_And_Folders(
            device,
            storage->id,
            LIBMTP_FILES_AND_FOLDERS_ROOT
        );

        if (children == NULL) {
            if (device_error_is_present(device)) {
                set_device_error(
                    error_message,
                    error_message_capacity,
                    device,
                    "Could not inspect Garmin storage"
                );
                return -3;
            }
            continue;
        }

        for (LIBMTP_file_t *child = children; child != NULL; child = child->next) {
            if (child->filetype != LIBMTP_FILETYPE_FOLDER
                || child->filename == NULL
                || strcasecmp(child->filename, "GARMIN") != 0) {
                continue;
            }

            matches += 1;
            matched_storage_id = storage->id;
            matched_folder_id = child->item_id;
        }

        LIBMTP_destroy_file_t(children);
    }

    if (matches == 0) {
        set_error(error_message, error_message_capacity, "The validated Garmin storage has no /GARMIN folder");
        return -4;
    }

    if (matches != 1) {
        set_error(error_message, error_message_capacity, "More than one /GARMIN folder was detected");
        return -5;
    }

    *storage_id = matched_storage_id;
    *folder_id = matched_folder_id;
    return 0;
}

static int find_write_test_file(
    LIBMTP_mtpdevice_t *device,
    uint32_t storage_id,
    uint32_t folder_id,
    uint32_t *item_id,
    uint64_t *size_bytes,
    size_t *match_count,
    char *error_message,
    size_t error_message_capacity
) {
    if (device == NULL || item_id == NULL || size_bytes == NULL || match_count == NULL) {
        set_error(error_message, error_message_capacity, "Write-test object result is unavailable");
        return -1;
    }

    *item_id = 0;
    *size_bytes = 0;
    *match_count = 0;

    LIBMTP_Clear_Errorstack(device);
    LIBMTP_file_t *children = LIBMTP_Get_Files_And_Folders(device, storage_id, folder_id);
    if (children == NULL) {
        if (device_error_is_present(device)) {
            set_device_error(
                error_message,
                error_message_capacity,
                device,
                "Could not inspect the /GARMIN folder"
            );
            return -2;
        }
        return 0;
    }

    for (LIBMTP_file_t *child = children; child != NULL; child = child->next) {
        if (child->filename == NULL
            || strcmp(child->filename, TERENTO_WRITE_TEST_FILENAME) != 0) {
            continue;
        }

        if (child->filetype == LIBMTP_FILETYPE_FOLDER) {
            set_error(
                error_message,
                error_message_capacity,
                "The Write Test target name is already used by a folder"
            );
            LIBMTP_destroy_file_t(children);
            return -3;
        }

        *match_count += 1;
        *item_id = child->item_id;
        *size_bytes = child->filesize;
    }

    LIBMTP_destroy_file_t(children);
    return 0;
}

static int find_interrupt_test_file(
    LIBMTP_mtpdevice_t *device,
    uint32_t storage_id,
    uint32_t folder_id,
    uint32_t *item_id,
    uint64_t *size_bytes,
    size_t *match_count,
    char *error_message,
    size_t error_message_capacity
) {
    if (device == NULL || item_id == NULL || size_bytes == NULL || match_count == NULL) {
        set_error(error_message, error_message_capacity, "Interruption-test object result is unavailable");
        return -1;
    }

    *item_id = 0;
    *size_bytes = 0;
    *match_count = 0;

    LIBMTP_Clear_Errorstack(device);
    LIBMTP_file_t *children = LIBMTP_Get_Files_And_Folders(device, storage_id, folder_id);
    if (children == NULL) {
        if (device_error_is_present(device)) {
            set_device_error(
                error_message,
                error_message_capacity,
                device,
                "Could not inspect the /GARMIN folder for the interruption test"
            );
            return -2;
        }
        return 0;
    }

    for (LIBMTP_file_t *child = children; child != NULL; child = child->next) {
        if (child->filename == NULL
            || strcmp(child->filename, TERENTO_INTERRUPT_TEST_FILENAME) != 0) {
            continue;
        }

        if (child->filetype == LIBMTP_FILETYPE_FOLDER) {
            set_error(
                error_message,
                error_message_capacity,
                "The interruption-test target name is already used by a folder"
            );
            LIBMTP_destroy_file_t(children);
            return -3;
        }

        *match_count += 1;
        *item_id = child->item_id;
        *size_bytes = child->filesize;
    }

    LIBMTP_destroy_file_t(children);
    return 0;
}

static int validate_write_test_device(
    uint16_t vendor_id,
    uint16_t product_id,
    char *error_message,
    size_t error_message_capacity
) {
    if (vendor_id != GARMIN_VENDOR_ID || product_id != TERENTO_WRITE_TEST_PRODUCT_ID) {
        set_error(
            error_message,
            error_message_capacity,
            "Write Test is currently enabled only for the validated Garmin fēnix 8 device"
        );
        return -1;
    }

    return 0;
}

static int bounded_profile_text(const char *value) {
    return value != NULL
        && value[0] != '\0'
        && strnlen(value, TERENTO_PROFILE_TEXT_MAX_BYTES + 1)
            <= TERENTO_PROFILE_TEXT_MAX_BYTES;
}

static int trimmed_text_equal(
    const char *left,
    const char *right,
    int case_insensitive
) {
    if (left == NULL || right == NULL) {
        return 0;
    }

    while (*left != '\0' && isspace((unsigned char)*left)) {
        left += 1;
    }
    while (*right != '\0' && isspace((unsigned char)*right)) {
        right += 1;
    }

    const char *left_end = left + strlen(left);
    const char *right_end = right + strlen(right);
    while (left_end > left && isspace((unsigned char)left_end[-1])) {
        left_end -= 1;
    }
    while (right_end > right && isspace((unsigned char)right_end[-1])) {
        right_end -= 1;
    }

    size_t left_length = (size_t)(left_end - left);
    size_t right_length = (size_t)(right_end - right);
    if (left_length != right_length) {
        return 0;
    }

    for (size_t index = 0; index < left_length; index += 1) {
        unsigned char left_character = (unsigned char)left[index];
        unsigned char right_character = (unsigned char)right[index];
        if (case_insensitive) {
            left_character = (unsigned char)tolower(left_character);
            right_character = (unsigned char)tolower(right_character);
        }
        if (left_character != right_character) {
            return 0;
        }
    }
    return 1;
}

static int validate_map_operation_profile(
    const TerentoMTPMapOperationProfile *profile,
    char *error_message,
    size_t error_message_capacity
) {
    if (profile == NULL
        || profile->version != TERENTO_MAP_OPERATION_PROFILE_VERSION
        || profile->vendor_id != GARMIN_VENDOR_ID
        || profile->product_id == 0
        || !bounded_profile_text(profile->manufacturer)
        || !bounded_profile_text(profile->model)
        || profile->target_directory == NULL
        || strcmp(profile->target_directory, "/GARMIN") != 0) {
        set_error(
            error_message,
            error_message_capacity,
            "The map operation profile is invalid or incomplete"
        );
        return -1;
    }
    return 0;
}

static int validate_live_map_operation_device(
    const TerentoMTPMapOperationProfile *profile,
    uint16_t vendor_id,
    uint16_t product_id,
    LIBMTP_mtpdevice_t *device,
    char *error_message,
    size_t error_message_capacity
) {
    if (validate_map_operation_profile(
            profile,
            error_message,
            error_message_capacity
        ) != 0) {
        return -1;
    }
    if (device == NULL
        || vendor_id != profile->vendor_id
        || product_id != profile->product_id) {
        set_error(
            error_message,
            error_message_capacity,
            "The connected Garmin USB identity does not match the authorized map operation"
        );
        return -2;
    }

    LIBMTP_Clear_Errorstack(device);
    char *manufacturer = LIBMTP_Get_Manufacturername(device);
    LIBMTP_Clear_Errorstack(device);
    char *model = LIBMTP_Get_Modelname(device);
    int matches = manufacturer != NULL
        && model != NULL
        && trimmed_text_equal(manufacturer, profile->manufacturer, 1)
        && trimmed_text_equal(model, profile->model, 1);
    if (manufacturer != NULL) {
        LIBMTP_FreeMemory(manufacturer);
    }
    if (model != NULL) {
        LIBMTP_FreeMemory(model);
    }

    if (!matches) {
        set_error(
            error_message,
            error_message_capacity,
            "The connected Garmin MTP identity does not match the authorized map operation"
        );
        return -3;
    }
    return 0;
}

static int validate_stage42_target(
    const char *target_filename,
    char *error_message,
    size_t error_message_capacity
) {
    /* The Swift layer validates the exact catalog package. The native boundary
       independently accepts only the safe Terento-managed filename grammar. */
    if (target_filename == NULL) {
        set_error(
            error_message,
            error_message_capacity,
            "The managed map filename is unavailable"
        );
        return -1;
    }

    size_t length = strlen(target_filename);
    const char *prefix = "terento_";
    const char *suffix = ".img";
    size_t prefix_length = strlen(prefix);
    size_t suffix_length = strlen(suffix);
    if (length <= prefix_length + suffix_length
        || length > 255
        || strncmp(target_filename, prefix, prefix_length) != 0
        || strcmp(target_filename + length - suffix_length, suffix) != 0) {
        set_error(
            error_message,
            error_message_capacity,
            "The managed map filename is not a valid Terento target"
        );
        return -1;
    }

    for (size_t index = prefix_length; index < length - suffix_length; index += 1) {
        unsigned char character = (unsigned char)target_filename[index];
        if (!(islower(character) || isdigit(character) || character == '_')) {
            set_error(
                error_message,
                error_message_capacity,
                "The managed map filename contains unsafe characters"
            );
            return -1;
        }
    }

    return 0;
}

static int validate_external_map_target(
    const char *target_filename,
    char *error_message,
    size_t error_message_capacity
) {
    if (target_filename == NULL) {
        set_error(error_message, error_message_capacity, "The external map filename is unavailable");
        return -1;
    }

    size_t length = strlen(target_filename);
    if (length <= 4 || length > 255
        || strcasecmp(target_filename + length - 4, ".img") != 0) {
        set_error(
            error_message,
            error_message_capacity,
            "The external map filename is not a valid IMG target"
        );
        return -1;
    }

    for (size_t index = 0; index < length; index += 1) {
        unsigned char character = (unsigned char)target_filename[index];
        if (!(isalnum(character) || character == '_' || character == '-'
              || character == '.')) {
            set_error(
                error_message,
                error_message_capacity,
                "The external map filename contains unsafe characters"
            );
            return -1;
        }
    }

    if (strstr(target_filename, "..") != NULL) {
        set_error(
            error_message,
            error_message_capacity,
            "The external map filename contains an unsafe path sequence"
        );
        return -1;
    }

    const char *protected_names[] = {
        "gmapbmap.img",
        "gmaptz.img",
        "gmappmap.img",
        "gmapprom.img",
        "gmapdem.img",
        "gmap3d.img",
        "gmaprgn.img"
    };
    for (size_t index = 0; index < sizeof(protected_names) / sizeof(protected_names[0]); index += 1) {
        if (strcasecmp(target_filename, protected_names[index]) == 0) {
            set_error(
                error_message,
                error_message_capacity,
                "The external map target is a protected Garmin file"
            );
            return -1;
        }
    }

    if ((target_filename[0] == 'd' || target_filename[0] == 'D')
        && strcasecmp(target_filename + length - 4, ".img") == 0) {
        set_error(
            error_message,
            error_message_capacity,
            "The external map target is a protected Garmin file"
        );
        return -1;
    }

    return 0;
}

static int validate_stage42_source(
    const char *local_path,
    struct stat *file_stat,
    char *error_message,
    size_t error_message_capacity
) {
    if (local_path == NULL || file_stat == NULL) {
        set_error(error_message, error_message_capacity, "The validated map source is unavailable");
        return -1;
    }

    if (stat(local_path, file_stat) != 0) {
        set_error(error_message, error_message_capacity, "The validated map source could not be read");
        return -2;
    }

    if (!S_ISREG(file_stat->st_mode) || file_stat->st_size <= 0) {
        set_error(error_message, error_message_capacity, "The validated map source must be a non-empty file");
        return -3;
    }

    return 0;
}

static int find_stage42_map_file(
    LIBMTP_mtpdevice_t *device,
    uint32_t storage_id,
    uint32_t folder_id,
    const char *target_filename,
    uint32_t *item_id,
    uint64_t *size_bytes,
    size_t *match_count,
    char *error_message,
    size_t error_message_capacity
) {
    if (device == NULL || target_filename == NULL || item_id == NULL
        || size_bytes == NULL || match_count == NULL) {
        set_error(error_message, error_message_capacity, "The map target result is unavailable");
        return -1;
    }

    *item_id = 0;
    *size_bytes = 0;
    *match_count = 0;

    LIBMTP_Clear_Errorstack(device);
    LIBMTP_file_t *children = LIBMTP_Get_Files_And_Folders(
        device,
        storage_id,
        folder_id
    );
    if (children == NULL) {
        if (device_error_is_present(device)) {
            set_device_error(
                error_message,
                error_message_capacity,
                device,
                "Could not inspect the /GARMIN folder"
            );
            return -2;
        }
        return 0;
    }

    for (LIBMTP_file_t *child = children; child != NULL; child = child->next) {
        if (child->filename == NULL || strcmp(child->filename, target_filename) != 0) {
            continue;
        }

        if (child->filetype == LIBMTP_FILETYPE_FOLDER) {
            set_error(error_message, error_message_capacity, "The map target name is already used by a folder");
            LIBMTP_destroy_file_t(children);
            return -3;
        }

        *match_count += 1;
        *item_id = child->item_id;
        *size_bytes = child->filesize;
    }

    LIBMTP_destroy_file_t(children);
    return 0;
}

/* Transfer the catalog-validated artifact on an already-open device.
 * Keeping this part separate lets the production install path perform its
 * sampled verification after the write session is released. */
static int send_stage42_map_file(
    LIBMTP_mtpdevice_t *device,
    const char *local_path,
    const char *target_filename,
    const struct stat *source_stat,
    uint32_t *item_id,
    uint64_t *size_bytes,
    TerentoMTPProgressCallback progress_callback,
    const void *progress_context,
    char *error_message,
    size_t error_message_capacity
) {
    if (device == NULL || local_path == NULL || target_filename == NULL
        || source_stat == NULL || item_id == NULL || size_bytes == NULL) {
        set_error(error_message, error_message_capacity, "The map transfer request is unavailable");
        return -1;
    }

    *item_id = 0;
    *size_bytes = 0;

    uint32_t storage_id = 0;
    uint32_t folder_id = 0;
    int result = find_single_garmin_folder(
        device,
        &storage_id,
        &folder_id,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        return result;
    }

    uint32_t existing_item_id = 0;
    uint64_t existing_size = 0;
    size_t existing_count = 0;
    result = find_stage42_map_file(
        device,
        storage_id,
        folder_id,
        target_filename,
        &existing_item_id,
        &existing_size,
        &existing_count,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        return result;
    }
    if (existing_count != 0) {
        set_error(
            error_message,
            error_message_capacity,
            "The selected map target already exists; nothing was overwritten"
        );
        return TERENTO_MTP_MAP_TARGET_EXISTS;
    }

    LIBMTP_file_t *file = LIBMTP_new_file_t();
    if (file == NULL) {
        set_error(error_message, error_message_capacity, "Could not prepare the map object");
        return -5;
    }

    file->storage_id = storage_id;
    file->parent_id = folder_id;
    file->filesize = (uint64_t)source_stat->st_size;
    file->modificationdate = time(NULL);
    file->filetype = LIBMTP_FILETYPE_UNKNOWN;
    file->filename = strdup(target_filename);
    if (file->filename == NULL) {
        LIBMTP_destroy_file_t(file);
        set_error(error_message, error_message_capacity, "Could not prepare the map filename");
        return -6;
    }

    LIBMTP_Clear_Errorstack(device);
    result = LIBMTP_Send_File_From_File(
        device,
        local_path,
        file,
        progress_callback,
        progress_context
    );
    if (file->item_id != 0) {
        *item_id = file->item_id;
    }
    LIBMTP_destroy_file_t(file);

    if (result != 0) {
        set_write_test_device_error(
            error_message,
            error_message_capacity,
            device,
            "The selected map could not be transferred"
        );
        return -7;
    }

    if (*item_id == 0) {
        uint64_t sent_size = 0;
        size_t sent_count = 0;
        result = find_stage42_map_file(
            device,
            storage_id,
            folder_id,
            target_filename,
            item_id,
            &sent_size,
            &sent_count,
            error_message,
            error_message_capacity
        );
        if (result != 0 || sent_count != 1 || *item_id == 0) {
            if (result == 0) {
                set_error(error_message, error_message_capacity, "The transferred map could not be identified safely");
                result = -8;
            }
            return result;
        }
    }

    *size_bytes = (uint64_t)source_stat->st_size;
    return 0;
}

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
) {
    if (validate_map_operation_profile(
            profile,
            error_message,
            error_message_capacity
        ) != 0) {
        return TERENTO_MTP_MAP_UNSUPPORTED_DEVICE;
    }
    if (item_id == NULL || size_bytes == NULL) {
        set_error(error_message, error_message_capacity, "The map installation result is unavailable");
        return -1;
    }

    *item_id = 0;
    *size_bytes = 0;
    set_error(error_message, error_message_capacity, "");

    if (validate_stage42_target(target_filename, error_message, error_message_capacity) != 0) {
        return -2;
    }

    struct stat source_stat;
    if (validate_stage42_source(local_path, &source_stat, error_message, error_message_capacity) != 0) {
        return -3;
    }

    uint16_t vendor_id = 0;
    uint16_t product_id = 0;
    LIBMTP_mtpdevice_t *device = open_single_garmin_device(
        &vendor_id,
        &product_id,
        error_message,
        error_message_capacity,
        1
    );
    if (device == NULL) {
        return -4;
    }

    int result = validate_live_map_operation_device(
        profile,
        vendor_id,
        product_id,
        device,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        result = map_live_validation_error(result);
        goto cleanup;
    }

    result = send_stage42_map_file(
        device,
        local_path,
        target_filename,
        &source_stat,
        item_id,
        size_bytes,
        progress_callback,
        progress_context,
        error_message,
        error_message_capacity
    );

cleanup:
    LIBMTP_Release_Device(device);
    return result;
}

static int validate_managed_map_object(
    LIBMTP_mtpdevice_t *device,
    const char *target_filename,
    uint32_t expected_item_id,
    uint64_t expected_size_bytes,
    uint32_t *resolved_item_id,
    uint64_t *actual_size_bytes,
    char *error_message,
    size_t error_message_capacity
) {
    uint32_t storage_id = 0;
    uint32_t folder_id = 0;
    int result = find_single_garmin_folder(
        device,
        &storage_id,
        &folder_id,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        return result;
    }

    uint32_t actual_item_id = 0;
    uint64_t remote_size = 0;
    size_t match_count = 0;
    result = find_stage42_map_file(
        device,
        storage_id,
        folder_id,
        target_filename,
        &actual_item_id,
        &remote_size,
        &match_count,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        return result;
    }
    if (match_count == 0) {
        set_error(error_message, error_message_capacity, "The transferred map was not found on the Garmin device");
        return TERENTO_MTP_MAP_REMOTE_FILE_MISSING;
    }
    /* MTP object IDs may be re-enumerated by Garmin firmware after a write.
       A zero expected ID deliberately requests resolution by the exact
       managed filename and validated size instead. */
    if (match_count != 1
        || (expected_item_id != 0 && actual_item_id != expected_item_id)) {
        set_error(error_message, error_message_capacity, "The managed map object identity did not match exactly");
        return TERENTO_MTP_MAP_OBJECT_ID_MISMATCH;
    }
    if (remote_size == 0 || remote_size != expected_size_bytes) {
        set_error(error_message, error_message_capacity, "The managed map size did not match the validated source");
        return TERENTO_MTP_MAP_OBJECT_ID_MISMATCH;
    }

    if (resolved_item_id != NULL) {
        *resolved_item_id = actual_item_id;
    }
    if (actual_size_bytes != NULL) {
        *actual_size_bytes = remote_size;
    }
    return 0;
}

int terento_mtp_verify_managed_map_samples(
    const TerentoMTPMapOperationProfile *profile,
    const char *local_path,
    const char *target_filename,
    uint32_t expected_item_id,
    uint64_t expected_size_bytes,
    uint32_t *resolved_item_id,
    const uint64_t *sample_offsets,
    size_t sample_count,
    uint32_t sample_length,
    uint64_t *sampled_bytes,
    uint32_t *matched_samples,
    TerentoMTPProgressCallback progress_callback,
    const void *progress_context,
    char *error_message,
    size_t error_message_capacity
) {
    if (validate_map_operation_profile(
            profile,
            error_message,
            error_message_capacity
        ) != 0) {
        return TERENTO_MTP_MAP_UNSUPPORTED_DEVICE;
    }
    if (local_path == NULL || expected_item_id == 0 || expected_size_bytes == 0
        || resolved_item_id == NULL
        || sample_offsets == NULL || sample_count == 0 || sample_count > 32
        || sample_length == 0 || sampled_bytes == NULL || matched_samples == NULL) {
        set_error(error_message, error_message_capacity, "The sampled map verification request is invalid");
        return -1;
    }

    *sampled_bytes = 0;
    *matched_samples = 0;
    *resolved_item_id = 0;
    set_error(error_message, error_message_capacity, "");

    if (validate_stage42_target(target_filename, error_message, error_message_capacity) != 0) {
        return -2;
    }

    struct stat source_stat;
    if (validate_stage42_source(local_path, &source_stat, error_message, error_message_capacity) != 0) {
        return -3;
    }
    if ((uint64_t)source_stat.st_size != expected_size_bytes) {
        set_error(error_message, error_message_capacity, "The local source size changed before sampled verification");
        return -4;
    }

    uint64_t total_sample_bytes = 0;
    for (size_t index = 0; index < sample_count; index += 1) {
        if (sample_offsets[index] >= expected_size_bytes) {
            set_error(error_message, error_message_capacity, "A sampled map offset is outside the validated source");
            return -5;
        }
        uint64_t remaining = expected_size_bytes - sample_offsets[index];
        uint64_t requested = remaining < sample_length ? remaining : sample_length;
        if (UINT64_MAX - total_sample_bytes < requested) {
            set_error(error_message, error_message_capacity, "The sampled verification size is unavailable");
            return -6;
        }
        total_sample_bytes += requested;
    }

    FILE *source = fopen(local_path, "rb");
    if (source == NULL) {
        set_error(error_message, error_message_capacity, "The validated map source could not be opened");
        return -7;
    }

    const unsigned int maximum_sample_attempts = 3;
    LIBMTP_mtpdevice_t *device = NULL;
    int result = 0;

    for (size_t index = 0; index < sample_count; index += 1) {
        uint64_t remaining = expected_size_bytes - sample_offsets[index];
        uint32_t region_length = remaining < sample_length ? (uint32_t)remaining : sample_length;
        /* Keep the exact sampled byte coverage, but do not ask Garmin firmware
           to buffer a multi-megabyte GetPartialObject response in one call. */
        for (uint32_t consumed = 0; consumed < region_length;) {
        uint64_t offset = sample_offsets[index] + consumed;
        uint32_t requested = region_length - consumed;
        if (requested > 64 * 1024) requested = 64 * 1024;
        unsigned int failed_attempts = 0;
        int sample_verified = 0;

        while (!sample_verified) {
            if (device == NULL) {
                uint16_t vendor_id = 0;
                uint16_t product_id = 0;
                device = open_single_garmin_device(
                    &vendor_id,
                    &product_id,
                    error_message,
                    error_message_capacity,
                    1
                );
                if (device == NULL) {
                    result = -8;
                    goto sample_cleanup;
                }

                int identity_result = validate_live_map_operation_device(
                        profile,
                        vendor_id,
                        product_id,
                        device,
                        error_message,
                        error_message_capacity
                    );
                if (identity_result != 0) {
                    result = map_live_validation_error(identity_result);
                    goto sample_cleanup;
                }

                /* Resolve the current ID: the SendObject ID can be stale in
                   a fresh session even though the exact target is present. */
                uint32_t current_item_id = 0;
                result = validate_managed_map_object(
                    device,
                    target_filename,
                    0,
                    expected_size_bytes,
                    &current_item_id,
                    NULL,
                    error_message,
                    error_message_capacity
                );
                if (result != 0) {
                    goto sample_cleanup;
                }
                if (current_item_id == 0) {
                    set_error(error_message, error_message_capacity, "The managed map object identity could not be resolved");
                    result = TERENTO_MTP_MAP_OBJECT_ID_MISMATCH;
                    goto sample_cleanup;
                }
                *resolved_item_id = current_item_id;
            }

            unsigned char *raw_bytes = NULL;
            unsigned int actual_length = 0;
            LIBMTP_Clear_Errorstack(device);
            int read_result = LIBMTP_GetPartialObject(
                device,
                *resolved_item_id,
                offset,
                requested,
                &raw_bytes,
                &actual_length
            );

            if (read_result != 0 || actual_length != requested) {
                if (raw_bytes != NULL) {
                    LIBMTP_FreeMemory(raw_bytes);
                }
                failed_attempts += 1;
                if (failed_attempts >= maximum_sample_attempts) {
                    set_device_error(error_message, error_message_capacity, device, "The sampled map verification failed repeatedly");
                    result = -9;
                    goto sample_cleanup;
                }
                LIBMTP_Release_Device(device);
                device = NULL;
                usleep(250000);
                continue;
            }

            unsigned char *source_bytes = malloc(requested);
            if (source_bytes == NULL) {
                LIBMTP_FreeMemory(raw_bytes);
                set_error(error_message, error_message_capacity, "The sampled map verification buffer could not be allocated");
                result = -10;
                goto sample_cleanup;
            }

            int seek_result = fseeko(source, (off_t)offset, SEEK_SET);
            size_t source_length = seek_result == 0
                ? fread(source_bytes, 1, requested, source)
                : 0;
            int matches = source_length == requested
                && memcmp(source_bytes, raw_bytes, requested) == 0;
            free(source_bytes);
            LIBMTP_FreeMemory(raw_bytes);

            if (!matches) {
                set_error(error_message, error_message_capacity, "A sampled map region did not match the validated source");
                result = -11;
                goto sample_cleanup;
            }

            *sampled_bytes += requested;
            consumed += requested;
            sample_verified = 1;
            if (progress_callback != NULL
                && progress_callback(*sampled_bytes, total_sample_bytes, progress_context) != 0) {
                set_error(error_message, error_message_capacity, "The sampled map verification was cancelled");
                result = -12;
                goto sample_cleanup;
            }
        }
        }
        *matched_samples += 1;
        /* A clean session boundary between regions lets firmware settle and
           avoids carrying a stale object cache through randomized seeks. */
        LIBMTP_Release_Device(device);
        device = NULL;
    }

sample_cleanup:
    if (device != NULL) {
        LIBMTP_Release_Device(device);
    }
    fclose(source);
    return result;
}

int terento_mtp_delete_managed_map(
    const TerentoMTPMapOperationProfile *profile,
    const char *target_filename,
    uint32_t expected_item_id,
    uint64_t expected_size_bytes,
    char *error_message,
    size_t error_message_capacity
) {
    if (validate_map_operation_profile(
            profile,
            error_message,
            error_message_capacity
        ) != 0) {
        return TERENTO_MTP_MAP_UNSUPPORTED_DEVICE;
    }
    if (expected_item_id == 0) {
        set_error(error_message, error_message_capacity, "Managed map cleanup requires an exact object identity");
        return -1;
    }

    set_error(error_message, error_message_capacity, "");
    if (validate_stage42_target(target_filename, error_message, error_message_capacity) != 0) {
        return -2;
    }

    uint16_t vendor_id = 0;
    uint16_t product_id = 0;
    LIBMTP_mtpdevice_t *device = open_single_garmin_device(
        &vendor_id,
        &product_id,
        error_message,
        error_message_capacity,
        1
    );
    if (device == NULL) {
        return -3;
    }

    int result = validate_live_map_operation_device(
        profile,
        vendor_id,
        product_id,
        device,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        result = map_live_validation_error(result);
        goto cleanup;
    }

    uint32_t storage_id = 0;
    uint32_t folder_id = 0;
    result = find_single_garmin_folder(device, &storage_id, &folder_id, error_message, error_message_capacity);
    if (result != 0) {
        goto cleanup;
    }

    uint32_t actual_item_id = 0;
    uint64_t remote_size = 0;
    size_t match_count = 0;
    result = find_stage42_map_file(
        device,
        storage_id,
        folder_id,
        target_filename,
        &actual_item_id,
        &remote_size,
        &match_count,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        goto cleanup;
    }
    if (match_count != 1
        || (expected_size_bytes == 0 && actual_item_id != expected_item_id)
        || (expected_size_bytes != 0 && remote_size != expected_size_bytes)) {
        set_error(error_message, error_message_capacity, "Managed map cleanup refused: exact target identity did not match");
        result = TERENTO_MTP_MAP_OBJECT_ID_MISMATCH;
        goto cleanup;
    }

    LIBMTP_Clear_Errorstack(device);
    if (LIBMTP_Delete_Object(device, actual_item_id) != 0) {
        set_device_error(error_message, error_message_capacity, device, "The managed map could not be removed");
        result = -4;
        goto cleanup;
    }

    /*
     * Do not enumerate /GARMIN again in this session. Garmin devices can
     * leave the libmtp object list stale, or block while refreshing it,
     * immediately after DeleteObject. The Swift lifecycle layer releases
     * this session and performs the authoritative read-only post-delete
     * verification in a fresh session.
     */
    result = 0;

cleanup:
    LIBMTP_Release_Device(device);
    return result;
}

int terento_mtp_delete_external_map(
    const TerentoMTPMapOperationProfile *profile,
    const char *target_filename,
    uint32_t expected_item_id,
    uint64_t expected_size_bytes,
    char *error_message,
    size_t error_message_capacity
) {
    if (validate_map_operation_profile(
            profile,
            error_message,
            error_message_capacity
        ) != 0) {
        return TERENTO_MTP_MAP_UNSUPPORTED_DEVICE;
    }
    if (expected_item_id == 0) {
        set_error(error_message, error_message_capacity, "External map removal requires an exact object identity");
        return -1;
    }

    set_error(error_message, error_message_capacity, "");
    if (validate_external_map_target(target_filename, error_message, error_message_capacity) != 0) {
        return -2;
    }

    uint16_t vendor_id = 0;
    uint16_t product_id = 0;
    LIBMTP_mtpdevice_t *device = open_single_garmin_device(
        &vendor_id,
        &product_id,
        error_message,
        error_message_capacity,
        1
    );
    if (device == NULL) {
        return -3;
    }

    int result = validate_live_map_operation_device(
        profile,
        vendor_id,
        product_id,
        device,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        result = map_live_validation_error(result);
        goto external_cleanup;
    }

    uint32_t storage_id = 0;
    uint32_t folder_id = 0;
    result = find_single_garmin_folder(device, &storage_id, &folder_id, error_message, error_message_capacity);
    if (result != 0) {
        goto external_cleanup;
    }

    uint32_t actual_item_id = 0;
    uint64_t remote_size = 0;
    size_t match_count = 0;
    result = find_stage42_map_file(
        device,
        storage_id,
        folder_id,
        target_filename,
        &actual_item_id,
        &remote_size,
        &match_count,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        goto external_cleanup;
    }
    if (match_count != 1
        || (expected_size_bytes == 0 && actual_item_id != expected_item_id)
        || (expected_size_bytes != 0 && remote_size != expected_size_bytes)) {
        set_error(error_message, error_message_capacity, "External map removal refused: exact target identity did not match");
        result = TERENTO_MTP_MAP_OBJECT_ID_MISMATCH;
        goto external_cleanup;
    }

    LIBMTP_Clear_Errorstack(device);
    if (LIBMTP_Delete_Object(device, actual_item_id) != 0) {
        set_device_error(error_message, error_message_capacity, device, "The external map could not be removed");
        result = -4;
        goto external_cleanup;
    }

    /* The Swift lifecycle layer performs authoritative post-delete checking
       in a fresh MTP session because this object list may be stale. */
    result = 0;

external_cleanup:
    LIBMTP_Release_Device(device);
    return result;
}

static int validate_write_test_source(
    const char *local_path,
    struct stat *file_stat,
    char *error_message,
    size_t error_message_capacity
) {
    if (local_path == NULL || file_stat == NULL) {
        set_error(error_message, error_message_capacity, "Write-test source file is unavailable");
        return -1;
    }

    const char *filename = strrchr(local_path, '/');
    filename = filename != NULL ? filename + 1 : local_path;
    if (strcmp(filename, TERENTO_WRITE_TEST_FILENAME) != 0) {
        set_error(
            error_message,
            error_message_capacity,
            "Only terento-write-test.txt can be sent by the Write Test"
        );
        return -2;
    }

    if (stat(local_path, file_stat) != 0) {
        char message[256];
        snprintf(message, sizeof(message), "Could not read the local test file: %s", strerror(errno));
        set_error(error_message, error_message_capacity, message);
        return -3;
    }

    if (!S_ISREG(file_stat->st_mode)) {
        set_error(error_message, error_message_capacity, "The Write Test source must be a regular file");
        return -4;
    }

    if (file_stat->st_size <= 0 || file_stat->st_size > TERENTO_WRITE_TEST_MAX_BYTES) {
        set_error(error_message, error_message_capacity, "The Write Test source must be between 1 byte and 1 MiB");
        return -5;
    }

    return 0;
}

static int validate_interrupt_test_source(
    const char *local_path,
    struct stat *file_stat,
    char *error_message,
    size_t error_message_capacity
) {
    if (local_path == NULL || file_stat == NULL) {
        set_error(error_message, error_message_capacity, "Interruption-test source file is unavailable");
        return -1;
    }

    const char *filename = strrchr(local_path, '/');
    filename = filename != NULL ? filename + 1 : local_path;
    if (strcmp(filename, TERENTO_INTERRUPT_TEST_FILENAME) != 0) {
        set_error(
            error_message,
            error_message_capacity,
            "Only the generated interruption-test payload can be sent"
        );
        return -2;
    }

    if (stat(local_path, file_stat) != 0) {
        char message[256];
        snprintf(message, sizeof(message), "Could not read the local interruption-test file: %s", strerror(errno));
        set_error(error_message, error_message_capacity, message);
        return -3;
    }

    if (!S_ISREG(file_stat->st_mode)) {
        set_error(error_message, error_message_capacity, "The interruption-test source must be a regular file");
        return -4;
    }

    if (file_stat->st_size <= 0 || file_stat->st_size > TERENTO_INTERRUPT_TEST_MAX_BYTES) {
        set_error(error_message, error_message_capacity, "The interruption-test source must be between 1 byte and 64 MiB");
        return -5;
    }

    return 0;
}

typedef struct {
    uint64_t interrupt_after_bytes;
    uint8_t cancel_at_threshold;
    uint8_t pause_for_physical_disconnect;
    uint8_t threshold_handled;
    uint8_t transfer_was_cancelled;
    unsigned int last_reported_percent;
} TerentoInterruptProgress;

static int interruption_progress_callback(
    uint64_t sent,
    uint64_t total,
    const void *data
) {
    TerentoInterruptProgress *progress = (TerentoInterruptProgress *)data;
    if (progress == NULL || total == 0) {
        return 0;
    }

    unsigned int percent = (unsigned int)(
        ((long double)sent * 100.0L) / (long double)total
    );
    if (percent > 100) {
        percent = 100;
    }

    if (percent != progress->last_reported_percent) {
        progress->last_reported_percent = percent;
        fprintf(
            stdout,
            "Interruption Test: transfer %u%% (%llu/%llu bytes)\n",
            percent,
            (unsigned long long)sent,
            (unsigned long long)total
        );
        fflush(stdout);
    }

    if (!progress->threshold_handled && sent >= progress->interrupt_after_bytes) {
        progress->threshold_handled = 1;

        if (progress->cancel_at_threshold) {
            progress->transfer_was_cancelled = 1;
            fprintf(stdout, "Interruption Test: canceling transfer at the safety checkpoint.\n");
            fflush(stdout);
            return 1;
        }

        if (progress->pause_for_physical_disconnect) {
            fprintf(
                stdout,
                "Interruption Test: PAUSED at the safety checkpoint. "
                "Disconnect the watch now, then press Return.\n"
            );
            fflush(stdout);
            int character;
            while ((character = getchar()) != '\n' && character != EOF) {
            }
        }
    }

    return 0;
}

int terento_mtp_write_test_file(
    const char *local_path,
    uint32_t *item_id,
    uint64_t *size_bytes,
    char *error_message,
    size_t error_message_capacity
) {
    if (item_id == NULL || size_bytes == NULL) {
        set_error(error_message, error_message_capacity, "Write-test result is unavailable");
        return -1;
    }

    *item_id = 0;
    *size_bytes = 0;
    set_error(error_message, error_message_capacity, "");

    struct stat source_stat;
    if (validate_write_test_source(local_path, &source_stat, error_message, error_message_capacity) != 0) {
        return -2;
    }

    uint16_t vendor_id = 0;
    uint16_t product_id = 0;
    LIBMTP_mtpdevice_t *device = open_single_garmin_device(
        &vendor_id,
        &product_id,
        error_message,
        error_message_capacity,
        1
    );
    if (device == NULL) {
        return -3;
    }

    int result = validate_write_test_device(
        vendor_id,
        product_id,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        goto cleanup;
    }

    uint32_t storage_id = 0;
    uint32_t folder_id = 0;
    result = find_single_garmin_folder(
        device,
        &storage_id,
        &folder_id,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        goto cleanup;
    }

    uint32_t existing_item_id = 0;
    uint64_t existing_size = 0;
    size_t existing_count = 0;
    result = find_write_test_file(
        device,
        storage_id,
        folder_id,
        &existing_item_id,
        &existing_size,
        &existing_count,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        goto cleanup;
    }
    if (existing_count != 0) {
        set_error(
            error_message,
            error_message_capacity,
            "The Write Test target already exists; nothing was overwritten"
        );
        result = -4;
        goto cleanup;
    }

    LIBMTP_file_t *file = LIBMTP_new_file_t();
    if (file == NULL) {
        set_error(error_message, error_message_capacity, "Could not prepare the Write Test object");
        result = -5;
        goto cleanup;
    }

    file->storage_id = storage_id;
    file->parent_id = folder_id;
    file->filesize = (uint64_t)source_stat.st_size;
    file->modificationdate = time(NULL);
    /*
     * Garmin accepts the payload as a generic MTP object more reliably than
     * when the same .txt payload is advertised as PTP Text. This remains a
     * fixed developer test object; it is not a map transfer path.
     */
    file->filetype = LIBMTP_FILETYPE_UNKNOWN;
    file->filename = strdup(TERENTO_WRITE_TEST_FILENAME);
    if (file->filename == NULL) {
        LIBMTP_destroy_file_t(file);
        set_error(error_message, error_message_capacity, "Could not prepare the Write Test filename");
        result = -6;
        goto cleanup;
    }

    LIBMTP_Clear_Errorstack(device);
    result = LIBMTP_Send_File_From_File(device, local_path, file, NULL, NULL);
    if (file->item_id != 0) {
        *item_id = file->item_id;
    }
    LIBMTP_destroy_file_t(file);

    if (result != 0) {
        set_write_test_device_error(
            error_message,
            error_message_capacity,
            device,
            "The Write Test file could not be sent"
        );
        result = -7;
        goto cleanup;
    }

    if (*item_id == 0) {
        uint64_t sent_size = 0;
        size_t sent_count = 0;
        result = find_write_test_file(
            device,
            storage_id,
            folder_id,
            item_id,
            &sent_size,
            &sent_count,
            error_message,
            error_message_capacity
        );
        if (result != 0 || sent_count != 1 || *item_id == 0) {
            if (result == 0) {
                set_error(error_message, error_message_capacity, "The sent Write Test object could not be identified safely");
                result = -8;
            }
            goto cleanup;
        }
    }

    *size_bytes = (uint64_t)source_stat.st_size;
    result = 0;

cleanup:
    LIBMTP_Release_Device(device);
    return result;
}

int terento_mtp_read_test_file_to_local(
    uint32_t expected_item_id,
    const char *local_path,
    uint64_t *size_bytes,
    char *error_message,
    size_t error_message_capacity
) {
    if (expected_item_id == 0 || local_path == NULL || size_bytes == NULL) {
        set_error(error_message, error_message_capacity, "Write-test read-back request is invalid");
        return -1;
    }

    *size_bytes = 0;
    set_error(error_message, error_message_capacity, "");

    struct stat destination_stat;
    if (stat(local_path, &destination_stat) == 0) {
        set_error(error_message, error_message_capacity, "The read-back destination already exists");
        return -2;
    }
    if (errno != ENOENT) {
        set_error(error_message, error_message_capacity, "The read-back destination is not available");
        return -3;
    }

    uint16_t vendor_id = 0;
    uint16_t product_id = 0;
    LIBMTP_mtpdevice_t *device = open_single_garmin_device(
        &vendor_id,
        &product_id,
        error_message,
        error_message_capacity,
        1
    );
    if (device == NULL) {
        return -4;
    }

    int result = validate_write_test_device(
        vendor_id,
        product_id,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        goto cleanup;
    }

    uint32_t storage_id = 0;
    uint32_t folder_id = 0;
    result = find_single_garmin_folder(
        device,
        &storage_id,
        &folder_id,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        goto cleanup;
    }

    uint32_t actual_item_id = 0;
    uint64_t remote_size = 0;
    size_t match_count = 0;
    result = find_write_test_file(
        device,
        storage_id,
        folder_id,
        &actual_item_id,
        &remote_size,
        &match_count,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        goto cleanup;
    }
    if (match_count != 1 || actual_item_id != expected_item_id) {
        set_error(error_message, error_message_capacity, "The expected Write Test object was not found exactly");
        result = -5;
        goto cleanup;
    }

    LIBMTP_Clear_Errorstack(device);
    if (LIBMTP_Get_File_To_File(device, actual_item_id, local_path, NULL, NULL) != 0) {
        set_device_error(
            error_message,
            error_message_capacity,
            device,
            "The Write Test object could not be read back"
        );
        result = -6;
        goto cleanup;
    }

    *size_bytes = remote_size;
    result = 0;

cleanup:
    LIBMTP_Release_Device(device);
    return result;
}

int terento_mtp_delete_test_file(
    uint32_t expected_item_id,
    char *error_message,
    size_t error_message_capacity
) {
    if (expected_item_id == 0) {
        set_error(error_message, error_message_capacity, "Write-test cleanup request is invalid");
        return -1;
    }

    set_error(error_message, error_message_capacity, "");

    uint16_t vendor_id = 0;
    uint16_t product_id = 0;
    LIBMTP_mtpdevice_t *device = open_single_garmin_device(
        &vendor_id,
        &product_id,
        error_message,
        error_message_capacity,
        1
    );
    if (device == NULL) {
        return -2;
    }

    int result = validate_write_test_device(
        vendor_id,
        product_id,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        goto cleanup;
    }

    uint32_t storage_id = 0;
    uint32_t folder_id = 0;
    result = find_single_garmin_folder(
        device,
        &storage_id,
        &folder_id,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        goto cleanup;
    }

    uint32_t actual_item_id = 0;
    uint64_t remote_size = 0;
    size_t match_count = 0;
    result = find_write_test_file(
        device,
        storage_id,
        folder_id,
        &actual_item_id,
        &remote_size,
        &match_count,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        goto cleanup;
    }
    if (match_count != 1 || actual_item_id != expected_item_id) {
        set_error(error_message, error_message_capacity, "Cleanup refused: the exact Write Test object was not found");
        result = -3;
        goto cleanup;
    }

    LIBMTP_Clear_Errorstack(device);
    if (LIBMTP_Delete_Object(device, actual_item_id) != 0) {
        set_device_error(
            error_message,
            error_message_capacity,
            device,
            "The Write Test object could not be removed"
        );
        result = -4;
        goto cleanup;
    }

    uint32_t remaining_item_id = 0;
    uint64_t remaining_size = 0;
    size_t remaining_count = 0;
    result = find_write_test_file(
        device,
        storage_id,
        folder_id,
        &remaining_item_id,
        &remaining_size,
        &remaining_count,
        error_message,
        error_message_capacity
    );
    if (result == 0 && remaining_count != 0) {
        set_error(error_message, error_message_capacity, "Cleanup could not confirm that the Write Test object was removed");
        result = -5;
    }

cleanup:
    LIBMTP_Release_Device(device);
    return result;
}

int terento_mtp_interrupt_test_file(
    const char *local_path,
    uint8_t interrupt_after_percent,
    uint8_t pause_for_physical_disconnect,
    uint32_t *item_id,
    uint64_t *size_bytes,
    uint8_t *transfer_was_cancelled,
    char *error_message,
    size_t error_message_capacity
) {
    if (item_id == NULL || size_bytes == NULL || transfer_was_cancelled == NULL) {
        set_error(error_message, error_message_capacity, "Interruption-test result is unavailable");
        return -1;
    }

    if (interrupt_after_percent == 0 || interrupt_after_percent >= 100) {
        set_error(error_message, error_message_capacity, "The interruption checkpoint must be between 1% and 99%");
        return -2;
    }

    *item_id = 0;
    *size_bytes = 0;
    *transfer_was_cancelled = 0;
    set_error(error_message, error_message_capacity, "");

    struct stat source_stat;
    if (validate_interrupt_test_source(local_path, &source_stat, error_message, error_message_capacity) != 0) {
        return -3;
    }

    uint16_t vendor_id = 0;
    uint16_t product_id = 0;
    LIBMTP_mtpdevice_t *device = open_single_garmin_device(
        &vendor_id,
        &product_id,
        error_message,
        error_message_capacity,
        1
    );
    if (device == NULL) {
        return -4;
    }

    int result = validate_write_test_device(
        vendor_id,
        product_id,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        goto cleanup;
    }

    uint32_t storage_id = 0;
    uint32_t folder_id = 0;
    result = find_single_garmin_folder(
        device,
        &storage_id,
        &folder_id,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        goto cleanup;
    }

    uint32_t existing_item_id = 0;
    uint64_t existing_size = 0;
    size_t existing_count = 0;
    result = find_interrupt_test_file(
        device,
        storage_id,
        folder_id,
        &existing_item_id,
        &existing_size,
        &existing_count,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        goto cleanup;
    }
    if (existing_count != 0) {
        set_error(
            error_message,
            error_message_capacity,
            "The interruption-test target already exists; nothing was overwritten"
        );
        result = -5;
        goto cleanup;
    }

    LIBMTP_file_t *file = LIBMTP_new_file_t();
    if (file == NULL) {
        set_error(error_message, error_message_capacity, "Could not prepare the interruption-test object");
        result = -6;
        goto cleanup;
    }

    file->storage_id = storage_id;
    file->parent_id = folder_id;
    file->filesize = (uint64_t)source_stat.st_size;
    file->modificationdate = time(NULL);
    file->filetype = LIBMTP_FILETYPE_UNKNOWN;
    file->filename = strdup(TERENTO_INTERRUPT_TEST_FILENAME);
    if (file->filename == NULL) {
        LIBMTP_destroy_file_t(file);
        set_error(error_message, error_message_capacity, "Could not prepare the interruption-test filename");
        result = -7;
        goto cleanup;
    }

    uint64_t source_size = (uint64_t)source_stat.st_size;
    uint64_t interrupt_after_bytes =
        (source_size / 100) * interrupt_after_percent
        + ((source_size % 100) * interrupt_after_percent) / 100;
    TerentoInterruptProgress progress = {
        .interrupt_after_bytes = interrupt_after_bytes,
        .cancel_at_threshold = pause_for_physical_disconnect ? 0 : 1,
        .pause_for_physical_disconnect = pause_for_physical_disconnect,
        .threshold_handled = 0,
        .transfer_was_cancelled = 0,
        .last_reported_percent = 255
    };
    if (progress.interrupt_after_bytes == 0) {
        progress.interrupt_after_bytes = 1;
    }

    LIBMTP_Clear_Errorstack(device);
    result = LIBMTP_Send_File_From_File(
        device,
        local_path,
        file,
        interruption_progress_callback,
        &progress
    );
    if (file->item_id != 0) {
        *item_id = file->item_id;
    }
    *transfer_was_cancelled = progress.transfer_was_cancelled;
    LIBMTP_destroy_file_t(file);

    if (result != 0) {
        if (progress.transfer_was_cancelled) {
            set_error(
                error_message,
                error_message_capacity,
                "The interruption test canceled the transfer at the requested checkpoint"
            );
        } else {
            set_write_test_device_error(
                error_message,
                error_message_capacity,
                device,
                "The interruption-test file could not be sent"
            );
        }
        result = -8;
        goto cleanup;
    }

    if (*item_id == 0) {
        uint64_t sent_size = 0;
        size_t sent_count = 0;
        result = find_interrupt_test_file(
            device,
            storage_id,
            folder_id,
            item_id,
            &sent_size,
            &sent_count,
            error_message,
            error_message_capacity
        );
        if (result != 0 || sent_count != 1 || *item_id == 0) {
            if (result == 0) {
                set_error(error_message, error_message_capacity, "The interruption-test object could not be identified safely");
                result = -9;
            }
            goto cleanup;
        }
    }

    *size_bytes = (uint64_t)source_stat.st_size;
    result = 0;

cleanup:
    LIBMTP_Release_Device(device);
    return result;
}

int terento_mtp_inspect_interrupt_test_file(
    uint32_t *item_id,
    uint64_t *size_bytes,
    size_t *match_count,
    char *error_message,
    size_t error_message_capacity
) {
    if (item_id == NULL || size_bytes == NULL || match_count == NULL) {
        set_error(error_message, error_message_capacity, "Interruption-test inspection result is unavailable");
        return -1;
    }

    *item_id = 0;
    *size_bytes = 0;
    *match_count = 0;
    set_error(error_message, error_message_capacity, "");

    uint16_t vendor_id = 0;
    uint16_t product_id = 0;
    LIBMTP_mtpdevice_t *device = open_single_garmin_device(
        &vendor_id,
        &product_id,
        error_message,
        error_message_capacity,
        1
    );
    if (device == NULL) {
        return -2;
    }

    int result = validate_write_test_device(
        vendor_id,
        product_id,
        error_message,
        error_message_capacity
    );
    if (result == 0) {
        uint32_t storage_id = 0;
        uint32_t folder_id = 0;
        result = find_single_garmin_folder(
            device,
            &storage_id,
            &folder_id,
            error_message,
            error_message_capacity
        );
        if (result == 0) {
            result = find_interrupt_test_file(
                device,
                storage_id,
                folder_id,
                item_id,
                size_bytes,
                match_count,
                error_message,
                error_message_capacity
            );
        }
    }

    LIBMTP_Release_Device(device);
    return result;
}

int terento_mtp_delete_interrupt_test_file(
    uint32_t expected_item_id,
    char *error_message,
    size_t error_message_capacity
) {
    if (expected_item_id == 0) {
        set_error(error_message, error_message_capacity, "Interruption-test cleanup requires an exact object identity");
        return -1;
    }

    set_error(error_message, error_message_capacity, "");

    uint16_t vendor_id = 0;
    uint16_t product_id = 0;
    LIBMTP_mtpdevice_t *device = open_single_garmin_device(
        &vendor_id,
        &product_id,
        error_message,
        error_message_capacity,
        1
    );
    if (device == NULL) {
        return -2;
    }

    int result = validate_write_test_device(
        vendor_id,
        product_id,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        goto cleanup;
    }

    uint32_t storage_id = 0;
    uint32_t folder_id = 0;
    result = find_single_garmin_folder(
        device,
        &storage_id,
        &folder_id,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        goto cleanup;
    }

    uint32_t actual_item_id = 0;
    uint64_t remote_size = 0;
    size_t match_count = 0;
    result = find_interrupt_test_file(
        device,
        storage_id,
        folder_id,
        &actual_item_id,
        &remote_size,
        &match_count,
        error_message,
        error_message_capacity
    );
    if (result != 0) {
        goto cleanup;
    }
    if (match_count != 1 || actual_item_id != expected_item_id) {
        set_error(
            error_message,
            error_message_capacity,
            "Interruption-test cleanup refused: exact object identity did not match"
        );
        result = -3;
        goto cleanup;
    }

    LIBMTP_Clear_Errorstack(device);
    if (LIBMTP_Delete_Object(device, actual_item_id) != 0) {
        set_device_error(
            error_message,
            error_message_capacity,
            device,
            "The interruption-test object could not be removed"
        );
        result = -4;
        goto cleanup;
    }

    uint32_t remaining_item_id = 0;
    uint64_t remaining_size = 0;
    size_t remaining_count = 0;
    result = find_interrupt_test_file(
        device,
        storage_id,
        folder_id,
        &remaining_item_id,
        &remaining_size,
        &remaining_count,
        error_message,
        error_message_capacity
    );
    if (result == 0 && remaining_count != 0) {
        set_error(error_message, error_message_capacity, "Cleanup could not confirm that the interruption-test object was removed");
        result = -5;
    }

cleanup:
    LIBMTP_Release_Device(device);
    return result;
}

int terento_mtp_read_snapshot(
    TerentoMTPDeviceSnapshot *snapshot,
    char *error_message,
    size_t error_message_capacity
) {
    if (snapshot == NULL) {
        set_error(error_message, error_message_capacity, "Snapshot output is unavailable");
        return -1;
    }

    clear_snapshot(snapshot);
    set_error(error_message, error_message_capacity, "");

    LIBMTP_Init();
    LIBMTP_Set_Debug(0);

    LIBMTP_raw_device_t *raw_devices = NULL;
    int raw_device_count = 0;
    LIBMTP_error_number_t detect_result = LIBMTP_Detect_Raw_Devices(
        &raw_devices,
        &raw_device_count
    );

    if (detect_result != LIBMTP_ERROR_NONE || raw_device_count <= 0 || raw_devices == NULL) {
        free(raw_devices);
        set_error(error_message, error_message_capacity, "No MTP device connected");
        return -2;
    }

    int garmin_count = 0;
    int selected_index = -1;
    for (int index = 0; index < raw_device_count; index += 1) {
        if (raw_devices[index].device_entry.vendor_id == GARMIN_VENDOR_ID) {
            garmin_count += 1;
            selected_index = index;
        }
    }

    if (garmin_count == 0) {
        free(raw_devices);
        set_error(error_message, error_message_capacity, "No Garmin MTP device detected");
        return -3;
    }

    if (garmin_count != 1 || selected_index < 0) {
        free(raw_devices);
        set_error(error_message, error_message_capacity, "More than one Garmin MTP device detected");
        return -4;
    }

    LIBMTP_raw_device_t selected_device = raw_devices[selected_index];
    snapshot->vendor_id = selected_device.device_entry.vendor_id;
    snapshot->product_id = selected_device.device_entry.product_id;

    LIBMTP_mtpdevice_t *device = LIBMTP_Open_Raw_Device_Uncached(&raw_devices[selected_index]);
    free(raw_devices);
    raw_devices = NULL;

    if (device == NULL) {
        set_error(error_message, error_message_capacity, "Garmin MTP device could not be opened");
        clear_snapshot(snapshot);
        return -5;
    }

    int result = 0;

    LIBMTP_Clear_Errorstack(device);
    if (copy_libmtp_text(
            &snapshot->manufacturer,
            LIBMTP_Get_Manufacturername(device),
            "Garmin"
        ) != 0) {
        set_error(error_message, error_message_capacity, "Could not read manufacturer information");
        result = -6;
        goto cleanup;
    }

    LIBMTP_Clear_Errorstack(device);
    if (copy_libmtp_text(
            &snapshot->model,
            LIBMTP_Get_Modelname(device),
            "Garmin smartwatch"
        ) != 0) {
        set_error(error_message, error_message_capacity, "Could not read model information");
        result = -7;
        goto cleanup;
    }

    LIBMTP_Clear_Errorstack(device);
    if (copy_libmtp_text(
            &snapshot->device_version,
            LIBMTP_Get_Deviceversion(device),
            "Unknown"
        ) != 0) {
        set_error(error_message, error_message_capacity, "Could not read device version");
        result = -8;
        goto cleanup;
    }

    LIBMTP_Clear_Errorstack(device);
    if (copy_libmtp_text(
            &snapshot->serial_number,
            LIBMTP_Get_Serialnumber(device),
            ""
        ) != 0) {
        set_error(error_message, error_message_capacity, "Could not read the local device discriminator");
        result = -9;
        goto cleanup;
    }

    LIBMTP_Clear_Errorstack(device);
    if (LIBMTP_Get_Storage(device, LIBMTP_STORAGE_SORTBY_NOTSORTED) != 0) {
        set_device_error(
            error_message,
            error_message_capacity,
            device,
            "Could not read storage information"
        );
        result = -10;
        goto cleanup;
    }

    size_t storage_count = 0;
    for (LIBMTP_devicestorage_t *storage = device->storage;
         storage != NULL;
         storage = storage->next) {
        storage_count += 1;
        if (storage_count > MAX_SUPPORTED_STORAGES) {
            set_error(error_message, error_message_capacity, "Storage list is unexpectedly large");
            result = -11;
            goto cleanup;
        }
    }

    if (storage_count == 0) {
        set_error(error_message, error_message_capacity, "The Garmin device reported no storage");
        result = -12;
        goto cleanup;
    }

    snapshot->storages = calloc(storage_count, sizeof(*snapshot->storages));
    if (snapshot->storages == NULL) {
        set_error(error_message, error_message_capacity, "Could not allocate storage information");
        result = -13;
        goto cleanup;
    }
    snapshot->storage_count = storage_count;

    size_t storage_index = 0;
    for (LIBMTP_devicestorage_t *storage = device->storage;
         storage != NULL;
         storage = storage->next) {
        if (copy_storage(&snapshot->storages[storage_index], storage, storage_index) != 0) {
            set_error(error_message, error_message_capacity, "Could not copy storage information");
            result = -14;
            goto cleanup;
        }
        storage_index += 1;
    }

    /* Optional read-only identity fallback. Failure here must not hide a
       usable MTP serial or prevent ordinary read-only device detection. */
    read_garmin_device_xml(device, snapshot);

cleanup:
    LIBMTP_Release_Device(device);
    if (result != 0) {
        clear_snapshot(snapshot);
    }
    return result;
}
