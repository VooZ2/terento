const assert=require('node:assert/strict');
const {PGlite}=require(process.argv[2]);
const {sql}=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
(async()=>{
 const db=new PGlite();
 await db.exec(`CREATE TABLE map_update_diagnostic(event_id UUID,operation_id UUID,occurred_at TIMESTAMPTZ,provider TEXT,region TEXT,outcome TEXT,is_local_test BOOLEAN,payload JSONB,canonical_device_model_id TEXT,diagnostic_status TEXT);
 CREATE TABLE map_provider(id TEXT,name TEXT);
 CREATE TABLE device_model(id TEXT,model TEXT,variant TEXT,case_size_mm INT,screen_technology TEXT);
 CREATE TABLE map_download_event(operation_id UUID,provider_id TEXT,region TEXT,is_local_test BOOLEAN,statistics_exclusion_code TEXT,event_type TEXT,outcome TEXT);
 INSERT INTO map_provider VALUES('freizeitkarte','Freizeitkarte');
 INSERT INTO device_model VALUES('exact','Catalog model','47 mm',47,'AMOLED');`);
 const uuid=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
 let id=100;
 async function add(n,changes={}) {
  const d={occurred:'2026-10-05T10:00:00Z',outcome:'NOT_STARTED',local:false,model:'exact',status:'ACTIVE',writeStarted:false,failureCode:'UPDATE_FAILED_ACQUISITION',...changes};
  await db.query('INSERT INTO map_update_diagnostic VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)',[uuid(id++),uuid(n),d.occurred,'freizeitkarte','LTU',d.outcome,d.local,{writeStarted:d.writeStarted,automaticFinishingResult:'NOT_REACHED',failureCode:d.failureCode},d.model,d.status]);
 }
 await add(1);await add(1); // replay with distinct report IDs collapses
 await add(2,{status:'RESOLVED'}); // review state must not erase history
 await add(3);await add(3,{outcome:'FAILED',writeStarted:true});
 await add(4);await add(4,{model:'other'});
 await add(5,{local:true});
 await add(6,{occurred:'2026-10-04T23:00:00Z'});
 await add(7);await add(7,{failureCode:'UPDATE_BLOCKED_NO_UPDATE'});
 await add(8,{model:null}); // show outcome, never guessed device
 await add(9);
 await db.query("INSERT INTO map_download_event VALUES($1,'freizeitkarte','LTU',false,NULL,'MAP_UPDATE_FAILED','FAILED')",[uuid(9)]);
 await add(10);await add(10,{outcome:'FAILED',writeStarted:true,occurred:'2026-10-04T23:00:00Z'}); // conflict before filter still matters
 const rows=(await db.query(sql,['2026-10-05T00:00:00Z',8])).rows;
 assert.deepEqual(rows.map(r=>r.operation_id).sort(),[uuid(1),uuid(2),uuid(8)]);
 assert.ok(rows.every(r=>r.event_type==='MAP_UPDATE_NOT_STARTED'&&r.outcome==='UNKNOWN'));
 assert.equal(rows.find(r=>r.operation_id===uuid(8)).model,null);
 assert.equal((await db.query(sql,['2026-10-05T00:00:00Z',1])).rows.length,1);
 await db.close();
 console.log('Update activity: dedup, resolved, conflicts, local/time/limit and no guessed identity passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
