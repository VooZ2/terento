// Isolated PostgreSQL/WASM integration; no application or production data is used.
const {PGlite} = require(process.argv[2]);
const {randomUUID} = require('node:crypto');
(async () => {
 const input = JSON.parse(require('node:fs').readFileSync(0,'utf8'));
 const db = new PGlite();
 await db.exec(`CREATE TABLE map_download_event(event_id uuid, acquisition_id uuid, operation_id uuid,
 provider_id text, map_package_id text, component_kind text, region text, event_type text,
 outcome text, occurred_at timestamptz, is_local_test boolean,
 statistics_exclusion_code text)`);
 let rows=[]; const base=Date.parse('2026-09-01T00:00:00Z'); const op=randomUUID();
 const acquisition=(seconds, opts={})=>{
   const id=randomUUID(), start=base + (opts.cross ? -10000 : 10000);
   const phases=['STARTED','PROCESSING',opts.end || 'SUCCEEDED'].map((phase,i)=>({
     event_id:randomUUID(),acquisition_id:id,operation_id:op,provider_id:opts.provider || 'test',map_package_id:'map',
     component_kind:opts.component || 'main',region:'LT',event_type:'DOWNLOAD_'+phase,
     outcome:phase==='SUCCEEDED'?'SUCCEEDED':phase==='FAILED'?'FAILED':'UNKNOWN',
     occurred_at:new Date(start+(i===0?0:i===1?seconds*1000:Math.max(seconds*1000+1000,20000))).toISOString(),is_local_test:!!opts.local,
     statistics_exclusion_code:null
   }));
   rows.push(...phases);return phases;
 };
 acquisition(8); acquisition(277); acquisition(3912); acquisition(0); acquisition(20,{cross:true});
 acquisition(7,{provider:'other'});
 const duplicate=rows[0]; rows.push({...duplicate,event_id:randomUUID()});
 acquisition(9,{provider:'custom'}); acquisition(9,{component:'contours'}); acquisition(9,{local:true});
 for(const end of ['FAILED','CANCELLED','INTERRUPTED'])acquisition(9,{end});
 // Nine successful acquisitions that must not become measurements.
 let p=acquisition(9);rows=rows.filter(x=>x!==p[0]);
 p=acquisition(9);rows=rows.filter(x=>x!==p[1]);
 acquisition(-1);
 p=acquisition(9);rows.push({...p[1],event_id:randomUUID(),occurred_at:new Date(base+22000).toISOString()});
 p=acquisition(9);p[1].operation_id=randomUUID();
 p=acquisition(9);p[1].provider_id='other';
 p=acquisition(9);p[1].map_package_id='different';
 p=acquisition(9);p[1].component_kind='contours';
 p=acquisition(9);p.forEach(x=>x.acquisition_id=null); // legacy no reliable identity
 const cols=Object.keys(rows[0]);
 for(const row of rows)await db.query(`INSERT INTO map_download_event(${cols.join(',')}) VALUES(${cols.map((_,i)=>'$'+(i+1)).join(',')})`,cols.map(k=>row[k]));
 const result=await db.query(input.query,input.values);
 console.log(JSON.stringify(result.rows));await db.close();
})().catch(e=>{console.error(e);process.exitCode=1});
