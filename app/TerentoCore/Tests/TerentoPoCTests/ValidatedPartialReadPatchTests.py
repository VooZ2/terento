"""Pinned validated partial-read patch contract on synthetic libmtp sources."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

patch = Path(sys.argv[1])
diagnostic = '  add_ptp_error_to_errorstack(device, ret, "Terento partial read response");\n'
anchor = "int LIBMTP_SendPartialObject(LIBMTP_mtpdevice_t *device, uint32_t const id,\n"
source = ("int LIBMTP_GetPartialObject(void)\n{\n  LIBMTP_file_t *mtpfile = LIBMTP_Get_Filemetadata(device, id);\n"
          + diagnostic + "  return -1;\n}\n\n\n" + anchor + "  uint64_t offset) {}\n")
symbols = "LIBMTP_FreeMemory\nLIBMTP_Terento_Abort_Device\n"


def run(directory, text, exports=symbols):
    c_path = Path(directory) / "libmtp.c"
    sym_path = Path(directory) / "libmtp.sym"
    c_path.write_text(text)
    sym_path.write_text(exports)
    result = subprocess.run([sys.executable, str(patch), str(c_path), str(sym_path)], capture_output=True)
    return result, c_path.read_text(), sym_path.read_text()


with tempfile.TemporaryDirectory(prefix="terento-validated-read-") as directory:
    result, patched, exported = run(directory, source)
    assert result.returncode == 0, result.stderr
    start = patched.index("int LIBMTP_Terento_GetPartialObject_Validated(")
    body = patched[start:patched.index(anchor)]
    assert patched.index(anchor) > start and patched.count(anchor) == 1
    # Exactly one read transaction per call: no per-chunk object metadata.
    assert "Get_Filemetadata" not in body and "getobjectpropssupported" not in body.lower()
    assert len(re.findall(r"ret = ptp_(?:android_)?getpartialobject(?:64)?\(", body)) == 2
    assert diagnostic in body and "maxbytes == 0" in body and "offset >> 32" in body
    assert exported.splitlines().count("LIBMTP_Terento_GetPartialObject_Validated") == 1

    again, repeated, repeated_symbols = run(directory, patched, exported)
    assert again.returncode == 0 and repeated == patched and repeated_symbols == exported

    for invalid in (source.replace(diagnostic, ""), source.replace(anchor, ""), source + anchor):
        failed, unchanged, unchanged_symbols = run(directory, invalid)
        assert failed.returncode != 0 and unchanged == invalid and unchanged_symbols == symbols

print("PASS: validated partial read issues only the read transaction, is idempotent and rejects source drift")
