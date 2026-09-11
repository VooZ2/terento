"""Execute patched native context/abort/open paths against fake USB."""
from pathlib import Path
import subprocess
import sys
import tempfile
patch=Path(sys.argv[1])
source='''static libusb_context *libmtp_libusb_context;
static LIBMTP_error_number_t init_usb()
{
  static int libusb1_initialized = 0;
  if (libusb1_initialized) return 0;
  if (libusb_init(&libmtp_libusb_context) < 0) return -1;
  libusb1_initialized = 1;
  return 0;
}
void close_device (PTP_USB *ptp_usb, PTPParams *params)
{
  if (ptp_closesession(params)!=PTP_RC_OK) LIBMTP_ERROR("close failed");
  close_usb(ptp_usb);
}
static int failed_open(PTP_USB *ptp_usb) {
    void *devs = (void *)1;
    LIBMTP_ERROR("LIBMTP libusb: Attempt to reset device\\n");
    libusb_reset_device(ptp_usb->handle);
    return 7;
}
'''
harness=r'''
#include <assert.h>
#include <stdlib.h>
typedef int libusb_context;
typedef int LIBMTP_error_number_t;
typedef int PTPParams;
typedef struct { void *handle; int interface; struct { struct { int vendor_id, product_id; } device_entry; } rawdevice; } PTP_USB;
static int contexts, exits, releases, closes, sessions, resets, frees, lists;
static libusb_context ours;
static int libusb_init(libusb_context **p) { *p=&ours; contexts++; return 0; }
static void libusb_exit(libusb_context *p) { assert(p==&ours); exits++; }
static void libusb_release_interface(void *h,int i) { assert(h && i==3); releases++; }
static void libusb_close(void *h) { assert(h); closes++; }
static int ptp_closesession(PTPParams *p) { (void)p; sessions++; return 0; }
static void close_usb(PTP_USB *p) { libusb_release_interface(p->handle,p->interface); libusb_close(p->handle); p->handle=NULL; }
static void libusb_free_device_list(void *p,int unref) { assert(p==(void *)1 && !unref); lists++; }
static void libusb_reset_device(void *p) { assert(p); resets++; }
static void fake_free(void *p) { assert(p); frees++; }
#define free fake_free
#define PTP_RC_OK 0
#define LIBMTP_ERROR_CONNECTING 3
#define LIBMTP_ERROR(...) ((void)0)
'''
main=r'''
int main(void) {
  LIBMTP_Terento_End_Operation(); assert(exits==0);
  assert(init_usb()==0 && init_usb()==0 && contexts==1);
  LIBMTP_Terento_End_Operation(); assert(exits==1 && !libmtp_libusb_context && !libusb1_initialized);
  LIBMTP_Terento_End_Operation(); assert(exits==1);
  assert(init_usb()==0 && contexts==2);
  LIBMTP_Terento_End_Operation(); assert(exits==2);
  PTP_USB d={(void *)1,3,{{0x091e,0x51b8}}};
  LIBMTP_Terento_Abort_Device(&d); assert(!d.handle && releases==1 && closes==1 && !sessions && !resets);
  LIBMTP_Terento_Abort_Device(&d); close_device(&d,NULL);
  assert(releases==1 && closes==1 && !sessions);
  d.handle=(void *)1; close_device(&d,NULL);
  assert(releases==2 && closes==2 && sessions==1);
  d.handle=(void *)1;
#ifdef __APPLE__
  assert(failed_open(&d)==3 && !d.handle && frees==1 && lists==1 && !resets);
#else
  assert(failed_open(&d)==7 && d.handle && !frees && !lists && resets==1);
#endif
  d.handle=(void *)1; d.rawdevice.device_entry.product_id=0x51b6;
  assert(failed_open(&d)==7 && d.handle);
  d.rawdevice.device_entry.product_id=0x51b8; d.rawdevice.device_entry.vendor_id=0x1234;
  assert(failed_open(&d)==7 && d.handle);
  return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='terento-usb-recovery-') as tmp:
 p=Path(tmp)/'glue.c';sym=Path(tmp)/'libmtp.sym';p.write_text(source);sym.write_text('LIBMTP_Init\n')
 subprocess.run([sys.executable,str(patch),str(p),str(sym)],check=True)
 changed=p.read_text();exports=sym.read_text()
 subprocess.run([sys.executable,str(patch),str(p),str(sym)],check=True)
 assert p.read_text()==changed and sym.read_text()==exports
 for bad in (source+source,source.replace('static int libusb1_initialized = 0;','static int libusb1_initialized = 2;')):
  p.write_text(bad)
  assert subprocess.run([sys.executable,str(patch),str(p),str(sym)],capture_output=True).returncode!=0
  assert p.read_text()==bad
 for platform in ('apple','other'):
  p.write_text(harness+changed+main)
  binary=Path(tmp)/platform
  subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-variable','-Wno-unused-function', '-D__APPLE__=1' if platform=='apple' else '-U__APPLE__',str(p),'-o',str(binary)],check=True)
  subprocess.run([str(binary)],check=True)
print('PASS: exact context shutdown/reinitialization, aborted/healthy close, narrow failed-open policy, idempotence and drift checks')

# Compile the actual Swift retry classifier against a small error fixture.
import re
repo=patch.resolve().parents[2]
transport=(repo/'app/TerentoCore/Sources/TerentoPoC/Installation/MTPMapInstallationTransport.swift').read_text()
method=re.search(r"    private static func shouldRetryReadBack\(_ error: Error\) -> Bool \{.*?\n    \}",transport,re.S).group().replace('private static','static')
swift = """import Foundation
enum InstallationTransportError: Error {
case targetAlreadyExists, remoteFileMissing, objectIdentityMismatch, unsupportedDevice, liveIdentityMismatch
case deviceDisconnected(String, createdItemID: UInt32?), operationFailed(String, createdItemID: UInt32?)
}
struct Policy {
"""+method+"""
}
let fatalErrors: [InstallationTransportError] = [.deviceDisconnected("lost", createdItemID: nil), .operationFailed("deadline", createdItemID: nil), .targetAlreadyExists, .unsupportedDevice, .liveIdentityMismatch]
for error in fatalErrors { precondition(!Policy.shouldRetryReadBack(error)) }
precondition(Policy.shouldRetryReadBack(InstallationTransportError.remoteFileMissing))
precondition(Policy.shouldRetryReadBack(InstallationTransportError.objectIdentityMismatch))
"""
with tempfile.TemporaryDirectory(prefix='terento-retry-policy-') as tmp:
 p=Path(tmp)/'Policy.swift';p.write_text(swift);binary=Path(tmp)/'policy'
 subprocess.run(['swiftc',str(p),'-o',str(binary)],check=True)
 subprocess.run([str(binary)],check=True)
print('PASS: production retry policy stops transport/deadline/identity failures and only retries stale object metadata')
