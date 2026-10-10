// Production SQL against isolated PostgreSQL: local purge must preserve production
// even when the client reuses an operation UUID across local/production streams.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const { PGlite } = require(process.argv[2]);
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const db = new PGlite();
  await db.exec(`
    CREATE TABLE map_provider(id TEXT PRIMARY KEY);
    CREATE TABLE map_artifact(id TEXT PRIMARY KEY);
    CREATE TABLE compatibility_evidence_event(event_id UUID PRIMARY KEY, operation_id UUID, release_label TEXT,
      phase_outcome TEXT, occurred_at TIMESTAMPTZ, is_local_test BOOLEAN NOT NULL);
    CREATE TABLE map_download_event(event_id UUID PRIMARY KEY, operation_id UUID, release_label TEXT,
      outcome TEXT, occurred_at TIMESTAMPTZ, is_local_test BOOLEAN NOT NULL);
    CREATE TABLE support_report(id UUID PRIMARY KEY, is_local_test BOOLEAN NOT NULL);
    CREATE TABLE admin_audit_log(admin_user_id BIGINT, action TEXT, provider_id TEXT, old_status TEXT,
      new_status TEXT, reason TEXT, target TEXT, request_id TEXT, details JSONB);
  `);
  await db.exec(input.migration);
  const op = '11111111-1111-4111-8111-111111111111';
  const local = '22222222-2222-4222-8222-222222222222';
  const prod = '33333333-3333-4333-8333-333333333333';
  for (const [id, isLocal] of [[local, true], [prod, false]]) {
    const label = isLocal ? '1.0.0-beta.15-local' : '1.0.0-beta.15';
    await db.query("INSERT INTO compatibility_evidence_event VALUES($1,$2,$3,'FAILED',now(),$4)", [id,op,label,isLocal]);
    await db.query("INSERT INTO map_download_event VALUES($1,$2,$3,'FAILED',now(),$4)", [id,op,label,isLocal]);
    await db.query("INSERT INTO map_update_diagnostic(event_id,operation_id,occurred_at,provider,region,outcome,payload,is_local_test) VALUES($1,$2,now(),'bbbike','LTU','FAILED',$3::jsonb,$4)", [id,op,JSON.stringify({releaseLabel:label}),isLocal]);
  }
  const execute = ([sql, args]) => {
    let index=0;
    return db.query(sql.replace(/%s/g, () => '$'+(++index)), args || []);
  };
  const summaries = [];
  for (const query of input.summary) summaries.push((await execute(query)).rows);
  assert.equal(summaries[0][0].event_count, 2);
  assert.deepEqual(summaries[0][0].labels,['1.0.0-beta.15-local']);
  assert.equal(summaries[1][0].event_count, 1);
  assert.equal(summaries[2][0].operation_count, 1);
  assert.equal(summaries[3].length, 3);
  await db.exec('BEGIN');
  for (const query of input.purge) await execute(query);
  await db.exec('COMMIT');
  for (const table of ['compatibility_evidence_event','map_download_event','map_update_diagnostic']) {
    const rows = (await db.query('SELECT event_id,is_local_test FROM '+table)).rows;
    assert.deepEqual(rows,[{event_id:prod,is_local_test:false}]);
  }
  await db.close();
  console.log('PASS: local update diagnostics counted, excluded and purged without deleting production');
})().catch(error => { console.error(error); process.exit(1); });
