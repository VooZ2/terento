#!/usr/bin/env python3
"""Strict local extensions to pinned libmtp1.1.23; run after lifecycle-v1."""
from pathlib import Path
import sys
p=Path(sys.argv[1]); symbols=Path(sys.argv[2]); s=p.read_text()
def replace(old,new):
 global s
 if new in s and old not in s.replace(new, ""): return
 if s.count(old)!=1: raise SystemExit("Pinned recovery source drift: "+old[:70])
 s=s.replace(old,new)
replace("static libusb_context *libmtp_libusb_context;", """static libusb_context *libmtp_libusb_context;
static int libusb1_initialized = 0;

/* Caller owns Terento's process-wide native-operation gate. All device handles,
 * lists and libmtp objects have been released before this exact context exits.
 * libusb_exit joins its event machinery before another operation may start. */
void LIBMTP_Terento_End_Operation(void)
{
  if (!libusb1_initialized) return;
  libusb_exit(libmtp_libusb_context);
  libmtp_libusb_context = NULL;
  libusb1_initialized = 0;
}

/* Abort host resources only: never send CloseSession, CLEAR_HALT or reset to
 * an unresponsive device. Standard Release_Device subsequently frees objects. */
void LIBMTP_Terento_Abort_Device(void *usbinfo)
{
  PTP_USB *ptp_usb = (PTP_USB *)usbinfo;
  if (ptp_usb == NULL || ptp_usb->handle == NULL) return;
  libusb_release_interface(ptp_usb->handle, ptp_usb->interface);
  libusb_close(ptp_usb->handle);
  ptp_usb->handle = NULL;
}""")
replace("static LIBMTP_error_number_t init_usb()\n{\n  static int libusb1_initialized = 0;", "static LIBMTP_error_number_t init_usb()\n{\n  /* Terento: initialization flag is reset at the operation boundary. */")
replace("void close_device (PTP_USB *ptp_usb, PTPParams *params)\n{", """void close_device (PTP_USB *ptp_usb, PTPParams *params)
{
  if (ptp_usb->handle == NULL) return; /* already aborted without device I/O */""")
replace('    LIBMTP_ERROR("LIBMTP libusb: Attempt to reset device\\n");', '''    /* Local macOS fenix8 candidate: a failed OpenSession must not trigger a
     * reset/re-enumeration storm across parent, worker and other USB clients. */
#ifdef __APPLE__
    if (ptp_usb->rawdevice.device_entry.vendor_id == 0x091e &&
        ptp_usb->rawdevice.device_entry.product_id == 0x51b8) {
      LIBMTP_Terento_Abort_Device(ptp_usb);
      libusb_free_device_list (devs, 0);
      free (ptp_usb);
      return LIBMTP_ERROR_CONNECTING;
    }
#endif
    LIBMTP_ERROR("LIBMTP libusb: Attempt to reset device\\n");''')
exports=symbols.read_text()
for name in ("LIBMTP_Terento_End_Operation", "LIBMTP_Terento_Abort_Device"):
 if name not in exports.splitlines(): exports = exports.rstrip()+"\n"+name+"\n"
p.write_text(s); symbols.write_text(exports)
print("USB recovery/context patch applied or already present")