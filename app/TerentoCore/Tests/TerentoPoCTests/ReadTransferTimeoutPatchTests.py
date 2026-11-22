"""Pinned read transfer timeout patch contract on synthetic libusb1-glue sources."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

patch = Path(sys.argv[1])
define = "#define USB_TIMEOUT_LONG        60000\n"
read_timeout = "    if (ret == LIBUSB_ERROR_TIMEOUT) {\n      return PTP_ERROR_TIMEOUT;\n    }\n"
write_failure = "\t    if (ret != LIBUSB_SUCCESS) {\n              free(bytes);\n\t      return PTP_ERROR_IO;\n\t    }\n"
zero_write = "  if (ret != LIBUSB_SUCCESS)\n    return PTP_ERROR_IO;\n  return PTP_RC_OK;\n}\n"
setter = "void set_usb_device_timeout(PTP_USB *ptp_usb, int timeout)\n{\n  ptp_usb->timeout = timeout;\n}\n"
source = (define + "static short ptp_read_func(void) {\n" + read_timeout + "}\n"
          + "static short ptp_write_func(void) {\n" + write_failure + zero_write
          + "void close_device (PTP_USB *ptp_usb, PTPParams *params)\n{\n}\n" + setter)
symbols = "LIBMTP_FreeMemory\nLIBMTP_Terento_Abort_Device\n"


def run(directory, text, exports=symbols):
    c_path = Path(directory) / "libusb1-glue.c"
    sym_path = Path(directory) / "libmtp.sym"
    c_path.write_text(text)
    sym_path.write_text(exports)
    result = subprocess.run([sys.executable, str(patch), str(c_path), str(sym_path)], capture_output=True)
    return result, c_path.read_text(), sym_path.read_text()


with tempfile.TemporaryDirectory(prefix="terento-read-timeout-") as directory:
    result, patched, exported = run(directory, source)
    assert result.returncode == 0, result.stderr
    # Declared before the read/write functions that set it.
    assert patched.index("static int terento_transfer_timed_out = 0;") < patched.index("ptp_read_func")
    # Every bulk data/response timeout is recorded; nothing else in those paths changes.
    assert patched.count("terento_transfer_timed_out = 1;") == 3
    assert "return PTP_ERROR_TIMEOUT;" in patched and patched.count("return PTP_ERROR_IO;") == 2
    setter_body = patched[patched.index("void LIBMTP_Terento_Set_Transfer_Timeout("):]
    setter_body = setter_body[:setter_body.index("\n}\n")]
    # Only ever shortens the open session's timeout; never sends anything.
    assert "milliseconds > ptp_usb->timeout) return;" in setter_body
    assert not re.search(r"libusb_|ptp_[a-z]+\(", setter_body)
    take = patched[patched.index("int LIBMTP_Terento_Take_Transfer_Timed_Out(void)"):]
    assert "terento_transfer_timed_out = 0;" in take[:take.index("\n}\n")]
    for name in ("LIBMTP_Terento_Set_Transfer_Timeout", "LIBMTP_Terento_Take_Transfer_Timed_Out"):
        assert exported.splitlines().count(name) == 1, name

    again, repeated, repeated_symbols = run(directory, patched, exported)
    assert again.returncode == 0 and repeated == patched and repeated_symbols == exported

    for anchor in (define, read_timeout, write_failure, zero_write, setter):
        for invalid in (source.replace(anchor, ""), source + anchor):
            failed, unchanged, unchanged_symbols = run(directory, invalid)
            assert failed.returncode != 0 and unchanged == invalid and unchanged_symbols == symbols

print("PASS: read transfer timeout patch records bulk timeouts, only shortens the timeout, is idempotent and rejects source drift")
