/* Safe Update content checks: the production native entrypoints used by an
 * update of a Terento-managed map, with a synthetic libmtp backend serving a
 * virtual old and new map object. Measures the bytes read over MTP for a
 * 434 MB update with the full checks and with the recorded/sampled checks.
 * No USB, no real map bytes. */
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
static int fake_send(LIBMTP_mtpdevice_t *, const char *, LIBMTP_file_t *, LIBMTP_progressfunc_t, const void *);
static int fake_delete(LIBMTP_mtpdevice_t *, uint32_t);
static int fake_partial(LIBMTP_mtpdevice_t *, uint32_t, uint64_t, uint32_t, unsigned char **, unsigned int *);
static int fake_get_file(LIBMTP_mtpdevice_t *, uint32_t, const char *, LIBMTP_progressfunc_t, const void *);
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
#define LIBMTP_Get_File_To_File fake_get_file
#include "../Sources/LibMTPBridge/MTPBridge.c"

#define L TERENTO_REMOVAL_PROOF_REGION_LENGTH
#define N TERENTO_REMOVAL_PROOF_REGION_COUNT
#define OLD_ID 77u
#define NEW_ID 88u
#define INSTALL_SAMPLE_LENGTH (4u * 1024u * 1024u)
static LIBMTP_mtpdevice_t device;
static LIBMTP_devicestorage_t storage;
static const char *old_name = "terento_test_map_2026-04.img";
static const char *new_name = "terento_test_map_2026-10.img";
static uint64_t object_size, observed_old_size;
static int old_present, new_present, duplicate_old, substitute_after_read, sends, deletes;
static uint64_t flip_old = UINT64_MAX, flip_new = UINT64_MAX, fail_offset = UINT64_MAX;
static uint64_t bytes_read, read_requests, full_reads, progress_total, progress_done;
static char directory[] = "/private/tmp/terento-fast-update-XXXXXX";
static char claim[PATH_MAX];
static unsigned operation;

/* Deterministic virtual content: a valid IMG header, then salted bytes. */
static unsigned char content_byte(uint64_t offset, unsigned salt) {
    if (offset < 0x48) {
        if (offset >= 0x10 && offset < 0x16) return (unsigned char)"DSKIMG"[offset - 0x10];
        if (offset >= 0x41 && offset < 0x47) return (unsigned char)"GARMIN"[offset - 0x41];
        return 0;
    }
    return (unsigned char)((((offset * 2654435761u) >> 13) ^ (offset >> 20)) + salt);
}
static unsigned char live_byte(uint32_t id, uint64_t offset) {
    if (id == OLD_ID) return (unsigned char)(content_byte(offset, 0) ^ (offset == flip_old ? 1 : 0));
    return (unsigned char)(content_byte(offset, 0x5a) ^ (offset == flip_new ? 1 : 0));
}

