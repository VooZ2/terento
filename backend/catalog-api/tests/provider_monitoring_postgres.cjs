const assert = require('node:assert/strict');
const fs = require('node:fs');
const { PGlite } = require(process.argv[2]);
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
 const db = new PGlite();
 await db.exec(`
 CREATE TABLE map_provider(id text PRIMARY KEY,status text,updated_at timestamptz);
 CREATE TABLE map_package(id text PRIMARY KEY,provider_id text,availability text,release text,updated_at timestamptz, provider_region_id text,canonical_region_id text, name text,region text,country text,release_id text,version_label text,generated_at timestamptz,source_updated_at timestamptz,map_type text,geographic_region_id text,country_codes jsonb,region_kind text);
 CREATE TABLE provider_health_check(id serial PRIMARY KEY,provider_id text,checked_at timestamptz);
 CREATE TABLE admin_audit_log(admin_user_id int,action text,provider_id text,old_status text,new_status text,reason text,target text,request_id text,details jsonb);
 INSERT INTO map_provider(id,status) VALUES ('due','ACTIVE'),('fresh','ACTIVE'),('paused','PAUSED'),('cooldown','ACTIVE'),('never','ACTIVE');
 INSERT INTO map_package(id,provider_id,availability) VALUES ('pkg','due','AVAILABLE');
 `);
 await db.exec(input.migration);
 async function command([sql,args]) { let i=0; return db.query(sql.replace(/%s/g,()=>'$'+(++i)),args); }
 for(const c of input.interval) await command(c);
 assert.equal((await db.query("SELECT health_check_interval_hours AS n FROM map_provider WHERE id='due'")).rows[0].n,6);
 await assert.rejects(db.exec("UPDATE map_provider SET health_check_interval_hours=2 WHERE id='due'"),/check constraint/);
 for(const c of input.disable) await command(c);
 assert.equal((await db.query("SELECT downloads_disabled AS d FROM map_package WHERE id='pkg'")).rows[0].d,true);
 assert.equal((await db.query("SELECT downloads_disabled_reason AS r FROM map_package WHERE id='pkg'")).rows[0].r,'Broken map');
 await command([input.packageSql,['pkg','due','LT','LT','Lithuania','LT','Lithuania','2026-10','new','2026-10',null,null,'AVAILABLE','base','LT','["LT"]','country']]);
 assert.equal((await db.query("SELECT downloads_disabled AS d FROM map_package WHERE id='pkg'")).rows[0].d,true);
 assert.equal((await db.query("SELECT release AS r FROM map_package WHERE id='pkg'")).rows[0].r,'2026-10');
 for(const c of input.enable) await command(c);
 assert.equal((await db.query("SELECT downloads_disabled AS d FROM map_package WHERE id='pkg'")).rows[0].d,false);
 assert.equal((await db.query('SELECT count(*)::int AS n FROM admin_audit_log')).rows[0].n,3);
 await db.exec(`INSERT INTO provider_health_check(provider_id,checked_at) VALUES
 ('due',now()-interval '7 hours'),('fresh',now()),('paused',now()-interval '2 days'),('cooldown',now()-interval '2 days');
 UPDATE map_provider SET health_retry_not_before=now()+interval '2 hours' WHERE id='cooldown';`);
 assert.deepEqual((await command(input.due)).rows.map(r=>r.id),['never','due']);
 await command(input.cooldown);
 assert.deepEqual((await command(input.due)).rows.map(r=>r.id),['never']);
 const expiry=(await db.query("SELECT health_retry_not_before AS t FROM map_provider WHERE id='due'")).rows[0].t;
 await command([input.cooldown[0],[null,null,'due']]);
 assert.equal((await db.query("SELECT health_retry_not_before AS t FROM map_provider WHERE id='due'")).rows[0].t.toISOString(),expiry.toISOString());
 await db.exec(`INSERT INTO provider_health_check(provider_id,checked_at)
 SELECT 'due',now()- n*interval '1 hour' FROM generate_series(8,40) n;
 INSERT INTO provider_health_check(provider_id,checked_at) VALUES ('due',now()-interval '60 days'),('paused',now()-interval '70 days'),('old-only',now()-interval '90 days');`);
 await command(input.prune);
 assert.equal((await db.query("SELECT count(*)::int AS n FROM provider_health_check WHERE provider_id='old-only'")).rows[0].n,1);
 assert.equal((await db.query("SELECT count(*)::int AS n FROM provider_health_check WHERE provider_id='due' AND checked_at<now()-interval '30 days'")).rows[0].n,0);
 assert.equal((await command(input.history)).rows.length,11);
 await db.exec("UPDATE map_provider SET status='RETIRED' WHERE id='due'");
 assert.equal((await command(input.disable[0])).rows.length,0);
 await db.close(); console.log('PASS migration066 controls/audit, due/cooldown, retention and capped history SQL');
})().catch(error=>{console.error(error);process.exit(1);});
