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
