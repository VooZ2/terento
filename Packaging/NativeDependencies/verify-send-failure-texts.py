#!/usr/bin/env python3
"""Verify the pinned libmtp send-failure texts that Terento diagnostics read.

MTPBridge.c describe_map_send_failure() names the step of a failed map send
(and keeps its PTP response) only by these exact error-stack texts. If an
updated libmtp changes any of them, the step would silently become unknown,
so the build stops here instead. Read only; nothing is patched.
"""
from pathlib import Path
import re
import sys

source = Path(sys.argv[1]).read_text()
# Join adjacent C string literals ("a" "b" and "a"\n"b") as the compiler does.
joined = re.sub(r'"\s*"', '', source)
required = (
    '"PTP Layer error %04x: %s"',
    '"LIBMTP_Send_File_From_File(): Could not open source file."',
    '"LIBMTP_Send_File_From_File_Descriptor(): Cancelled transfer."',
    '"LIBMTP_Send_File_From_File_Descriptor(): Could not retrieve updated metadata."',
    '"send_file_object_info(): Could not send object info."',
    '"send_file_object_info():Could not send object property list."',
    '"LIBMTP_Send_File_From_File_Descriptor(): Could not send object."',
)
missing = [text for text in required if text not in joined]
if missing:
    for text in missing:
        print(f"Pinned libmtp send-failure text is missing: {text}", file=sys.stderr)
    sys.exit(1)
print("Pinned libmtp send-failure diagnostic texts: PASS")
