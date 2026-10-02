const assert=require('node:assert/strict');
const {PGlite}=require(process.argv[2]);
const {sql}=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
(async()=>{
 const db=new PGlite();
 await db.exec(`CREATE TABLE device_model(id TEXT,model TEXT,variant TEXT,case_size_mm INT,screen_technology TEXT);
 CREATE TABLE map_package(id TEXT,provider_id TEXT,region TEXT,provider_region_id TEXT,canonical_region_id TEXT);
 CREATE TABLE compatibility_evidence_event(operation_id UUID,provider TEXT,region TEXT,phase_outcome TEXT,canonical_device_model_id TEXT,is_local_test BOOLEAN,statistics_exclusion_code TEXT);
 CREATE TABLE map_update_diagnostic(operation_id UUID,provider TEXT,region TEXT,outcome TEXT,canonical_device_model_id TEXT,is_local_test BOOLEAN);
 INSERT INTO device_model VALUES('exact','Catalog name','47 mm',47,'AMOLED'),('other','Other model','51 mm',51,'MIP');
 INSERT INTO map_package VALUES('lt','bbbike','Lithuania','LTU','LT'),('de','bbbike','Germany','DEU','DE');`);
 const uuid=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
 const targets=[];
 async function add(n,{update=false,outcome='SUCCEEDED',model='exact',provider='bbbike',region='Lithuania',local=false,excluded=null}={}) {
  if(update) await db.query('INSERT INTO map_update_diagnostic VALUES($1,$2,$3,$4,$5,$6)',[uuid(n),provider,region,outcome,model,local]);
  else await db.query('INSERT INTO compatibility_evidence_event VALUES($1,$2,$3,$4,$5,$6,$7)',[uuid(n),provider,region,outcome,model,local,excluded]);
 }
 function target(n,changes={}){targets.push({index:n,operation_id:uuid(n),provider_id:'bbbike',region:'Lithuania',map_package_id:'lt',event_type:'INSTALL_SUCCEEDED',outcome:'SUCCEEDED',trusted_model_id:null,...changes});}
 for(const [n,update,outcome] of [[1,false,'SUCCEEDED'],[2,false,'FAILED'],[3,true,'SUCCEEDED'],[4,true,'FAILED']]) {
  target(n,{event_type:`${update?'MAP_UPDATE':'INSTALL'}_${outcome}`,outcome}); await add(n,{update,outcome});
 }
 target(5); await add(5,{model:null}); // unresolved
 target(6); await add(6,{outcome:'FAILED'}); // opposite result
 target(7); await add(7,{provider:'maprando'}); // different provider
 target(8); await add(8,{region:'Germany'}); // different map in same operation
 target(9); await add(9,{local:true});
 target(10); await add(10,{excluded:'EXCLUDED'});
 target(11); await add(11); await add(11,{model:null}); // ambiguous multi-map result
 target(12); await add(12,{region:'LTU'}); // reviewed package aliases
 target(13,{region:'Unrelated'}); await add(13,{region:'LTU'}); // target must belong to package too
 target(14,{provider_id:'maprando'}); await add(14,{provider:'maprando',region:'LTU'}); // package of other provider
 target(15,{provider_id:'custom',trusted_model_id:'exact'});
 target(16,{provider_id:'custom',trusted_model_id:'missing'});
 target(17); // sharing disabled or diagnostic missing
 target(18,{event_type:'MAP_UPDATE_SUCCEEDED'}); await add(18,{update:true,local:true});
 target(19); await add(19); await add(19,{region:'LTU',model:'other'}); // same-region alias ambiguity
 target(20,{event_type:'MAP_UPDATE_SUCCEEDED'}); await add(20,{update:true}); await add(20,{update:true,model:null});
 target(21); await add(21); await add(21,{region:'Germany',model:'other'}); // exact map excludes another map
 target(22); await add(23); // operation identity must match; timestamp/name cannot correlate
 const result=(await db.query(sql,[JSON.stringify(targets)])).rows;
 assert.deepEqual(result.map(r=>r.index).sort((a,b)=>a-b),[1,2,3,4,12,15,21]);
 assert.ok(result.every(r=>r.model==='Catalog name'&&r.variant==='47 mm'&&r.canonical_device_model_id==='exact'));
 await db.close(); console.log('Activity exact correlation PASS');
})().catch(error=>{console.error(error);process.exit(1);});
