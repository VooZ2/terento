#!/usr/bin/env python3
"""Balance pinned libmtp 1.1.23 device references before context shutdown.

Run after recovery-v1. Device lists own one reference per returned device;
MTP list entries and open handles retain their own references independently.
"""
from pathlib import Path
import sys

path = Path(sys.argv[1])
source = path.read_text()
def replace(old, new, count=1):
    global source
    remainder = source.replace(new, "")
    if source.count(new) == count and old not in remainder:
        return
    if source.count(old) != count or new in source:
        raise SystemExit("Pinned device-reference source drift: " + old[:80])
    source = source.replace(old, new)

replace("  new_list_entry->device = newdevice;",
        "  new_list_entry->device = libusb_ref_device(newdevice);")
replace("    // Do not free() the fields (ptp_usb, params)! These are used elsewhere.\n    free(tmp);",
        "    // The MTP list owns its reference independently of the enumeration list.\n    libusb_unref_device(tmp->device);\n    free(tmp);")
replace("    return NULL;\n  }\n  // Fill in USB device,", "    return devlist; /* preserve existing list on allocation failure */\n  }\n  // Fill in USB device,")
# All enumeration exits in discovery/open, including the recovery-v1 abort.
replace("    if (probe_device_descriptor(devs[i], NULL))\n\treturn 1;\n  }\n  return 0;",
        "    if (probe_device_descriptor(devs[i], NULL)) {\n      libusb_free_device_list (devs, 1);\n      return 1;\n    }\n  }\n  libusb_free_device_list (devs, 1);\n  return 0;")
replace("    // Out of memory\n    *devices = NULL;", "    // Out of memory\n    free_mtpdevice_list(devlist);\n    *devices = NULL;")
old = "libusb_free_device_list (devs, 0);"
new = "libusb_free_device_list (devs, 1);"
if source.count(old) == 10 and source.count(new) == 2:
    source = source.replace(old, new)
elif source.count(old) != 0 or source.count(new) != 12:
    raise SystemExit("Pinned enumeration release count drift")
path.write_text(source)
print("USB device-reference patch applied or already present")
