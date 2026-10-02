// Execute recovery's actual SQL commands against isolated PostgreSQL/WASM.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { PGlite } = require(process.argv[2]);
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const db = new PGlite();
  await db.exec(`
    CREATE TABLE map_provider(id TEXT PRIMARY KEY, status TEXT);
    CREATE TABLE map_package(id TEXT PRIMARY KEY, provider_id TEXT, provider_region_id TEXT,
      map_type TEXT, country_codes JSONB, region TEXT, availability TEXT,
      release TEXT, version_label TEXT, release_id TEXT, generated_at TIMESTAMPTZ,
      source_updated_at TIMESTAMPTZ, updated_at TIMESTAMPTZ);
    CREATE TABLE map_artifact(id TEXT PRIMARY KEY, package_id TEXT, source_url TEXT,
      validation_status TEXT CHECK(validation_status IN ('NOT_VALIDATED','VALIDATING','VALIDATED','FAILED','UNAVAILABLE')),
      required BOOLEAN, size_bytes BIGINT, install_size_bytes BIGINT,
      install_payload_path TEXT, source_proof JSONB, source_updated_at TIMESTAMPTZ,
      updated_at TIMESTAMPTZ);
    CREATE TABLE provider_source(provider_id TEXT, source_type TEXT, source_url TEXT,
      last_checked_at TIMESTAMPTZ, updated_at TIMESTAMPTZ);
  `);
  await db.exec(input.migration);
  await db.exec("INSERT INTO map_provider VALUES ('bbbike','ACTIVE')");
  for (const row of input.rows) {
    await db.query("INSERT INTO map_package(id,provider_id,availability) VALUES($1,'bbbike','UNAVAILABLE')", [row.package_id]);
    await db.query("INSERT INTO map_artifact(id,package_id,source_url,updated_at,validation_status,required) VALUES($1,$2,$3,$4,'UNAVAILABLE',TRUE)", [row.id,row.package_id,row.source_url,row.updated_at]);
    await db.query("INSERT INTO provider_source(provider_id,source_type,source_url) VALUES('bbbike','DOWNLOAD',$1)", [row.source_url]);
  }
  await db.exec("INSERT INTO provider_recheck(provider_id) VALUES ('bbbike')");
  // Locks are exercised in process tests; this single PostgreSQL session validates
  // all publication SQL, parameter types, constraints and durable query results.
  for (const [sql, args] of input.commands) {
    if (sql.includes('pg_try_advisory_lock') || sql.includes('pg_advisory_unlock')) continue;
    let index = 0;
    await db.query(sql.replace(/%s/g, () => '$' + (++index)), args);
  }
  const artifacts = (await db.query('SELECT * FROM map_artifact ORDER BY id')).rows;
  const packages = (await db.query('SELECT * FROM map_package ORDER BY id')).rows;
  const job = (await db.query('SELECT * FROM provider_recheck')).rows[0];
  const history = (await db.query('SELECT * FROM provider_artifact_check')).rows;
  assert.equal(job.state, input.expectedState);
  assert.equal(history.length, input.resultCount);
  if (input.expectedState === 'SUCCEEDED') {
    assert(artifacts.every(a => a.validation_status === 'VALIDATED' && a.source_proof.revision === 'abc'));
    assert(packages.every(p => p.availability === 'AVAILABLE' && p.release === '2026-09-30' && p.release_id === 'abc'));
    assert.equal((await db.query('SELECT count(*) AS n FROM provider_source WHERE last_checked_at IS NOT NULL')).rows[0].n, 2);
  } else {
    assert(artifacts.every(a => a.validation_status === 'UNAVAILABLE'));
    assert(job.retry_not_before);
    assert.equal(job.results[0].httpStatus,429);
  }
  // Actual partial unique index, independent of Python precheck, blocks a race.
  await db.exec("INSERT INTO provider_recheck(provider_id) VALUES ('bbbike')");
  await assert.rejects(db.exec("INSERT INTO provider_recheck(provider_id) VALUES ('bbbike')"), /duplicate key/);
  await db.close();
  console.log('PASS provider recovery migration, publication, cooldown and active-job uniqueness');
})().catch(error => { console.error(error); process.exit(1); });
