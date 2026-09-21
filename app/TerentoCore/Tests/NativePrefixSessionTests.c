/* Production prefix entrypoints with a synthetic libmtp session. Never opens USB. */
#include <libmtp.h>
#include <assert.h>
static LIBMTP_mtpdevice_t *fake_open(uint16_t *, uint16_t *);
static char *fake_serial(LIBMTP_mtpdevice_t *);
static char *fake_manufacturer(LIBMTP_mtpdevice_t *);
static char *fake_model(LIBMTP_mtpdevice_t *);
static int fake_storage(LIBMTP_mtpdevice_t *, int);
static LIBMTP_file_t *fake_files(LIBMTP_mtpdevice_t *, uint32_t, uint32_t);
static void fake_release(LIBMTP_mtpdevice_t *);
static void fake_clear(LIBMTP_mtpdevice_t *);
static LIBMTP_error_t *fake_error(LIBMTP_mtpdevice_t *);
static int fake_partial(LIBMTP_mtpdevice_t *, uint32_t, uint64_t, uint32_t, unsigned char **, unsigned int *);
#define TERENTO_NATIVE_TEST_OPEN fake_open
#define LIBMTP_Get_Serialnumber fake_serial
#define LIBMTP_Get_Manufacturername fake_manufacturer
#define LIBMTP_Get_Modelname fake_model
#define LIBMTP_Get_Storage fake_storage
#define LIBMTP_Get_Files_And_Folders fake_files
#define LIBMTP_Release_Device fake_release
#define LIBMTP_Clear_Errorstack fake_clear
#define LIBMTP_Get_Errorstack fake_error
#define LIBMTP_GetPartialObject fake_partial
#include "../Sources/LibMTPBridge/MTPBridge.c"

