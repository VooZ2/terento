/* Sampled removal proof: production native delete entrypoints with a synthetic
 * libmtp backend serving a virtual map object. No USB, no real map bytes. */
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

#define L TERENTO_REMOVAL_PROOF_REGION_LENGTH
#define N TERENTO_REMOVAL_PROOF_REGION_COUNT
static LIBMTP_mtpdevice_t device;
static LIBMTP_devicestorage_t storage;
static const char *filename = "terento_test_map.img";
static const char *observed_name;
static uint64_t object_size, observed_size;
static uint64_t flip_offset = UINT64_MAX; /* one changed live byte */
static uint64_t fail_offset = UINT64_MAX; /* one failed read */
static int duplicate, substitute_after_read, deletes, sends;
static uint64_t bytes_read, read_requests, progress_total, progress_done;
static char directory[] = "/private/tmp/terento-removal-proof-XXXXXX";
static char claim[PATH_MAX];
static unsigned operation;

/* Deterministic virtual content shared with ManagedRemovalProofTests.swift. */
static unsigned char content_byte(uint64_t offset) {
    if (offset < 0x48) {
        if (offset >= 0x10 && offset < 0x16) return (unsigned char)"DSKIMG"[offset - 0x10];
        if (offset >= 0x41 && offset < 0x47) return (unsigned char)"GARMIN"[offset - 0x41];
        return 0;
    }
    return (unsigned char)(((offset * 2654435761u) >> 13) ^ (offset >> 20));
}
static unsigned char live_byte(uint64_t offset) {
    return (unsigned char)(content_byte(offset) ^ (offset == flip_offset ? 1 : 0));
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
    LIBMTP_file_t *f=LIBMTP_new_file_t(); f->filename=strdup(name); f->item_id=id;
    f->storage_id=1; f->filetype=is_folder?LIBMTP_FILETYPE_FOLDER:LIBMTP_FILETYPE_UNKNOWN; f->filesize=size; return f;
}
static LIBMTP_file_t *fake_files(LIBMTP_mtpdevice_t *d, uint32_t s, uint32_t parent) {
    (void)d; (void)s;
    if (parent==LIBMTP_FILES_AND_FOLDERS_ROOT) return entry("GARMIN",10,1,0);
    if (parent!=10) return NULL;
    LIBMTP_file_t *f=entry(observed_name?observed_name:filename,substitute_after_read==2?78:77,0,observed_size);
    if (duplicate) f->next=entry(filename,79,0,observed_size);
    return f;
}
static int fake_send(LIBMTP_mtpdevice_t *d,const char *path,LIBMTP_file_t *f,LIBMTP_progressfunc_t p,const void *c) {
    (void)d; (void)path; (void)f; (void)p; (void)c; ++sends; return -1;
}
static int fake_delete(LIBMTP_mtpdevice_t *d,uint32_t id) { (void)d; assert(id==77); ++deletes; return 0; }
static int fake_partial(LIBMTP_mtpdevice_t *d,uint32_t id,uint64_t offset,uint32_t size,unsigned char **out,unsigned int *count) {
    (void)d; assert(id==77 && size>0 && size<=65536);
    if (offset+size>object_size) return -1;
    if (fail_offset>=offset && fail_offset<offset+size) return -1;
    *out=malloc(size); assert(*out);
    for (uint32_t i=0;i<size;++i) (*out)[i]=live_byte(offset+i);
    *count=size; bytes_read+=size; ++read_requests;
    if (substitute_after_read==1) substitute_after_read=2;
    return 0;
}
static int progress(uint64_t done, uint64_t total, const void *context) {
    (void)context; assert(done<=total && done>=progress_done); progress_done=done; progress_total=total; return 0;
}
static TerentoMTPMapOperationProfile profile(void) {
    return (TerentoMTPMapOperationProfile){2,0x091e,0x51b8,"Garmin","Test Watch","/GARMIN","TEST-SERIAL",1,1};
}

