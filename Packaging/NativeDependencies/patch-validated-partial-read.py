#!/usr/bin/env python3
"""Validated-size partial read for pinned libmtp 1.1.23.

Run after partial-read-diagnostics-v1. Upstream LIBMTP_GetPartialObject calls
LIBMTP_Get_Filemetadata before every chunk. Without a cached property list
(fenix 8 uses DEVICE_FLAG_BROKEN_MTPGETOBJPROPLIST) that adds a
GetObjectPropsSupported and a GetObjectPropValue(ObjectSize) transaction per
chunk, and obj2file() ignores a failed GetObjectPropsSupported. The extension
issues only the partial-read transaction. The caller must already have
resolved the exact object in the same session and must bound every request
by that validated size; it never replaces content or size verification.
"""
from pathlib import Path
import sys

p = Path(sys.argv[1]); symbols = Path(sys.argv[2]); s = p.read_text()
anchor = """int LIBMTP_SendPartialObject(LIBMTP_mtpdevice_t *device, uint32_t const id,"""
extension = """/* Terento: partial read for an object whose identity and size the caller has
 * already validated in this session. No per-call object metadata transaction.
 * The PTP response of a failed read is kept in the error stack exactly as the
 * partial-read-diagnostics patch records it. */
int LIBMTP_Terento_GetPartialObject_Validated(LIBMTP_mtpdevice_t *device,
                                              uint32_t const id,
                                              uint64_t offset, uint32_t maxbytes,
                                              unsigned char **data,
                                              unsigned int *size)
{
  PTPParams *params = (PTPParams *) device->params;
  uint16_t ret;

  *size = 0;
  if (id == 0 || maxbytes == 0) {
    add_error_to_errorstack(device, LIBMTP_ERROR_GENERAL,
      "LIBMTP_Terento_GetPartialObject_Validated: invalid request");
    return -1;
  }
  if (!ptp_operation_issupported(params, PTP_OC_ANDROID_GetPartialObject64)) {
    if (!ptp_operation_issupported(params, PTP_OC_GetPartialObject)) {
      add_error_to_errorstack(device, LIBMTP_ERROR_GENERAL,
        "LIBMTP_Terento_GetPartialObject_Validated: PTP_OC_GetPartialObject not supported");
      return -1;
    }
    if (offset >> 32 != 0) {
      add_error_to_errorstack(device, LIBMTP_ERROR_GENERAL,
        "LIBMTP_Terento_GetPartialObject_Validated: PTP_OC_GetPartialObject only supports 32bit offsets");
      return -1;
    }
    ret = ptp_getpartialobject(params, id, (uint32_t)offset, maxbytes, data, size);
  } else {
    ret = ptp_android_getpartialobject64(params, id, offset, maxbytes, data, size);
  }
  if (ret == PTP_RC_OK)
    return 0;
  add_ptp_error_to_errorstack(device, ret, "Terento partial read response");
  return -1;
}


"""
if "LIBMTP_Terento_GetPartialObject_Validated" in s:
    if s.count(extension + anchor) != 1:
        raise SystemExit("Validated partial-read extension source drift")
    print("Validated partial-read extension already applied")
else:
    if 'add_ptp_error_to_errorstack(device, ret, "Terento partial read response");' not in s:
        raise SystemExit("Validated partial read requires partial-read-diagnostics-v1")
    if s.count(anchor) != 1:
        raise SystemExit("Pinned validated partial-read source drift")
    s = s.replace(anchor, extension + anchor)
    p.write_text(s)
    print("Validated partial-read extension applied")
exports = symbols.read_text()
name = "LIBMTP_Terento_GetPartialObject_Validated"
if name not in exports.splitlines():
    symbols.write_text(exports.rstrip() + "\n" + name + "\n")