static LIBMTP_mtpdevice_t device;
static LIBMTP_devicestorage_t storage;
static int scenario, reads, opens, closes;
static uint32_t ids[8];
void terento_prefix_test_reset(int value) {
    scenario=value; reads=opens=closes=0;
    memset(&device,0,sizeof(device)); memset(&storage,0,sizeof(storage));
    storage.id=1; device.storage=&storage;
}
int terento_prefix_test_reads(void) { return reads; }
static LIBMTP_mtpdevice_t *fake_open(uint16_t *v,uint16_t *p) {
    if(v)*v=0x091e; if(p)*p=0x51b8; ++opens; return &device;
}
static char *fake_serial(LIBMTP_mtpdevice_t *d) { return strdup(scenario==8?"OTHER-WATCH":"TEST-WATCH"); }
static char *fake_manufacturer(LIBMTP_mtpdevice_t *d) { return strdup("Garmin"); }
static char *fake_model(LIBMTP_mtpdevice_t *d) { return strdup("Test Watch"); }
static int fake_storage(LIBMTP_mtpdevice_t *d,int sort) { return 0; }
static void fake_release(LIBMTP_mtpdevice_t *d) { ++closes; }
static void fake_clear(LIBMTP_mtpdevice_t *d) {}
static LIBMTP_error_t *fake_error(LIBMTP_mtpdevice_t *d) { return NULL; }
static LIBMTP_file_t *entry(const char *name,uint32_t id,int folder,uint64_t size) {
    LIBMTP_file_t *f=LIBMTP_new_file_t(); assert(f); f->filename=strdup(name); f->item_id=id;
    f->parent_id=90; f->storage_id=1; f->filetype=folder?LIBMTP_FILETYPE_FOLDER:LIBMTP_FILETYPE_UNKNOWN;
    f->filesize=size; return f;
}
static LIBMTP_file_t *fake_files(LIBMTP_mtpdevice_t *d,uint32_t store,uint32_t parent) {
    if(parent==LIBMTP_FILES_AND_FOLDERS_ROOT) return entry("GARMIN",90,1,0);
    if(parent!=90) return NULL;
    LIBMTP_file_t *other=entry("unrelated.img",10,0,8);
    if(scenario==3) return other;
    LIBMTP_file_t *first=entry("expected.img",20,scenario==7,scenario==5?9:8);
    first->storage_id=scenario==6?2:1;
    other->next=first;
    first->next=entry("second.img",30,0,8);
    if(scenario==4) first->next->next=entry("expected.img",21,0,8);
    if(scenario==12 || scenario==14) other->item_id=20;
    if(scenario==13 || scenario==15) first->next->next=entry("EXPECTED.img",22,0,8);
    if(scenario==10) first->next->next=entry("second.img",31,0,9); /* ambiguous even with different size */
    return other;
}
static int fake_partial(LIBMTP_mtpdevice_t *d,uint32_t id,uint64_t offset,uint32_t length,unsigned char **out,unsigned int *count) {
    assert(reads<8); ids[reads++]=id;
    assert(id==20 || id==30 || id==10);
    *out=malloc(length); assert(*out); memset(*out,id==20?'A':id==30?'B':'X',length); *count=length; return 0;
}
static TerentoMTPMapOperationProfile profile(void) {
    return (TerentoMTPMapOperationProfile){2,0x091e,0x51b8,"Garmin","Test Watch","/GARMIN","TEST-WATCH",1,1};
}
#ifndef TERENTO_PREFIX_SWIFT_DRIVER
int main(void) {
    TerentoMTPMapOperationProfile p=profile();
    TerentoMTPFileDescriptor targets[2]={{1,8,0,"/GARMIN/expected.img","expected.img"},
        {1,8,0,"/GARMIN/second.img","second.img"}};
    for(int test=1;test<=15;++test) {
        terento_prefix_test_reset(test);
        TerentoMTPByteBuffer buffers[2]={{0}}; char error[256]={0}; int category=0;
        int batch=(test>=9 && test<=11) || test>=14;
        int result=batch ? terento_mtp_read_file_prefixes(&p,targets,2,8,buffers,error,sizeof(error))
            : terento_mtp_read_file_prefix_diagnostic(&p,targets,0,8,buffers,error,sizeof(error),&category);
        int success=test==1 || test==2 || test==9 || test==11;
        if ((result==0)!=success) fprintf(stderr,"scenario=%d result=%d error=%s category=%d\n",test,result,error,category);
        assert((result==0)==success);
        assert(opens==1 && closes==1);
        if(success) {
            // Historical expected ID was 10, now reused by unrelated.img. Never read it.
            assert(reads==(batch?2:1) && ids[0]==20 && buffers[0].bytes[0]=='A');
            if(batch) assert(ids[1]==30 && buffers[1].bytes[0]=='B');
        } else assert(reads==0 && buffers[0].byte_count==0 && buffers[1].byte_count==0);
        for(int i=0;i<2;++i)terento_mtp_free_byte_buffer(&buffers[i]);
        printf("PASS: prefix native scenario %d (reads=%d)\n",test,reads);
    }
    for(int i=0;i<3;++i) {
        const char *paths[]={"/GARMIN//expected.img","/GARMIN/./expected.img","/GARMIN/../expected.img"};
        terento_prefix_test_reset(1);
        TerentoMTPFileDescriptor invalid=targets[0]; invalid.path=paths[i];
        TerentoMTPByteBuffer buffer={0}; char text[256]={0};
        assert(terento_mtp_read_file_prefix(&p,&invalid,0,8,&buffer,text,sizeof(text))!=0 && reads==0 && opens==0);
    }
    terento_prefix_test_reset(8);
    TerentoMTPFileInventory inventory={0}; char error[256]={0}; int category=0;
    assert(terento_mtp_read_file_inventory_bound(&p,&inventory,error,sizeof(error),&category)!=0);
    assert(inventory.file_count==0 && reads==0 && opens==1 && closes==1);
    terento_prefix_test_reset(1);
    assert(terento_mtp_read_file_inventory_bound(&p,&inventory,error,sizeof(error),&category)==0);
    assert(inventory.file_count==4 && reads==0); terento_mtp_free_file_inventory(&inventory);
    puts("PASS: bound raw inventory validates the opened physical device");
    return 0;
}
#endif
