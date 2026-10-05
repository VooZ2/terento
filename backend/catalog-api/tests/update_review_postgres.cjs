const assert=require('node:assert/strict');
const {PGlite}=require(process.argv[2]);
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
(async()=>{
 const db=new PGlite();
 await db.exec(`CREATE TABLE map_provider(id TEXT PRIMARY KEY); CREATE TABLE map_artifact(id TEXT PRIMARY KEY);
 CREATE TABLE device_model(id TEXT PRIMARY KEY,model TEXT,variant TEXT);
 CREATE TABLE admin_audit_log(admin_user_id BIGINT,action TEXT,provider_id TEXT,old_status TEXT,new_status TEXT,reason TEXT,target TEXT,request_id TEXT,details JSONB);`);
 await db.exec(`CREATE TABLE compatibility_evidence_event(event_id UUID,operation_id UUID,phase_outcome TEXT,write_started BOOLEAN,
 failure_stage TEXT,failure_code TEXT,linked_github_issue TEXT,canonical_device_model_id TEXT,identity_resolution_state TEXT,
 diagnostic_status TEXT,is_local_test BOOLEAN,statistics_exclusion_code TEXT,map_result_index INT,provider TEXT,region TEXT,
 compatibility_identity TEXT,model TEXT);
 CREATE TABLE compatibility_model_statistics(canonical_device_model_id TEXT,calculated_status TEXT,successful_install_count INT,
 review_status TEXT,public_statistics_enabled BOOLEAN);
 CREATE TABLE map_download_event(event_id UUID,operation_id UUID,is_local_test BOOLEAN,statistics_exclusion_code TEXT,
 event_type TEXT,outcome TEXT,map_package_id TEXT,provider_id TEXT,region TEXT,map_result_index INT,acquisition_id UUID,reported_map_id TEXT);
 CREATE TABLE map_package(id TEXT,provider_id TEXT,provider_region_id TEXT,canonical_region_id TEXT,region TEXT);
 CREATE TABLE admin_map_review_task(event_id UUID,task_type TEXT,status TEXT);
 INSERT INTO compatibility_evidence_event(event_id,operation_id,phase_outcome,write_started,canonical_device_model_id,diagnostic_status,is_local_test)
 VALUES('99999999-9999-4999-8999-999999999999','99999999-9999-4999-8999-999999999999','FAILED',TRUE,'exact-47','ACTIVE',FALSE);`);
 for(const migration of input.migrations) await db.exec(migration);
 await db.exec("INSERT INTO device_model VALUES('exact-47','fēnix 8','47 mm'),('exact-51','fēnix 8','51 mm')");
 let sequence=0;
 const uuid=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
 async function add({operation,model='exact-47',outcome='FAILED',write=true,finishing='FAILED',local=false,id,status='ACTIVE'}){
  const eventId=id||uuid(++sequence);
  await db.query(`INSERT INTO map_update_diagnostic(event_id,operation_id,occurred_at,provider,region,outcome,payload,is_local_test,canonical_device_model_id,diagnostic_status)
  VALUES($1,$2,now(),'bbbike','LTU',$3,$4::jsonb,$5,$6,$7)`,[eventId,uuid(operation),outcome,JSON.stringify({writeStarted:write,automaticFinishingResult:finishing}),local,model,status]);
 }
 await add({id:'11111111-1111-4111-8111-111111111111',operation:101});
 await add({operation:102,outcome:'SUCCEEDED',finishing:'VERIFIED'});
 await add({operation:102,outcome:'SUCCEEDED',finishing:'VERIFIED'}); // agreed duplicate: one attempt
 await add({operation:103,outcome:'NOT_STARTED',write:false,finishing:'NOT_REACHED'});
 await add({operation:104,outcome:'SUCCEEDED',finishing:'FAILED'}); // never verified
 await add({operation:105,local:true});
 await add({operation:106,model:null}); // historic/unassigned never guessed
 await add({operation:107,model:'exact-51'});
 await add({operation:108});
 await add({operation:108,outcome:'SUCCEEDED',finishing:'VERIFIED'}); // conflicting outcome
 await add({operation:109});
 await add({operation:109,model:'exact-51'}); // conflicting model
 await add({operation:111}); await add({operation:111,write:false}); // conflicting write boundary
 await add({operation:112,outcome:'SUCCEEDED',finishing:'VERIFIED'}); await add({operation:112,outcome:'SUCCEEDED',finishing:'FAILED'});
 await add({operation:113}); await add({operation:113,model:null}); // unassigned conflict cannot inherit exact model
 await add({operation:114}); await add({operation:114,outcome:'SUCCEEDED',finishing:'VERIFIED',local:true});
 await add({operation:110,status:'RESOLVED'}); // review does not erase outcomes
 const stats=async()=>Object.fromEntries((await db.query(input.stats)).rows.map(r=>[r.canonical_device_model_id,r]));
 const before=await stats();
 assert.deepEqual(before['exact-47'],{canonical_device_model_id:'exact-47',successful:1,failed:3,not_started:1,ambiguous:5});
 assert.deepEqual(before['exact-51'],{canonical_device_model_id:'exact-51',successful:0,failed:1,not_started:0,ambiguous:1});
 const evidenceBefore=(await db.query('SELECT event_id,outcome,payload,canonical_device_model_id FROM map_update_diagnostic ORDER BY event_id')).rows;
 const reviewCounts=[];
 for(const[sql,args]of input.mutations){
  let index=0;await db.query(sql.replace(/%s/g,()=>'$'+(++index)),args||[]);
  if(sql.includes('UPDATE map_update_diagnostic')){
   const summary=(await db.query(input.summary)).rows[0];
   assert.equal(summary.installation_issues,1);assert.equal(summary.identity_pending,0);assert.equal(summary.ready_to_publish,0);
   reviewCounts.push(summary.github_issues_in_progress);
  }
 }
 assert.deepEqual(reviewCounts,[1,1,0,1,0]);
 assert.deepEqual(await stats(),before);
 assert.deepEqual((await db.query('SELECT event_id,outcome,payload,canonical_device_model_id FROM map_update_diagnostic ORDER BY event_id')).rows,evidenceBefore);
 assert.equal((await db.query('SELECT count(*) n FROM map_update_diagnostic_audit')).rows[0].n,5);
 assert.equal((await db.query(input.queue)).rows.length,0); // GitHub closed -> queue empty
 // A linked local report must not enter the queue or be selected for review.
 await db.exec("UPDATE map_update_diagnostic SET linked_github_issue='#12' WHERE is_local_test IS TRUE");
 assert.equal((await db.query(input.queue)).rows.length,0);
 assert.equal((await db.query(input.summary)).rows[0].github_issues_in_progress,0);
 await db.close(); console.log('PASS exact model, conflict dedup, local exclusion, retained resolved counts and immutable review SQL');
})().catch(e=>{console.error(e);process.exit(1)});
