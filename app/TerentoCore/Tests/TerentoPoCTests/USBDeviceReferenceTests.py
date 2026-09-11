"""Pinned patch contract plus executable ownership tests on upstream helpers."""
from pathlib import Path
import subprocess
import sys
import tempfile

patch = Path(sys.argv[1])
# Exact upstream function bodies; deliberately keep whitespace for patch drift checks.
source = '''static mtpdevice_list_t *append_to_mtpdevice_list(mtpdevice_list_t *devlist,
                                                  libusb_device *newdevice,
                                                  uint32_t bus_location)
{
  mtpdevice_list_t *new_list_entry;

  new_list_entry = (mtpdevice_list_t *) malloc(sizeof(mtpdevice_list_t));
  if (new_list_entry == NULL) {
    return NULL;
  }
  // Fill in USB device, if we *HAVE* to make a copy of the device do it here.
  new_list_entry->device = newdevice;
  new_list_entry->bus_location = bus_location;
  new_list_entry->next = NULL;

  if (devlist == NULL) {
    return new_list_entry;
  } else {
    mtpdevice_list_t *tmp = devlist;
    while (tmp->next != NULL) {
      tmp = tmp->next;
    }
    tmp->next = new_list_entry;
  }
  return devlist;
}
static void free_mtpdevice_list(mtpdevice_list_t *devlist)
{
  mtpdevice_list_t *tmplist = devlist;

  if (devlist == NULL)
    return;
  while (tmplist != NULL) {
    mtpdevice_list_t *tmp = tmplist;
    tmplist = tmplist->next;
    // Do not free() the fields (ptp_usb, params)! These are used elsewhere.
    free(tmp);
  }
  return;
}
int specific(libusb_device **devs, int nrofdevs) {
  for (int i = 0; i < nrofdevs; i++) {
    if (probe_device_descriptor(devs[i], NULL))
\treturn 1;
  }
  return 0;
}
void allocation_failed(void **devices, mtpdevice_list_t *devlist) {
    // Out of memory
    *devices = NULL;
}
'''
# Discovery and every open exit have this exact release call after recovery-v1.
source += '\n'.join('void exit%d(libusb_device **devs) { libusb_free_device_list (devs, 0); }' % i for i in range(10))
harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
typedef struct { int refs; int mtp; } libusb_device;
typedef struct list { libusb_device *device; uint32_t bus_location; struct list *next; } mtpdevice_list_t;
static int fail_alloc;
static void *allocate(size_t n) { return fail_alloc ? NULL : malloc(n); }
#define malloc allocate
static libusb_device *libusb_ref_device(libusb_device *d) { assert(d->refs>0); d->refs++; return d; }
static void libusb_unref_device(libusb_device *d) { assert(d->refs>0); d->refs--; }
static void libusb_free_device_list(libusb_device **ds,int unref) { assert(unref); for (int i=0;ds[i];i++) libusb_unref_device(ds[i]); }
static int probe_device_descriptor(libusb_device *d,void *unused) { (void)unused; return d->mtp; }
'''
main = r'''
int main(void) {
  for(int cycle=0;cycle<100;cycle++) {
    libusb_device a={1,1}, b={1,0}; libusb_device *ds[]={&a,&b,NULL};
    mtpdevice_list_t *list=append_to_mtpdevice_list(NULL,&a,1);
    assert(a.refs==2 && b.refs==1);
    fail_alloc=1; assert(append_to_mtpdevice_list(list,&b,1)==list); fail_alloc=0;
    exit0(ds); assert(a.refs==1 && b.refs==0);
    free_mtpdevice_list(list); assert(a.refs==0);
    // An opened handle keeps the device alive after its enumeration list ends.
    a.refs=1;b.refs=1;libusb_ref_device(&a);exit9(ds);
    assert(a.refs==1 && b.refs==0);libusb_unref_device(&a);assert(a.refs==0);
    a.refs=1;b.refs=1;assert(specific(ds,2)==1 && !a.refs && !b.refs);
    a.refs=1;b.refs=1;a.mtp=0;assert(specific(ds,2)==0 && !a.refs && !b.refs);
    a.refs=1;list=append_to_mtpdevice_list(NULL,&a,1);
    void *raw=(void *)1;allocation_failed(&raw,list);assert(!raw && a.refs==1);
    libusb_unref_device(&a);assert(a.refs==0);
  }
}
'''
with tempfile.TemporaryDirectory(prefix='terento-usb-refs-') as tmp:
    p=Path(tmp)/'glue.c';p.write_text(source)
    subprocess.run([sys.executable,str(patch),str(p)],check=True)
    changed=p.read_text()
    subprocess.run([sys.executable,str(patch),str(p)],check=True)
    assert p.read_text()==changed
    for bad in (source+source, source.replace('libusb_free_device_list (devs, 0);','libusb_free_device_list (devs, 2);',1)):
        p.write_text(bad)
        assert subprocess.run([sys.executable,str(patch),str(p)],capture_output=True).returncode != 0
        assert p.read_text()==bad
    p.write_text(harness+changed+main)
    binary=Path(tmp)/'refs'
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(p),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
print('PASS: 100 reference lifecycle cycles, list/handle ownership, allocation failure, specific-device exits, patch idempotence/drift')
