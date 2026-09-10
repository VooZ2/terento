"""Exercise the pinned patch without USB; compile its real generated policy/cleanup."""
import pathlib
import re
import subprocess
import sys
import tempfile

patch = pathlib.Path(sys.argv[1])
# A minimal pinned-source fixture includes every match, with sentinels preserving
# unrelated code. Each failure branch is extracted from the patched output below.
source = '''/* untouched prefix */
static void close_usb(PTP_USB* ptp_usb)
{
  if (FLAG_FORCE_RESET_ON_CLOSE(ptp_usb)) {
    libusb_reset_device(ptp_usb->handle);
  }
  libusb_close(ptp_usb->handle);
}
/* init open */
  ret = libusb_open(dev, &device_handle);
/* descriptor failure one */
      perror("libusb_get_active_config_descriptor(2) failed");
      return -1;
/* descriptor failure two */
      perror("libusb_get_active_config_descriptor(2) failed");
      return -1;
/* claim failure */
      fprintf(stderr, "error returned by libusb_claim_interface() = %d", usbresult);
    return -1;
/* second session failure */
      LIBMTP_ERROR("LIBMTP PANIC: failed to open session on second attempt\\n");
      libusb_free_device_list (devs, 0);
/* other session failure */
    libusb_release_interface(ptp_usb->handle, ptp_usb->interface);
    libusb_free_device_list (devs, 0);
/* untouched suffix */
'''
with tempfile.TemporaryDirectory(prefix="terento-usb-session-") as directory:
    directory = pathlib.Path(directory)
    path = directory / "glue.c"
    path.write_text(source)
    subprocess.run(["/usr/bin/perl", str(patch), str(path)], check=True)
    changed = path.read_text()
    subprocess.run(["/usr/bin/perl", str(patch), str(path)], check=True)
    assert path.read_text() == changed, "patch must be idempotent"
    assert changed.startswith("/* untouched prefix */")
    assert changed.endswith("/* untouched suffix */\n")
    for invalid in (source + source, source.replace("    return -1;", "    return -2;")):
        path.write_text(invalid)
        result = subprocess.run(["/usr/bin/perl", str(patch), str(path)], capture_output=True)
        assert result.returncode != 0 and path.read_text() == invalid, "source drift must fail before writing"

    # Execute the generated close policy. This catches a broadened PID/vendor or
    # platform condition, accidentally clearing other flags, or retaining a handle.
    functions = changed[changed.index("static int terento_force_reset_on_close"):changed.index("/* init open */")]
    harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
typedef struct { struct { struct { uint16_t vendor_id, product_id; unsigned flags; } device_entry; } rawdevice; void *handle; int interface; } PTP_USB;
#define FLAG_FORCE_RESET_ON_CLOSE(p) ((p)->rawdevice.device_entry.flags & 2)
static int resets, closes, releases, descriptors, lists;
static void libusb_reset_device(void *h) { assert(h); ++resets; }
static void libusb_close(void *h) { assert(h); ++closes; }
static void libusb_release_interface(void *h, int i) { assert(h && i == 3); ++releases; }
static void libusb_free_config_descriptor(void *p) { assert(p); ++descriptors; }
static void libusb_free_device_list(void *p, int n) { assert(p && n == 0); ++lists; }
#define LIBMTP_ERROR(...) ((void)0)
'''
    harness += functions
    # The inserted resource operations are executed from the generated failure
    # branches, rather than reimplemented in the fake backend.
    markers = ["descriptor failure one", "descriptor failure two", "claim failure", "second session failure", "other session failure"]
    for index, marker in enumerate(markers):
        branch = changed.split("/* " + marker + " */\n", 1)[1].split("/*", 1)[0]
        branch = re.sub(r'^\s*(?:perror|fprintf)\([^\n]+\);\n', '', branch, flags=re.M)
        harness += "\nstatic int failure_%d(PTP_USB *ptp_usb) {\n" % index
        harness += "void *config = ptp_usb, *devs = ptp_usb; (void)config; (void)devs;\n"
        harness += branch + "\nreturn -1;\n}\n"
    harness += r'''
int main(void) {
  PTP_USB value = {{{0x091e, 0x51b8, 0x1236}}, (void *)1, 3};
  close_usb(&value);
#ifdef __APPLE__
  assert(resets == 0);
#else
  assert(resets == 1);
#endif
  assert(closes == 1 && value.handle == NULL && value.rawdevice.device_entry.flags == 0x1236);
  resets = 0; value.handle = (void *)1; value.rawdevice.device_entry.product_id = 0x51b6;
  close_usb(&value); assert(resets == 1);
  resets = 0; value.handle = (void *)1; value.rawdevice.device_entry.product_id = 0x51b8; value.rawdevice.device_entry.vendor_id = 0x1234;
  close_usb(&value); assert(resets == 1);
  resets = 0; value.handle = (void *)1; value.rawdevice.device_entry.flags = 0x1234;
  close_usb(&value); assert(resets == 0);
  int (*failures[])(PTP_USB *) = {failure_0, failure_1, failure_2, failure_3, failure_4};
  for (int i = 0; i < 5; ++i) {
    closes = releases = descriptors = lists = resets = 0; value.handle = (void *)1;
    assert(failures[i](&value) == -1);
    assert(value.handle == NULL && closes == 1 && resets == 0);
    assert(releases == (i >= 3));
    assert(descriptors == (i == 2));
    assert(lists == (i >= 3));
  }
  return 0;
}
'''
    c_file = directory / "test.c"
    c_file.write_text(harness)
    for apple in (True, False):
        executable = directory / ("apple" if apple else "other")
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-D__APPLE__" if apple else "-U__APPLE__", str(c_file), "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
print("PASS: exact macOS VID/PID close policy, unchanged other flags/platforms, failed-open handle cleanup, idempotence and drift rejection")