static char full_hash[65], sample_hash[65];
static uint64_t plan[N];
static uint32_t plan_count;
static void hex(const unsigned char *digest, char *out) {
    for (int i=0;i<32;++i) snprintf(out+i*2,3,"%02x",digest[i]);
}
static void hash_full(uint64_t size) {
    CC_SHA256_CTX c; CC_SHA256_Init(&c); unsigned char chunk[65536];
    for (uint64_t o=0;o<size;) { uint32_t n=(uint32_t)(size-o>sizeof(chunk)?sizeof(chunk):size-o);
        for (uint32_t i=0;i<n;++i) chunk[i]=content_byte(o+i); CC_SHA256_Update(&c,chunk,n); o+=n; }
    unsigned char d[32]; CC_SHA256_Final(d,&c); hex(d,full_hash);
}
static void hash_samples(uint64_t size, const uint64_t *offsets, uint32_t count, char *out) {
    CC_SHA256_CTX c; CC_SHA256_Init(&c);
    for (uint32_t r=0;r<count;++r) for (uint64_t o=offsets[r];o<size && o<offsets[r]+L;++o) {
        unsigned char b=content_byte(o); CC_SHA256_Update(&c,&b,1); }
    unsigned char d[32]; CC_SHA256_Final(d,&c); hex(d,out);
}
/* Any valid geometry: first region, last bytes, 30 spread regions between. */
static void spread_plan(uint64_t size) {
    plan_count=N; plan[0]=0; plan[N-1]=size-L;
    uint64_t width=(size-2*(uint64_t)L)/(N-2);
    for (uint32_t i=0;i<N-2;++i) plan[i+1]=L+i*width+(i*7919u)%(width-L+1);
}
static void reset(uint64_t size) {
    object_size=observed_size=size; observed_name=NULL; flip_offset=fail_offset=UINT64_MAX;
    duplicate=substitute_after_read=0; bytes_read=read_requests=progress_total=progress_done=0;
}
static TerentoMTPMutationAuthorization grant(uint32_t purpose, uint64_t size, int with_proof) {
    static char id[64]; snprintf(id,sizeof(id),"proof-%u",++operation);
    uint32_t sequence=purpose==TERENTO_MUTATION_UPDATE_OLD?2:1;
    snprintf(claim,sizeof(claim),"%s/%s-%u.claim",directory,id,sequence);
    if (purpose==TERENTO_MUTATION_UPDATE_OLD) { /* same-operation verified new map */
        char path[PATH_MAX], text[160]; int fd;
        snprintf(path,sizeof(path),"%s/%s-1.claim",directory,id); snprintf(text,sizeof(text),"%s-1.claim|2|1",id);
        fd=open(path,O_WRONLY|O_CREAT|O_EXCL,0600); assert(fd>=0); assert(write(fd,text,strlen(text))==(ssize_t)strlen(text)); close(fd);
        snprintf(path,sizeof(path),"%s/%s-verified-new",directory,id);
        fd=open(path,O_WRONLY|O_CREAT|O_EXCL,0600); assert(fd>=0); assert(write(fd,id,strlen(id))==(ssize_t)strlen(id)); close(fd);
    }
    TerentoMTPMutationAuthorization a={1,id,claim,sequence,purpose,TERENTO_MUTATION_DELETE,filename,size,full_hash,
        "TEST-SERIAL",1,1,"/GARMIN",NULL,0,0,NULL};
    if (with_proof) { a.removal_sample_offsets=plan; a.removal_sample_count=plan_count;
        a.removal_sample_length=L; a.removal_sample_sha256=sample_hash; }
    return a;
}
static int delete_managed(TerentoMTPMutationAuthorization *a, TerentoMTPMutationRecord *r, uint64_t size) {
    TerentoMTPMapOperationProfile p=profile(); char error[256]={0};
    return terento_mtp_delete_managed_map_authorized(&p,a,r,filename,999,size,progress,NULL,error,sizeof(error));
}
static void refused(const char *scenario, uint64_t size, TerentoMTPMutationAuthorization a) {
    int before=deletes; TerentoMTPMutationRecord r;
    int result=delete_managed(&a,&r,size);
    assert(result!=0 && deletes==before && !r.attempted);
    printf("PASS: refused %s | delete=0 bytes_read=%llu\n",scenario,(unsigned long long)bytes_read);
}

