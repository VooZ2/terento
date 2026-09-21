/* Executes production native entrypoints with a synthetic libmtp backend. No USB. */
#include <libmtp.h>
#include <assert.h>
#include <sys/wait.h>
static LIBMTP_mtpdevice_t *fake_open(uint16_t *, uint16_t *);
static char *fake_serial(LIBMTP_mtpdevice_t *);
static char *fake_manufacturer(LIBMTP_mtpdevice_t *);
static char *fake_model(LIBMTP_mtpdevice_t *);
static int fake_storage(LIBMTP_mtpdevice_t *, int);
static LIBMTP_file_t *fake_files(LIBMTP_mtpdevice_t *, uint32_t, uint32_t);
static void fake_release(LIBMTP_mtpdevice_t *);
static void fake_clear(LIBMTP_mtpdevice_t *);
static LIBMTP_error_t *fake_error(LIBMTP_mtpdevice_t *);
static int fake_send(LIBMTP_mtpdevice_t *, const char *, LIBMTP_file_t *, LIBMTP_progressfunc_t, const void *);
static int fake_delete(LIBMTP_mtpdevice_t *, uint32_t);
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
#define LIBMTP_Send_File_From_File fake_send
#define LIBMTP_Delete_Object fake_delete
#define LIBMTP_GetPartialObject fake_partial
#include "../Sources/LibMTPBridge/MTPBridge.c"