static LIBMTP_mtpdevice_t *fake_open(uint16_t *v, uint16_t *p) { *v=0x091e; *p=0x51b8; return &device; }
static char *fake_serial(LIBMTP_mtpdevice_t *d) { (void)d; return strdup("TEST-SERIAL"); }
static char *fake_manufacturer(LIBMTP_mtpdevice_t *d) { (void)d; return strdup("Garmin"); }
static char *fake_model(LIBMTP_mtpdevice_t *d) { (void)d; return strdup("Test Watch"); }
static int fake_storage(LIBMTP_mtpdevice_t *d, int sort) { (void)d; (void)sort; return 0; }
static void fake_release(LIBMTP_mtpdevice_t *d) { (void)d; }
static void fake_clear(LIBMTP_mtpdevice_t *d) { (void)d; }
static LIBMTP_error_t *fake_error(LIBMTP_mtpdevice_t *d) { (void)d; return NULL; }
static LIBMTP_file_t *entry(const char *name, uint32_t id, int is_folder, uint64_t size) {
    LIBMTP_file_t *f=LIBMTP_new_file_t(); f->filename=strdup(name); f->item_id=id; f->parent_id=is_folder?0:10;
    f->storage_id=1; f->filetype=is_folder?LIBMTP_FILETYPE_FOLDER:LIBMTP_FILETYPE_UNKNOWN; f->filesize=size; return f;
}
static LIBMTP_file_t *fake_files(LIBMTP_mtpdevice_t *d, uint32_t s, uint32_t parent) {
    (void)d; (void)s;
    if (parent==LIBMTP_FILES_AND_FOLDERS_ROOT) return entry("GARMIN",10,1,0);
    if (parent!=10) return NULL;
    LIBMTP_file_t *head=NULL, **tail=&head;
    if (old_present) { *tail=entry(old_name,substitute_after_read==2?OLD_ID+1:OLD_ID,0,observed_old_size); tail=&(*tail)->next; }
    if (duplicate_old) { *tail=entry(old_name,OLD_ID+2,0,observed_old_size); tail=&(*tail)->next; }
    if (new_present) { *tail=entry(new_name,NEW_ID,0,object_size); tail=&(*tail)->next; }
    return head;
}
static int fake_send(LIBMTP_mtpdevice_t *d,const char *path,LIBMTP_file_t *f,LIBMTP_progressfunc_t p,const void *c) {
    (void)d; (void)path; (void)f; (void)p; (void)c; ++sends; return -1;
}
static int fake_delete(LIBMTP_mtpdevice_t *d,uint32_t id) { (void)d; assert(id==OLD_ID); ++deletes; old_present=0; return 0; }
static int fake_partial(LIBMTP_mtpdevice_t *d,uint32_t id,uint64_t offset,uint32_t size,unsigned char **out,unsigned int *count) {
    (void)d; assert((id==OLD_ID || id==NEW_ID) && size>0 && size<=65536);
    if (offset+size>object_size) return -1;
    if (fail_offset>=offset && fail_offset<offset+size) return -1;
    *out=malloc(size); assert(*out);
    for (uint32_t i=0;i<size;++i) (*out)[i]=live_byte(id,offset+i);
    *count=size; bytes_read+=size; ++read_requests;
    if (substitute_after_read==1) substitute_after_read=2;
    return 0;
}
/* A whole-object read: accounted as object_size bytes (sparse local file). */
static int fake_get_file(LIBMTP_mtpdevice_t *d,uint32_t id,const char *path,LIBMTP_progressfunc_t p,const void *c) {
    (void)d; assert(id==OLD_ID || id==NEW_ID);
    int fd=open(path,O_WRONLY|O_CREAT|O_EXCL,0600); assert(fd>=0);
    assert(ftruncate(fd,(off_t)object_size)==0); close(fd);
    bytes_read+=object_size; ++read_requests; ++full_reads;
    if (p) p(object_size,object_size,c);
    return 0;
}
static int progress(uint64_t done, uint64_t total, const void *context) {
    (void)context; assert(done<=total && done>=progress_done); progress_done=done; progress_total=total; return 0;
}
static TerentoMTPMapOperationProfile profile(void) {
    return (TerentoMTPMapOperationProfile){2,0x091e,0x51b8,"Garmin","Test Watch","/GARMIN","TEST-SERIAL",1,1};
}

static char old_hash[65], sample_hash[65], new_hash[65];
static uint64_t plan[N];
static void hex(const unsigned char *digest, char *out) {
    for (int i=0;i<32;++i) snprintf(out+i*2,3,"%02x",digest[i]);
}
static void hash_full(uint64_t size, unsigned salt, char *out) {
    CC_SHA256_CTX c; CC_SHA256_Init(&c); unsigned char chunk[65536];
    for (uint64_t o=0;o<size;) { uint32_t n=(uint32_t)(size-o>sizeof(chunk)?sizeof(chunk):size-o);
        for (uint32_t i=0;i<n;++i) chunk[i]=content_byte(o+i,salt); CC_SHA256_Update(&c,chunk,n); o+=n; }
    unsigned char d[32]; CC_SHA256_Final(d,&c); hex(d,out);
}
/* The format-1 plan of ManagedRemovalProof.plan, and its digest. */
static void record_proof(uint64_t size, const char *file_hash) {
    uint64_t seed=0xcbf29ce484222325ull;
    for (const char *c=file_hash;*c;++c) { seed^=(unsigned char)*c; seed*=0x100000001b3ull; }
    uint64_t width=(size-2*(uint64_t)L)/(N-2);
    plan[0]=0;
    for (uint32_t i=0;i<N-2;++i) { seed=seed*2862933555777941757ull+3037000493ull; plan[i+1]=L+i*width+seed%(width-L+1); }
    plan[N-1]=size-L;
    CC_SHA256_CTX c; CC_SHA256_Init(&c);
    for (uint32_t r=0;r<N;++r) for (uint64_t o=plan[r];o<plan[r]+L;++o) { unsigned char b=content_byte(o,0); CC_SHA256_Update(&c,&b,1); }
    unsigned char d[32]; CC_SHA256_Final(d,&c); hex(d,sample_hash);
}
/* The install read-back plan of MapInstallationCoordinator.verificationSampleOffsets. */
static size_t install_plan(uint64_t size, const char *file_hash, uint64_t *offsets) {
    uint64_t max=size-INSTALL_SAMPLE_LENGTH, seed=0xcbf29ce484222325ull; size_t n=0;
    for (const char *c=file_hash;*c;++c) { seed^=(unsigned char)*c; seed*=0x100000001b3ull; }
    offsets[n++]=0; offsets[n++]=max;
    for (int i=0;i<5;++i) { seed=seed*2862933555777941757ull+3037000493ull; uint64_t o=seed%(max+1);
        int seen=0; for (size_t k=0;k<n;++k) seen|=offsets[k]==o; if (!seen) offsets[n++]=o; }
    for (size_t i=1;i<n;++i) for (size_t k=i;k>0 && offsets[k-1]>offsets[k];--k) { uint64_t t=offsets[k]; offsets[k]=offsets[k-1]; offsets[k-1]=t; }
    return n;
}
/* The validated local artifact of the new map: sparse, with the real bytes in
 * every region the install read-back compares. */
