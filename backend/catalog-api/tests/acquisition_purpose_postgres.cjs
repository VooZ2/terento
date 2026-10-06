const assert=require('node:assert/strict');
const {PGlite}=require(process.argv[2]);
const migration=require('node:fs').readFileSync(process.argv[3],'utf8');
(async()=>{
 const db=new PGlite();
 await db.exec("CREATE TABLE map_download_event(event_id TEXT PRIMARY KEY);INSERT INTO map_download_event VALUES('historical');");
 await db.exec(migration);
 await db.exec("INSERT INTO map_download_event(event_id) VALUES('old-writer');INSERT INTO map_download_event VALUES('fresh','install'),('replacement','update');");
 assert.equal((await db.query('SELECT count(*) AS n FROM map_download_event WHERE acquisition_purpose IS NULL')).rows[0].n,2);
 await assert.rejects(db.exec("INSERT INTO map_download_event VALUES('invalid','guess')"));
 assert.deepEqual((await db.query('SELECT event_id FROM map_download_event ORDER BY event_id')).rows.map(r=>r.event_id),['fresh','historical','old-writer','replacement']);
 await db.close();
})().catch(e=>{console.error(e);process.exitCode=1;});
