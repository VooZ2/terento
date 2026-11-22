#!/usr/bin/env python3
"""Read-only transfer bound for pinned libmtp 1.1.23; run after recovery-v1.

Exports two Terento extensions:
- LIBMTP_Terento_Set_Transfer_Timeout: shorten the per-transfer USB timeout of
  one open session. libmtp gives every Garmin DEVICE_FLAG_LONG_TIMEOUT
  (60 s per bulk transfer); the bridge uses this only for read-only sessions
  after OpenSession, so a watch that stops answering ends the read itself.
- LIBMTP_Terento_Take_Transfer_Timed_Out: whether a bulk data or response
  transfer of this process timed out since the last call (and clear it).
USB requests, retries, resets and every write path keep upstream behavior.
"""
from pathlib import Path
import sys

p = Path(sys.argv[1]); symbols = Path(sys.argv[2]); s = p.read_text()


def replace(old, new):
    global s
    if new in s and old not in s.replace(new, ""):
        return
    if s.count(old) != 1:
        raise SystemExit("Pinned read transfer timeout source drift: " + old[:70])
    s = s.replace(old, new)


replace("#define USB_TIMEOUT_LONG        60000\n", """#define USB_TIMEOUT_LONG        60000
/* Terento: set when a bulk transfer times out; read and cleared by the caller. */
static int terento_transfer_timed_out = 0;
""")
replace("    if (ret == LIBUSB_ERROR_TIMEOUT) {\n      return PTP_ERROR_TIMEOUT;\n    }\n",
        "    if (ret == LIBUSB_ERROR_TIMEOUT) {\n      terento_transfer_timed_out = 1;\n"
        "      return PTP_ERROR_TIMEOUT;\n    }\n")
replace("\t    if (ret != LIBUSB_SUCCESS) {\n              free(bytes);\n\t      return PTP_ERROR_IO;\n\t    }\n",
        "\t    if (ret != LIBUSB_SUCCESS) {\n\t      if (ret == LIBUSB_ERROR_TIMEOUT) terento_transfer_timed_out = 1;\n"
        "              free(bytes);\n\t      return PTP_ERROR_IO;\n\t    }\n")
replace("  if (ret != LIBUSB_SUCCESS)\n    return PTP_ERROR_IO;\n  return PTP_RC_OK;\n}\n",
        "  if (ret == LIBUSB_ERROR_TIMEOUT) terento_transfer_timed_out = 1;\n"
        "  if (ret != LIBUSB_SUCCESS)\n    return PTP_ERROR_IO;\n  return PTP_RC_OK;\n}\n")
replace("void set_usb_device_timeout(PTP_USB *ptp_usb, int timeout)\n{\n  ptp_usb->timeout = timeout;\n}\n",
        """void set_usb_device_timeout(PTP_USB *ptp_usb, int timeout)
{
  ptp_usb->timeout = timeout;
}

/* Read-only sessions only, after OpenSession: never longer than libmtp's own. */
void LIBMTP_Terento_Set_Transfer_Timeout(void *usbinfo, int milliseconds)
{
  PTP_USB *ptp_usb = (PTP_USB *)usbinfo;
  if (ptp_usb == NULL || milliseconds <= 0 || milliseconds > ptp_usb->timeout) return;
  ptp_usb->timeout = milliseconds;
}

int LIBMTP_Terento_Take_Transfer_Timed_Out(void)
{
  int timed_out = terento_transfer_timed_out;
  terento_transfer_timed_out = 0;
  return timed_out;
}
""")
exports = symbols.read_text()
for name in ("LIBMTP_Terento_Set_Transfer_Timeout", "LIBMTP_Terento_Take_Transfer_Timed_Out"):
    if name not in exports.splitlines():
        exports = exports.rstrip() + "\n" + name + "\n"
p.write_text(s); symbols.write_text(exports)
print("Read transfer timeout extension applied or already present")