static char source_path[PATH_MAX];
static void write_source(uint64_t size, const uint64_t *offsets, size_t count) {
    snprintf(source_path,sizeof(source_path),"%s/new.img",directory);
    int fd=open(source_path,O_WRONLY|O_CREAT|O_TRUNC,0600); assert(fd>=0);
    assert(ftruncate(fd,(off_t)size)==0);
    unsigned char *buffer=malloc(INSTALL_SAMPLE_LENGTH); assert(buffer);
    for (size_t r=0;r<count;++r) {
        for (uint32_t i=0;i<INSTALL_SAMPLE_LENGTH;++i) buffer[i]=content_byte(offsets[r]+i,0x5a);
        assert(pwrite(fd,buffer,INSTALL_SAMPLE_LENGTH,(off_t)offsets[r])==(ssize_t)INSTALL_SAMPLE_LENGTH);
    }
    free(buffer); close(fd);
}
static void reset(uint64_t size) {
    object_size=observed_old_size=size; old_present=1; new_present=1; duplicate_old=substitute_after_read=0;
    flip_old=flip_new=fail_offset=UINT64_MAX; bytes_read=read_requests=full_reads=progress_total=progress_done=0;
}
static TerentoMTPMutationAuthorization grant_update_old(uint64_t size, int with_proof) {
    static char id[64]; snprintf(id,sizeof(id),"update-%u",++operation);
    snprintf(claim,sizeof(claim),"%s/%s-2.claim",directory,id);
    char path[PATH_MAX], text[160]; int fd; /* same-operation verified new map */
    snprintf(path,sizeof(path),"%s/%s-1.claim",directory,id); snprintf(text,sizeof(text),"%s-1.claim|2|1",id);
    fd=open(path,O_WRONLY|O_CREAT|O_EXCL,0600); assert(fd>=0); assert(write(fd,text,strlen(text))==(ssize_t)strlen(text)); close(fd);
    snprintf(path,sizeof(path),"%s/%s-verified-new",directory,id);
    fd=open(path,O_WRONLY|O_CREAT|O_EXCL,0600); assert(fd>=0); assert(write(fd,id,strlen(id))==(ssize_t)strlen(id)); close(fd);
    TerentoMTPMutationAuthorization a={1,id,claim,2,TERENTO_MUTATION_UPDATE_OLD,TERENTO_MUTATION_DELETE,old_name,size,old_hash,
        "TEST-SERIAL",1,1,"/GARMIN",NULL,0,0,NULL};
    if (with_proof) { a.removal_sample_offsets=plan; a.removal_sample_count=N;
        a.removal_sample_length=L; a.removal_sample_sha256=sample_hash; }
    return a;
}
static int proof_check(uint64_t size, const uint64_t *offsets, uint32_t count, uint32_t length,
                       const char *file_hash, const char *digest, uint32_t *resolved, uint64_t *sampled) {
    TerentoMTPMapOperationProfile p=profile(); char error[256]={0};
    return terento_mtp_verify_managed_map_proof(&p,old_name,size,file_hash,offsets,count,length,digest,
        resolved,sampled,progress,NULL,error,sizeof(error));
}
static int full_read(const char *name, uint64_t size) {
    TerentoMTPMapOperationProfile p=profile(); char error[256]={0}, path[PATH_MAX], remote[300];
    snprintf(path,sizeof(path),"%s/read-%u.img",directory,++operation); snprintf(remote,sizeof(remote),"/GARMIN/%s",name);
    uint32_t resolved=0; uint64_t read_size=0;
    int result=terento_mtp_read_existing_file_to_local(&p,999,remote,size,path,&resolved,&read_size,progress,NULL,error,sizeof(error));
    unlink(path); return result;
}
static int install_readback(uint64_t size, const uint64_t *offsets, size_t count, uint64_t *sampled) {
    TerentoMTPMapOperationProfile p=profile(); char error[256]={0}; uint32_t resolved=0, matched=0;
    return terento_mtp_verify_managed_map_samples(&p,source_path,new_name,NEW_ID,size,&resolved,offsets,count,
        INSTALL_SAMPLE_LENGTH,sampled,&matched,progress,NULL,error,sizeof(error));
}
static int delete_old(uint64_t size, int with_proof) {
    TerentoMTPMapOperationProfile p=profile(); char error[256]={0}; TerentoMTPMutationRecord r;
    TerentoMTPMutationAuthorization a=grant_update_old(size,with_proof);
    return terento_mtp_delete_managed_map_authorized(&p,&a,&r,old_name,999,size,progress,NULL,error,sizeof(error));
}
static void refused(const char *scenario, int result, int expected) {
    assert(result!=0 && (expected==0 || result==expected) && sends==0 && deletes==0);
    printf("PASS: current-map check blocked: %s | result=%d bytes_read=%llu\n",scenario,result,(unsigned long long)bytes_read);
}