static LIBMTP_mtpdevice_t device;
static LIBMTP_devicestorage_t storage;
static const char *serial = "TEST-SERIAL";
static int present, duplicate, folder, sends, deletes, substitute_after_read, send_failure;
static unsigned char content[131074];
static int track_reads, require_short_packets;
static uint32_t read_requests[8];
static size_t read_count;
static uint64_t read_total;
static const char *xml_fixture;
static const char *alias;
static const char *filename = "terento_test_map.img";
static char directory[] = "/private/tmp/terento-native-auth-XXXXXX";
static char claim[PATH_MAX], hash[65], source[PATH_MAX];
static unsigned operation;
static LIBMTP_mtpdevice_t *fake_open(uint16_t *v, uint16_t *p) { *v=0x091e; *p=0x51b8; return &device; }
static char *fake_serial(LIBMTP_mtpdevice_t *d) { return strdup(serial); }
static char *fake_manufacturer(LIBMTP_mtpdevice_t *d) { return strdup("Garmin"); }
static char *fake_model(LIBMTP_mtpdevice_t *d) { return strdup("Test Watch"); }
static int fake_storage(LIBMTP_mtpdevice_t *d, int sort) { return 0; }
static void fake_release(LIBMTP_mtpdevice_t *d) {}
static void fake_clear(LIBMTP_mtpdevice_t *d) {}
static LIBMTP_error_t *fake_error(LIBMTP_mtpdevice_t *d) { return NULL; }
static LIBMTP_file_t *entry(const char *name, uint32_t id, int is_folder, uint64_t size) {
    LIBMTP_file_t *f=LIBMTP_new_file_t(); f->filename=strdup(name); f->item_id=id;
    f->storage_id=1; f->filetype=is_folder?LIBMTP_FILETYPE_FOLDER:LIBMTP_FILETYPE_UNKNOWN; f->filesize=size; return f;
}
static LIBMTP_file_t *fake_files(LIBMTP_mtpdevice_t *d, uint32_t s, uint32_t parent) {
    if (parent==LIBMTP_FILES_AND_FOLDERS_ROOT) return entry("GARMIN",10,1,0);
    if (xml_fixture) return entry("GarminDevice.xml",88,0,strlen(xml_fixture));
    if (!present) return alias ? entry(alias,79,folder,512) : NULL;
    LIBMTP_file_t *f=entry(filename,substitute_after_read==2?78:77,folder,512);
    if (duplicate || alias) f->next=entry(alias ? alias : filename,79,folder,512);
    return f;
}
static int fake_send(LIBMTP_mtpdevice_t *d,const char *path,LIBMTP_file_t *f,LIBMTP_progressfunc_t progress,const void *ctx) {
    assert(f->storage_id==1 && f->parent_id==10 && !strcmp(f->filename,filename));
    ++sends; f->item_id=77; return send_failure;
}
static int fake_delete(LIBMTP_mtpdevice_t *d,uint32_t id) { assert(id==77); ++deletes; return 0; }
static int fake_partial(LIBMTP_mtpdevice_t *d,uint32_t id,uint64_t offset,uint32_t size,unsigned char **out,unsigned int *count) {
    if (track_reads) {
        assert(read_count < 8 && offset == read_total && size > 0 && size <= 65536);
        if (require_short_packets) assert(size % 2 == 1);
        read_requests[read_count++]=size;read_total+=size;
    }
    const unsigned char *data=xml_fixture?(const unsigned char *)xml_fixture:content;
    size_t length=xml_fixture?strlen(xml_fixture):sizeof(content);
    if (offset+size>length) return -1;
    *out=malloc(size); memcpy(*out,data+offset,size); *count=size;
    if(substitute_after_read==1) substitute_after_read=2;
    return 0;
}
static TerentoMTPMapOperationProfile profile(void) {
    return (TerentoMTPMapOperationProfile){2,0x091e,0x51b8,"Garmin","Test Watch","/GARMIN","TEST-SERIAL",1,1};
}
static TerentoMTPMutationAuthorization grant(uint32_t purpose,uint32_t kind) {
    static char id[64]; snprintf(id,sizeof(id),"test-%u",++operation);
    snprintf(claim,sizeof(claim),"%s/%s-1.claim",directory,id);
    return (TerentoMTPMutationAuthorization){1,id,claim,1,purpose,kind,filename,512,hash,
        "TEST-SERIAL",1,1,"/GARMIN"};
}
static int install(TerentoMTPMapOperationProfile *p,TerentoMTPMutationAuthorization *a,TerentoMTPMutationRecord *r) {
    char error[256]={0};uint32_t id=0;uint64_t size=0;
    return terento_mtp_install_map_file_authorized(p,a,r,source,filename,&id,&size,NULL,NULL,error,sizeof(error));
}
static int remove_map(TerentoMTPMapOperationProfile *p,TerentoMTPMutationAuthorization *a,TerentoMTPMutationRecord *r) {
    char error[256]={0};
    return terento_mtp_delete_external_map_authorized(p,a,r,filename,999,512,error,sizeof(error));
}
int main(void) {
    assert(mkdtemp(directory)); chmod(directory,0700);
    storage.id=1; device.storage=&storage;
    memcpy(content+0x10,"DSKIMG",6); memcpy(content+0x41,"GARMIN",6);
    unsigned char digest[32];CC_SHA256(content,512,digest);
    for(int i=0;i<32;++i)snprintf(hash+i*2,3,"%02x",digest[i]);
    snprintf(source,sizeof(source),"%s/source.img",directory);
    FILE *f=fopen(source,"wb");assert(f);assert(fwrite(content,1,512,f)==512);fclose(f);
    TerentoMTPMapOperationProfile p=profile(); TerentoMTPMutationRecord r;
    TerentoMTPMutationAuthorization a=grant(TERENTO_MUTATION_INSTALL,TERENTO_MUTATION_SEND);
    assert(install(&p,&a,&r)==0 && sends==1 && r.authorized && r.attempted && r.completed && r.resulting_object_id==77);
    assert(install(&p,&a,&r)!=0 && sends==1); /* in-process replay */
    pid_t child=fork();assert(child>=0);
    if(!child){terento_consumed_count=0;_exit(install(&p,&a,&r)!=0 && sends==1?0:1);}
    int status;waitpid(child,&status,0);assert(WIFEXITED(status)&&WEXITSTATUS(status)==0);
    a=grant(1,1);a.claim_path=NULL;assert(install(&p,&a,&r)!=0&&sends==1);
    a=grant(1,1);assert(install(&p,&a,NULL)!=0&&sends==1);
    a=grant(1,1);a.sequence=0;assert(install(&p,&a,&r)!=0&&sends==1);
    a=grant(1,2);assert(install(&p,&a,&r)!=0&&sends==1);
    a=grant(1,1);chmod(directory,0755);assert(install(&p,&a,&r)!=0&&sends==1);chmod(directory,0700);

    a=grant(1,1);serial="OTHER";assert(install(&p,&a,&r)!=0&&sends==1);serial="TEST-SERIAL";
    /* A valid unused grant for A cannot be rebound by swapping both profile and live device. */
    a=grant(1,1);serial="OTHER";p.physical_identifier="OTHER";
    assert(install(&p,&a,&r)!=0&&sends==1&&!r.attempted);serial="TEST-SERIAL";p=profile();
    a=grant(1,1);storage.id=2;p.expected_storage_id=2;
    assert(install(&p,&a,&r)!=0&&sends==1&&!r.attempted);storage.id=1;p=profile();
    a=grant(1,1);a.expected_target_directory="/OTHER";
    assert(install(&p,&a,&r)!=0&&sends==1&&!r.attempted);

    a=grant(1,1);p.expected_storage_id=2;assert(install(&p,&a,&r)!=0&&sends==1);p=profile();
    a=grant(1,1);a.expected_filename="terento_wrong.img";assert(install(&p,&a,&r)!=0&&sends==1);
    a=grant(1,1);a.expected_size=513;assert(install(&p,&a,&r)!=0&&sends==1);
    a=grant(5,1);assert(install(&p,&a,&r)!=0&&sends==1);
    alias="TERENTO_TEST_MAP.IMG";
    a=grant(1,1);assert(install(&p,&a,&r)!=0&&sends==1&&!r.attempted);
    folder=1;a=grant(1,1);assert(install(&p,&a,&r)!=0&&sends==1&&!r.attempted);folder=0;alias=NULL;
    a=grant(1,1);present=1;assert(install(&p,&a,&r)==TERENTO_MTP_MAP_TARGET_EXISTS&&sends==1);
    duplicate=1;a=grant(1,1);assert(install(&p,&a,&r)!=0&&sends==1);duplicate=0;
    folder=1;a=grant(1,1);assert(install(&p,&a,&r)!=0&&sends==1);folder=0;
    a=grant(5,2);serial="OTHER";p.physical_identifier="OTHER";
    assert(remove_map(&p,&a,&r)!=0&&deletes==0&&!r.attempted);serial="TEST-SERIAL";p=profile();
    alias="TERENTO_TEST_MAP.IMG";
    a=grant(5,2);assert(remove_map(&p,&a,&r)!=0&&deletes==0&&!r.attempted);alias=NULL;
    a=grant(5,2);assert(remove_map(&p,&a,&r)==0&&deletes==1&&r.attempted);
    assert(remove_map(&p,&a,&r)!=0&&deletes==1);
    a=grant(6,2);assert(remove_map(&p,&a,&r)!=0&&deletes==1);
    a=grant(5,2);content[200]=1;assert(remove_map(&p,&a,&r)!=0&&deletes==1);content[200]=0;
    a=grant(5,2);substitute_after_read=1;assert(remove_map(&p,&a,&r)!=0&&deletes==1);substitute_after_read=0;
    a=grant(5,2);duplicate=1;assert(remove_map(&p,&a,&r)!=0&&deletes==1);duplicate=0;
    a=grant(5,2);a.expected_sha256="0000000000000000000000000000000000000000000000000000000000000000";
    assert(remove_map(&p,&a,&r)!=0&&deletes==1);
    a=grant(5,2);filename="D123.img";a.expected_filename=filename;assert(remove_map(&p,&a,&r)!=0&&deletes==1);filename="terento_test_map.img";
    p.physical_identifier_source=2;p.physical_identifier="12345";
    xml_fixture="<GarminDevice><Id>12345</Id></GarminDevice>";assert(physical_identifier_matches(&p,&device));
    xml_fixture="<GarminDevice><Id>12345</Id><Id>12345</Id></GarminDevice>";assert(!physical_identifier_matches(&p,&device));
    xml_fixture="<Device><Id>12345</Id></Device>";assert(!physical_identifier_matches(&p,&device));
    xml_fixture="<GarminDevice><Other><Id>12345</Id></Other></GarminDevice>";assert(!physical_identifier_matches(&p,&device));
    xml_fixture="<!DOCTYPE GarminDevice><GarminDevice><Id>12345</Id></GarminDevice>";assert(!physical_identifier_matches(&p,&device));
    xml_fixture=NULL;
    p=profile();present=0;a=grant(1,1);send_failure=-123;
    assert(install(&p,&a,&r)!=0 && sends==2 && r.attempted && r.completed && r.native_result==-123);
    assert(install(&p,&a,&r)!=0 && sends==2);send_failure=0;
    char error[128];
    a=grant(6,2);assert(terento_mtp_delete_managed_map_authorized(&p,&a,&r,filename,77,512,error,sizeof(error))==TERENTO_MTP_MUTATION_REFUSED&&deletes==1);
assert(terento_mtp_delete_managed_map(&p,filename,77,512,error,sizeof(error))==TERENTO_MTP_MUTATION_REFUSED);
    assert(terento_mtp_write_test_file(source,NULL,NULL,error,sizeof(error))==TERENTO_MTP_MUTATION_REFUSED);
    a=grant(TERENTO_MUTATION_UPDATE_NEW,TERENTO_MUTATION_SEND);
    assert(install(&p,&a,&r)==0 && sends==3);
    char operation_id[65];strcpy(operation_id,a.operation_id);
    a.operation_id=operation_id;a.sequence=2;a.purpose=TERENTO_MUTATION_UPDATE_OLD;a.mutation_kind=TERENTO_MUTATION_DELETE;
    snprintf(claim,sizeof(claim),"%s/%s-2.claim",directory,operation_id);present=1;
    assert(terento_mtp_delete_managed_map_authorized(&p,&a,&r,filename,999,512,error,sizeof(error))!=0&&deletes==1);
    char marker[PATH_MAX];snprintf(marker,sizeof(marker),"%s/%s-verified-new",directory,operation_id);
    int marker_fd=open(marker,O_WRONLY|O_CREAT|O_EXCL,0600);assert(marker_fd>=0);
    assert(write(marker_fd,operation_id,strlen(operation_id))==(ssize_t)strlen(operation_id));assert(fsync(marker_fd)==0);close(marker_fd);
    assert(terento_mtp_delete_managed_map_authorized(&p,&a,&r,filename,999,512,error,sizeof(error))==0&&deletes==2);
    assert(terento_mtp_delete_managed_map_authorized(&p,&a,&r,filename,999,512,error,sizeof(error))!=0&&deletes==2);
    /* Fullhash uses the existing short-packet policy without dropping remainder bytes. */
    for(size_t i=512;i<sizeof(content);++i)content[i]=(unsigned char)(i%251);
    char segment_hash[65];
    CC_SHA256(content,(CC_LONG)sizeof(content),digest);
    for(int i=0;i<32;++i)snprintf(segment_hash+i*2,3,"%02x",digest[i]);
    track_reads=1;require_short_packets=1;read_count=0;read_total=0;
    p=profile();
    assert(verify_deletion_content(&device,&p,77,sizeof(content),segment_hash));
    assert(read_total==sizeof(content)&&read_count==4&&read_requests[0]==65535
        &&read_requests[1]==65535&&read_requests[2]==3&&read_requests[3]==1);
    content[sizeof(content)-1]^=1;read_count=0;read_total=0;
    assert(!verify_deletion_content(&device,&p,77,sizeof(content),segment_hash));
    assert(read_total==sizeof(content));content[sizeof(content)-1]^=1;
    p.product_id=0x51b9;require_short_packets=0;read_count=0;read_total=0;
    assert(verify_deletion_content(&device,&p,77,sizeof(content),segment_hash));
    assert(read_total==sizeof(content)&&read_count==3&&read_requests[0]==65536
        &&read_requests[1]==65536&&read_requests[2]==2);
    track_reads=0;
    puts("PASS: native mutation authorization (real entrypoints, fake libmtp, no USB)");
    return 0;
}
