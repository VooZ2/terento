/* Offline linkage for the real Swift cleanup-refusal path. Never in app sources. */
#include <libmtp.h>
#include <stdint.h>
static int forbidden_calls;
static LIBMTP_mtpdevice_t *deny_open(uint16_t *vendor, uint16_t *product) {
    ++forbidden_calls;
    return NULL;
}
static int deny_send(LIBMTP_mtpdevice_t *device, const char *source, LIBMTP_file_t *file,
    LIBMTP_progressfunc_t callback, const void *context) {
    ++forbidden_calls;
    return -1;
}
static int deny_delete(LIBMTP_mtpdevice_t *device, uint32_t object) {
    ++forbidden_calls;
    return -1;
}
#define TERENTO_NATIVE_TEST_OPEN deny_open
#define LIBMTP_Send_File_From_File deny_send
#define LIBMTP_Delete_Object deny_delete
#include "../Sources/LibMTPBridge/MTPBridge.c"
int terento_cleanup_forbidden_calls(void) { return forbidden_calls; }

/* Test-only pure adapter to the production inventory projection. No device I/O. */
int terento_test_project_garmin_path(const char *root, const char *path, char *out, size_t capacity) {
    TerentoMTPFileInventory inventory={0};
    TerentoMTPFile files[2]={{0}};
    inventory.files=files; inventory.file_count=2;
    files[0].item_id=1; files[0].storage_id=1; files[0].is_folder=1;
    files[0].path=strdup(root); files[0].filename=strdup(root+1);
    files[1].item_id=2; files[1].storage_id=1; files[1].path=strdup(path);
    canonicalize_garmin_inventory_root(&inventory);
    int ok=strlen(files[1].path)<capacity;
    if(ok) strcpy(out,files[1].path);
    free(files[0].path);free(files[0].filename);free(files[1].path);
    return ok;
}