int main(void) {
    assert(mkdtemp(directory)); chmod(directory,0700);
    storage.id=1; device.storage=&storage;
    const uint64_t size=434000000ull; /* a 434 MB managed map */
    hash_full(size,0,old_hash); hash_full(size,0x5a,new_hash); record_proof(size,old_hash);
    uint64_t install_offsets[7]; size_t install_count=install_plan(size,new_hash,install_offsets);
    write_source(size,install_offsets,install_count);
    uint64_t install_bytes=(uint64_t)install_count*INSTALL_SAMPLE_LENGTH;

    /* Before: full read of the installed map, full read-back of the new map,
     * then the sampled old-map removal. */
    reset(size);
    assert(full_read(old_name,size)==0); uint64_t before_current=bytes_read;
    progress_done=0; assert(full_read(new_name,size)==0); uint64_t before_new=bytes_read-before_current;
    uint64_t mark=bytes_read; progress_done=0; assert(delete_old(size,1)==0 && deletes==1); uint64_t before_delete=bytes_read-mark;
    uint64_t before_total=bytes_read;
    assert(before_current==size && before_new==size && before_delete==(uint64_t)N*L);
    deletes=0;

    /* After: recorded proof of the installed map, install-equivalent sampled
     * read-back of the new map, then the same sampled old-map removal. */
    reset(size); uint32_t resolved=0; uint64_t sampled=0;
    assert(proof_check(size,plan,N,L,old_hash,sample_hash,&resolved,&sampled)==0);
    assert(resolved==OLD_ID && sampled==(uint64_t)N*L && bytes_read==sampled && read_requests==N);
    assert(progress_total==sampled && progress_done==sampled && full_reads==0);
    uint64_t after_current=bytes_read; progress_done=0;
    uint64_t new_sampled=0; assert(install_readback(size,install_offsets,install_count,&new_sampled)==0);
    uint64_t after_new=bytes_read-after_current;
    assert(new_sampled==install_bytes && after_new==install_bytes && full_reads==0);
    mark=bytes_read; progress_done=0; assert(delete_old(size,1)==0 && deletes==1); uint64_t after_delete=bytes_read-mark;
    uint64_t after_total=bytes_read;
    assert(after_delete==(uint64_t)N*L && sends==0);
    assert(after_total*10<size); /* far below even one full read */
    printf("PASS: 434 MB managed Safe Update content reads | before: installed map %llu + new map %llu + old-map removal %llu = %llu bytes; "
           "after: installed map %llu + new map %llu (%zu x %u) + old-map removal %llu = %llu bytes\n",
        (unsigned long long)before_current,(unsigned long long)before_new,(unsigned long long)before_delete,(unsigned long long)before_total,
        (unsigned long long)after_current,(unsigned long long)after_new,install_count,INSTALL_SAMPLE_LENGTH,
        (unsigned long long)after_delete,(unsigned long long)after_total);
    deletes=0;

    /* One changed byte in any recorded region of the installed map blocks
     * (first, middle and last byte of each region); nothing is mutated. */
    for (uint32_t region=0;region<N;++region) {
        uint64_t picks[3]={plan[region],plan[region]+L/2,plan[region]+L-1};
        for (int k=0;k<3;++k) {
            if (region==0 && picks[k]<0x48) continue;
            reset(size); flip_old=picks[k];
            assert(proof_check(size,plan,N,L,old_hash,sample_hash,&resolved,&sampled)==TERENTO_MTP_MAP_CONTENT_MISMATCH);
            assert(resolved==0 && sends==0 && deletes==0 && full_reads==0);
        }
    }
    puts("PASS: current-map check blocked a single changed byte in each of the 32 recorded regions");
    reset(size); flip_old=0x10;
    refused("changed IMG header byte",proof_check(size,plan,N,L,old_hash,sample_hash,&resolved,&sampled),TERENTO_MTP_MAP_CONTENT_MISMATCH);
    reset(size); old_present=0;
    refused("installed map missing",proof_check(size,plan,N,L,old_hash,sample_hash,&resolved,&sampled),TERENTO_MTP_MAP_OBJECT_ID_MISMATCH);
    reset(size); observed_old_size=size+1;
    refused("installed map size changed",proof_check(size,plan,N,L,old_hash,sample_hash,&resolved,&sampled),TERENTO_MTP_MAP_OBJECT_ID_MISMATCH);
    reset(size); duplicate_old=1;
    refused("duplicate installed map",proof_check(size,plan,N,L,old_hash,sample_hash,&resolved,&sampled),TERENTO_MTP_MAP_OBJECT_ID_MISMATCH);
    reset(size); substitute_after_read=1;
    refused("object replaced after the recorded reads",proof_check(size,plan,N,L,old_hash,sample_hash,&resolved,&sampled),TERENTO_MTP_MAP_OBJECT_ID_MISMATCH);
    reset(size); fail_offset=plan[9]+11;
    refused("read error",proof_check(size,plan,N,L,old_hash,sample_hash,&resolved,&sampled),-5);
    char wrong[65]; strcpy(wrong,sample_hash); wrong[0]=wrong[0]=='0'?'1':'0';
    reset(size); refused("wrong recorded digest",proof_check(size,plan,N,L,old_hash,wrong,&resolved,&sampled),TERENTO_MTP_MAP_CONTENT_MISMATCH);
    reset(size); refused("31-region proof",proof_check(size,plan,N-1,L,old_hash,sample_hash,&resolved,&sampled),-1);
    reset(size); refused("wrong region length",proof_check(size,plan,N,L+1,old_hash,sample_hash,&resolved,&sampled),-1);
    reset(size); refused("zero recorded digest",proof_check(size,plan,N,L,old_hash,
        "0000000000000000000000000000000000000000000000000000000000000000",&resolved,&sampled),-1);
    reset(size); refused("proof for another size",proof_check(size-1,plan,N,L,old_hash,sample_hash,&resolved,&sampled),-1);
    assert(bytes_read==0);
    puts("PASS: malformed proofs are refused before any device read; no fallback");

    /* New-map verification is the install read-back: a changed byte in any
     * compared region fails, and the old map is untouched (no delete). */
    for (size_t r=0;r<install_count;++r) {
        reset(size); flip_new=install_offsets[r]+INSTALL_SAMPLE_LENGTH/2; uint64_t s=0;
        assert(install_readback(size,install_offsets,install_count,&s)!=0 && deletes==0 && old_present);
    }
    puts("PASS: new-map sampled read-back fails on a changed byte in each compared region; old map kept");
    assert(sends==0);
    puts("PASS: native Safe Update sampled content checks (real entrypoints, fake libmtp, no USB)");
    return 0;
}