int main(void) {
    assert(mkdtemp(directory)); chmod(directory,0700);
    storage.id=1; device.storage=&storage;
    const uint64_t size=434000000ull; /* a 434 MB managed map */
    hash_full(size); spread_plan(size); hash_samples(size,plan,plan_count,sample_hash);

    /* Before: a managed entry without a proof reads the whole object. */
    reset(size); TerentoMTPMutationRecord r;
    TerentoMTPMutationAuthorization a=grant(TERENTO_MUTATION_REMOVE_MANAGED,size,0);
    assert(delete_managed(&a,&r,size)==0 && deletes==1 && r.attempted && r.completed);
    assert(bytes_read==size && progress_total==size && progress_done==size);
    uint64_t full_bytes=bytes_read, full_requests=read_requests;

    /* After: the recorded proof reads only its 32 regions, one request each. */
    reset(size); a=grant(TERENTO_MUTATION_REMOVE_MANAGED,size,1);
    assert(delete_managed(&a,&r,size)==0 && deletes==2 && r.attempted && r.completed);
    assert(bytes_read==(uint64_t)N*L && read_requests==N && progress_total==(uint64_t)N*L && progress_done==progress_total);
    printf("PASS: 434 MB managed Remove | full check read %llu bytes in %llu requests; sampled proof read %llu bytes in %llu requests\n",
        (unsigned long long)full_bytes,(unsigned long long)full_requests,
        (unsigned long long)bytes_read,(unsigned long long)read_requests);

    /* Update's old-map removal uses the same proof. */
    reset(size); a=grant(TERENTO_MUTATION_UPDATE_OLD,size,1);
    assert(delete_managed(&a,&r,size)==0 && deletes==3 && bytes_read==(uint64_t)N*L);
    puts("PASS: Update old-map removal deletes after the sampled proof only");

    /* One changed byte in any sampled region refuses (first, middle, last byte). */
    for (uint32_t region=0;region<N;++region) {
        uint64_t picks[3]={plan[region],plan[region]+L/2,plan[region]+L-1};
        for (int k=0;k<3;++k) {
            if (region==0 && picks[k]<0x48) continue; /* header bytes: separate case below */
            reset(size); flip_offset=picks[k];
            a=grant(TERENTO_MUTATION_REMOVE_MANAGED,size,1);
            int before=deletes; assert(delete_managed(&a,&r,size)!=0 && deletes==before && !r.attempted);
        }
    }
    puts("PASS: refused a single changed byte in each of the 32 sampled regions");
    reset(size); flip_offset=0x10; refused("changed IMG header byte",size,grant(TERENTO_MUTATION_REMOVE_MANAGED,size,1));

    /* Exact object identity in the delete session. */
    reset(size); observed_name="terento_other_map.img"; refused("wrong object name",size,grant(TERENTO_MUTATION_REMOVE_MANAGED,size,1));
    reset(size); observed_size=size+1; refused("wrong object size",size,grant(TERENTO_MUTATION_REMOVE_MANAGED,size,1));
    reset(size); duplicate=1; refused("duplicate object",size,grant(TERENTO_MUTATION_REMOVE_MANAGED,size,1));
    reset(size); substitute_after_read=1; refused("object id changed after the sampled reads",size,grant(TERENTO_MUTATION_REMOVE_MANAGED,size,1));
    reset(size); fail_offset=plan[5]+3; refused("sampled read error",size,grant(TERENTO_MUTATION_REMOVE_MANAGED,size,1));

    /* Malformed or partial proofs refuse; they never fall back silently. */
    char wrong_hash[65]; strcpy(wrong_hash,sample_hash); wrong_hash[0]=wrong_hash[0]=='0'?'1':'0';
    TerentoMTPMutationAuthorization bad;
    reset(size); bad=grant(TERENTO_MUTATION_REMOVE_MANAGED,size,1); bad.removal_sample_sha256=wrong_hash; refused("wrong sample digest",size,bad);
    reset(size); bad=grant(TERENTO_MUTATION_REMOVE_MANAGED,size,1); bad.removal_sample_sha256="0000000000000000000000000000000000000000000000000000000000000000"; refused("zero sample digest",size,bad);
    reset(size); bad=grant(TERENTO_MUTATION_REMOVE_MANAGED,size,1); bad.removal_sample_count=N-1; refused("31-region plan",size,bad);
    reset(size); bad=grant(TERENTO_MUTATION_REMOVE_MANAGED,size,1); bad.removal_sample_length=65536; refused("wrong region length",size,bad);
    reset(size); bad=grant(TERENTO_MUTATION_REMOVE_MANAGED,size,1); bad.removal_sample_count=0; refused("partial proof without offsets",size,bad);
    reset(size); bad=grant(TERENTO_MUTATION_REMOVE_MANAGED,size,0); bad.removal_sample_sha256=sample_hash; refused("digest without plan",size,bad);
    uint64_t saved;
    saved=plan[0]; plan[0]=1; reset(size); refused("plan not starting at offset 0",size,grant(TERENTO_MUTATION_REMOVE_MANAGED,size,1)); plan[0]=saved;
    saved=plan[N-1]; plan[N-1]=size-L-1; reset(size); refused("plan not ending at the last byte",size,grant(TERENTO_MUTATION_REMOVE_MANAGED,size,1)); plan[N-1]=saved;
    saved=plan[7]; plan[7]=plan[6]+L-1; reset(size); refused("overlapping regions",size,grant(TERENTO_MUTATION_REMOVE_MANAGED,size,1)); plan[7]=saved;
    saved=plan[7]; plan[7]=plan[9]; plan[9]=saved; reset(size); refused("unsorted regions",size,grant(TERENTO_MUTATION_REMOVE_MANAGED,size,1)); plan[9]=plan[7]; plan[7]=saved;
    reset(size); bad=grant(TERENTO_MUTATION_REMOVE_MANAGED,size,1); bad.expected_sha256="0000000000000000000000000000000000000000000000000000000000000000"; refused("proof with invalid full hash",size,bad);

    /* External removal always uses the full check: a supplied proof is refused before any device access. */
    reset(size); a=grant(TERENTO_MUTATION_REMOVE_EXTERNAL,size,1);
    { TerentoMTPMapOperationProfile p=profile(); char error[256]; int before=deletes;
      assert(terento_mtp_delete_external_map_authorized(&p,&a,&r,filename,999,size,progress,NULL,error,sizeof(error))
          ==TERENTO_MTP_MUTATION_REFUSED && deletes==before && bytes_read==0 && !r.attempted); }
    puts("PASS: external removal refuses a sampled proof (full SHA-256 only)");
    reset(size); a=grant(TERENTO_MUTATION_REMOVE_EXTERNAL,size,0);
    { TerentoMTPMapOperationProfile p=profile(); char error[256];
      assert(terento_mtp_delete_external_map_authorized(&p,&a,&r,filename,999,size,progress,NULL,error,sizeof(error))==0
          && deletes==4 && bytes_read==size); }
    puts("PASS: external removal reads the whole object for its full SHA-256");

    /* Small maps: the proof tiles the whole file, so it is the full content. */
    const uint64_t small=150000; hash_full(small);
    plan_count=3; plan[0]=0; plan[1]=L; plan[2]=2*(uint64_t)L; hash_samples(small,plan,plan_count,sample_hash);
    reset(small); a=grant(TERENTO_MUTATION_REMOVE_MANAGED,small,1);
    assert(delete_managed(&a,&r,small)==0 && deletes==5 && bytes_read==small);
    plan_count=2; reset(small); refused("small map plan not covering the file",small,grant(TERENTO_MUTATION_REMOVE_MANAGED,small,1));
    puts("PASS: small managed map proof covers every byte");

    /* Cross-language golden: ManagedRemovalProofTests.swift records this exact
     * plan and digest from a local file with the same virtual content. */
    const uint64_t golden_size=5000000;
    static const uint64_t golden_plan[N]={
        0ull,81005ull,234085ull,479683ull,615030ull,739104ull,
        943268ull,1060447ull,1233770ull,1388787ull,1606203ull,1700738ull,
        1913924ull,2077926ull,2186130ull,2408816ull,2521019ull,2721118ull,
        2844610ull,3013496ull,3218342ull,3407722ull,3515707ull,3712406ull,
        3806923ull,4005117ull,4165570ull,4366903ull,4492503ull,4647142ull,
        4825178ull,4934465ull
    };
    hash_full(golden_size); memcpy(plan,golden_plan,sizeof(plan)); plan_count=N;
    strcpy(sample_hash,"ec831e2f7c30ea1650efecec649b82c2c27a85c043d987470308487877d089f1");
    assert(!strcmp(full_hash,"35b075826c4725a555a932903ef651024a548690b825fd366fa1558da901da1e"));
    reset(golden_size); a=grant(TERENTO_MUTATION_REMOVE_MANAGED,golden_size,1);
    assert(delete_managed(&a,&r,golden_size)==0 && deletes==6 && bytes_read==(uint64_t)N*L);
    puts("PASS: Swift-recorded golden proof is accepted by the native sampled check");
    assert(sends==0);
    puts("PASS: native sampled removal proof (real entrypoints, fake libmtp, no USB)");
    return 0;
}
