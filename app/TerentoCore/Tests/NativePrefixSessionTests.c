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
static int scenario, reads, opens, closes, listings, music_listings, fail_next_activity;
static uint32_t ids[8];
void terento_prefix_test_reset(int value) {
    scenario=value; reads=opens=closes=listings=music_listings=0; fail_next_activity=value==22;
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
static void fake_clear_error(void);
static void fake_clear(LIBMTP_mtpdevice_t *d) { fake_clear_error(); }
static int error_pending;
static LIBMTP_error_t scoped_error={LIBMTP_ERROR_GENERAL,"Synthetic listing failure",NULL};
static void fake_clear_error(void) { error_pending=0; }
static LIBMTP_error_t *fake_error(LIBMTP_mtpdevice_t *d) { return error_pending ? &scoped_error : NULL; }
static LIBMTP_file_t *entry(const char *name,uint32_t id,int folder,uint64_t size) {
    LIBMTP_file_t *f=LIBMTP_new_file_t(); assert(f); f->filename=strdup(name); f->item_id=id;
    f->parent_id=90; f->storage_id=1; f->filetype=folder?LIBMTP_FILETYPE_FOLDER:LIBMTP_FILETYPE_UNKNOWN;
    f->filesize=size; return f;
}
/* Scenario 18: a heavy watch with years of activities and a music library,
 * including two music objects listed under one name. */
static LIBMTP_file_t *heavy_files(uint32_t parent) {
    LIBMTP_file_t *head=NULL, **tail=&head;
    char name[64];
    if(parent==LIBMTP_FILES_AND_FOLDERS_ROOT) {
        *tail=entry("GARMIN",90,1,0); tail=&(*tail)->next;
        *tail=entry("Music",91,1,0); return head;
    }
    if(parent==90) return entry("Activity",92,1,0);
    if(parent==92) {
        for(int i=0;i<6000;++i) { snprintf(name,sizeof(name),"%d.fit",i);
            *tail=entry(name,1000+i,0,1000+i); tail=&(*tail)->next; }
        return head;
    }
    if(parent==91) {
        for(int i=0;i<6000;++i) { snprintf(name,sizeof(name),"track-%d.mp3",i);
            *tail=entry(name,10000+i,0,3000000+i); tail=&(*tail)->next; }
        *tail=entry("dup.mp3",20000,0,5000); tail=&(*tail)->next;
        *tail=entry("dup.mp3",20001,0,5000);
        return head;
    }
    return NULL;
}
/* Scenarios 19-23: a heavy watch whose bulk (12,000 music tracks) is outside
 * /GARMIN, a map-like file at the storage root and maps inside /GARMIN.
 * 20: a second case-alias root; 21: no root; 22: one failed scoped listing;
 * 23: a root-level file named like the root next to the root folder. */
static LIBMTP_file_t *scoped_files(uint32_t parent) {
    LIBMTP_file_t *head=NULL, **tail=&head;
    char name[64];
    if(parent==LIBMTP_FILES_AND_FOLDERS_ROOT) {
        if(scenario!=21) { *tail=entry("GARMIN",90,1,0); tail=&(*tail)->next; }
        if(scenario==20) { *tail=entry("Garmin",89,1,0); tail=&(*tail)->next; }
        if(scenario==23) { *tail=entry("garmin",88,0,4); tail=&(*tail)->next; }
        *tail=entry("Music",91,1,0); tail=&(*tail)->next;
        *tail=entry("rootmap.img",95,0,4096);
        return head;
    }
    if(parent==90) {
        *tail=entry("Activity",92,1,0); tail=&(*tail)->next;
        *tail=entry("terento_a.img",96,0,8192);
        return head;
    }
    if(parent==89) return entry("other.img",97,0,16);
    if(parent==92) {
        if(fail_next_activity) { fail_next_activity=0; error_pending=1; return NULL; }
        for(int i=0;i<50;++i) { snprintf(name,sizeof(name),"%d.fit",i);
            *tail=entry(name,1000+i,0,1000+i); tail=&(*tail)->next; }
        return head;
    }
    if(parent==91) {
        ++music_listings;
        for(int i=0;i<12000;++i) { snprintf(name,sizeof(name),"track-%d.mp3",i);
            *tail=entry(name,10000+i,0,3000000+i); tail=&(*tail)->next; }
        return head;
    }
    return NULL;
}
static LIBMTP_file_t *fake_files(LIBMTP_mtpdevice_t *d,uint32_t store,uint32_t parent) {
    ++listings;
    if(scenario==18) return heavy_files(parent);
    if(scenario>=19 && scenario<=23) return scoped_files(parent);
    if(parent==LIBMTP_FILES_AND_FOLDERS_ROOT) return entry(scenario==16?"Garmin":scenario==17?"garmin":"GARMIN",90,1,0);
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
static void test_root_projection(void) {
    for (int variant=0; variant<6; ++variant) {
        TerentoMTPFileInventory inv={0};
        inv.file_count=4; inv.files=calloc(inv.file_count,sizeof(*inv.files));
        const char *paths[]={"/Garmin","/Garmin/MyMap.IMG","/GarminElse/keep.img","/Garmin/other-store.img"};
        const char *names[]={"Garmin","MyMap.IMG","keep.img","other-store.img"};
        for(size_t i=0;i<inv.file_count;++i) {
            inv.files[i]=(TerentoMTPFile){0}; inv.files[i].item_id=i+10;
            inv.files[i].storage_id=i==3?2:1; inv.files[i].is_folder=i==0;
            inv.files[i].path=strdup(paths[i]); inv.files[i].filename=strdup(names[i]);
        }
        if(variant==1) inv.files[0].storage_id=0;
        if(variant==2) inv.files[0].item_id=0;
        if(variant==3 || variant==4) { // a second root: same or different storage
            free(inv.files[3].path); free(inv.files[3].filename);
            inv.files[3].path=strdup("/GARMIN"); inv.files[3].filename=strdup("GARMIN");
            inv.files[3].is_folder=1; inv.files[3].storage_id=variant==3?1:2;
        }
        if(variant==5) inv.files[0].is_folder=0;
        canonicalize_garmin_inventory_root(&inv);
        assert(!strcmp(inv.files[1].path,variant==0?"/GARMIN/MyMap.IMG":"/Garmin/MyMap.IMG"));
        assert(!strcmp(inv.files[0].filename,"Garmin"));
        assert(!strcmp(inv.files[1].filename,"MyMap.IMG"));
        assert(!strcmp(inv.files[2].path,"/GarminElse/keep.img"));
        if(variant!=3 && variant!=4) assert(!strcmp(inv.files[3].path,"/Garmin/other-store.img"));
        clear_file_inventory(&inv);
    }
    puts("PASS: native root projection is storage-bound, preserves suffix case and refuses ambiguity/invalid roots");
}

static int has_path(const TerentoMTPFileInventory *inv,const char *path) {
    for(size_t i=0;i<inv->file_count;++i) if(!strcmp(inv->files[i].path,path)) return 1;
    return 0;
}
static void test_map_scope_inventory(const TerentoMTPMapOperationProfile *p) {
    TerentoMTPFileInventory inv={0}; char error[256]={0}; int category=0, scope=-1, fallback=-1;
    /* Full walk of the heavy watch: every music track is listed. */
    terento_prefix_test_reset(19);
    assert(terento_mtp_read_file_inventory_bound(p,&inv,error,sizeof(error),&category)==0);
    size_t full_count=inv.file_count;
    assert(full_count==12055 && music_listings==1);
    terento_mtp_free_file_inventory(&inv);
    /* Scoped walk: root entries + the GARMIN subtree only; Music is never listed. */
    terento_prefix_test_reset(19);
    assert(terento_mtp_read_map_scope_inventory_bound(p,&inv,&scope,&fallback,error,sizeof(error),&category)==0);
    assert(scope==TERENTO_INVENTORY_SCOPE_GARMIN && fallback==TERENTO_INVENTORY_FALLBACK_NONE);
    assert(inv.file_count==55 && music_listings==0 && listings==3 && opens==1 && closes==1 && reads==0);
    assert(has_path(&inv,"/rootmap.img") && has_path(&inv,"/Music") && has_path(&inv,"/GARMIN/terento_a.img")
        && has_path(&inv,"/GARMIN/Activity/49.fit") && !has_path(&inv,"/Music/track-0.mp3"));
    terento_mtp_free_file_inventory(&inv);
    printf("PASS: map-scope inventory visits 55 of %zu objects, keeps the storage-root map and skips music\n",full_count);
    /* Missing, ambiguous or failed scope answers with the full walk in the same session. */
    int cases[][3]={{20,TERENTO_INVENTORY_FALLBACK_AMBIGUOUS_ROOT,12057},{21,TERENTO_INVENTORY_FALLBACK_NO_ROOT,12002},
        {22,TERENTO_INVENTORY_FALLBACK_SCOPED_FAILED,12055},{23,TERENTO_INVENTORY_FALLBACK_AMBIGUOUS_ROOT,12056}};
    for(size_t i=0;i<sizeof(cases)/sizeof(cases[0]);++i) {
        terento_prefix_test_reset(cases[i][0]); scope=fallback=-1; error[0]=0;
        int rc=terento_mtp_read_map_scope_inventory_bound(p,&inv,&scope,&fallback,error,sizeof(error),&category);
        if(rc!=0 || (int)inv.file_count!=cases[i][2]) fprintf(stderr,"scenario=%d rc=%d count=%zu fallback=%d\n",cases[i][0],rc,inv.file_count,fallback);
        assert(rc==0 && scope==TERENTO_INVENTORY_SCOPE_FULL && fallback==cases[i][1]);
        assert((int)inv.file_count==cases[i][2] && music_listings==1 && opens==1 && closes==1 && error[0]==0);
        assert(has_path(&inv,"/Music/track-11999.mp3"));
        terento_mtp_free_file_inventory(&inv);
        printf("PASS: map-scope fallback scenario %d returns the full walk (fallback=%d)\n",cases[i][0],fallback);
    }
    /* A wrong physical device is refused before any listing, as for the full read. */
    terento_prefix_test_reset(8); scope=fallback=-1;
    assert(terento_mtp_read_map_scope_inventory_bound(p,&inv,&scope,&fallback,error,sizeof(error),&category)!=0);
    assert(inv.file_count==0 && listings==0 && scope==TERENTO_INVENTORY_SCOPE_FULL);
    puts("PASS: map-scope inventory validates the opened physical device");
}

#ifndef TERENTO_PREFIX_SWIFT_DRIVER
int main(void) {
    test_root_projection();
    TerentoMTPMapOperationProfile p=profile();
    TerentoMTPFileDescriptor targets[2]={{1,8,0,"/GARMIN/expected.img","expected.img"},
        {1,8,0,"/GARMIN/second.img","second.img"}};
    for(int test=1;test<=17;++test) {
        terento_prefix_test_reset(test);
        TerentoMTPByteBuffer buffers[2]={{0}}; char error[256]={0}; int category=0;
        int batch=(test>=9 && test<=11) || (test>=14 && test<=15);
        int result=batch ? terento_mtp_read_file_prefixes(&p,targets,2,8,buffers,error,sizeof(error))
            : terento_mtp_read_file_prefix_diagnostic(&p,targets,0,8,buffers,error,sizeof(error),&category);
        int success=test==1 || test==2 || test==9 || test==11 || test==16 || test==17;
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
    terento_prefix_test_reset(18);
    assert(terento_mtp_read_file_inventory_bound(&p,&inventory,error,sizeof(error),&category)==0);
    assert(inventory.file_count==12005 && reads==0 && opens==1 && closes==1);
    size_t duplicates=0, activities=0;
    for(size_t i=0;i<inventory.file_count;++i) {
        if(!strcmp(inventory.files[i].path,"/Music/dup.mp3")) ++duplicates;
        if(!strncmp(inventory.files[i].path,"/GARMIN/Activity/",17)) ++activities;
    }
    assert(duplicates==2 && activities==6000);
    terento_mtp_free_file_inventory(&inventory);
    puts("PASS: heavy-watch inventory walks 12,005 objects and surfaces duplicate music entries unchanged");
    test_map_scope_inventory(&p);
    return 0;
}
#endif
