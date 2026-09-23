// Isolated PostgreSQL/WASM migration regression; never connects to an app DB.
const assert = require('node:assert/strict');
const { PGlite } = require(process.argv[2]);

const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const eventIds = {
  included: '00000000-0000-4000-8000-000000000001',
  excluded: '00000000-0000-4000-8000-000000000002',
  map: '00000000-0000-4000-8000-000000000003',
};
const operationId = '00000000-0000-4000-8000-000000000010';

async function createFixture() {
  const db = new PGlite();
  await db.exec(`
    CREATE TABLE compatibility_evidence_event (
      event_id UUID PRIMARY KEY,
      occurred_at TIMESTAMPTZ NOT NULL,
      model TEXT NOT NULL,
      compatibility_identity TEXT NOT NULL,
      variant TEXT,
      case_size_mm INTEGER,
      display_type TEXT,
      canonical_device_model_id TEXT,
      identity_assessment JSONB,
      operation_id UUID,
      map_result_index INTEGER,
      selected_map_count INTEGER,
      provider TEXT NOT NULL,
      region TEXT NOT NULL,
      phase_outcome TEXT NOT NULL,
      automatic_finishing_result TEXT,
      reconnect_verified BOOLEAN NOT NULL DEFAULT FALSE,
      firmware_version TEXT,
      error_category TEXT,
      failure_stage TEXT,
      failure_code TEXT,
      app_build TEXT,
      release_label TEXT,
      write_started BOOLEAN,
      diagnostic_status TEXT NOT NULL DEFAULT 'ACTIVE',
      is_local_test BOOLEAN NOT NULL DEFAULT FALSE
    );
    CREATE TABLE map_download_event (
      event_id UUID PRIMARY KEY,
      operation_id UUID NOT NULL,
      provider_id TEXT NOT NULL,
      map_package_id TEXT,
      region TEXT,
      event_type TEXT NOT NULL,
      outcome TEXT NOT NULL,
      occurred_at TIMESTAMPTZ NOT NULL
    );
    CREATE TABLE device_model (id TEXT PRIMARY KEY, map_capable BOOLEAN);
    CREATE TABLE compatibility_model_review (
      identity_key TEXT,
      model TEXT NOT NULL,
      review_status TEXT NOT NULL DEFAULT 'PENDING',
      physical_device_evidence_count INTEGER NOT NULL DEFAULT 0,
      review_notes TEXT NOT NULL DEFAULT '',
      public_statistics_enabled BOOLEAN NOT NULL DEFAULT FALSE,
      public_display_name TEXT,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE FUNCTION terento_compatibility_status(successful_count BIGINT, recognized BOOLEAN)
      RETURNS TEXT LANGUAGE SQL IMMUTABLE AS $$
        SELECT CASE WHEN recognized AND successful_count > 0 THEN 'VERIFIED' ELSE 'PENDING' END
      $$;
    CREATE TABLE schema_migrations (version TEXT PRIMARY KEY);
    INSERT INTO schema_migrations(version) VALUES ('060'), ('061');
  `);

  for (const [eventId, identity] of [
    [eventIds.included, 'Migration 062 included fixture'],
    [eventIds.excluded, 'Migration 062 excluded fixture'],
  ]) {
    await db.query(`
      INSERT INTO compatibility_evidence_event (
        event_id, occurred_at, model, compatibility_identity, provider, region,
        phase_outcome, automatic_finishing_result, write_started
      ) VALUES ($1, now(), 'Fixture Watch', $2, 'freizeitkarte', 'LT',
                'SUCCEEDED', 'VERIFIED', TRUE)
    `, [eventId, identity]);
  }
  await db.query(`
    INSERT INTO map_download_event (
      event_id, operation_id, provider_id, map_package_id, region,
      event_type, outcome, occurred_at
    ) VALUES ($1, $2, 'freizeitkarte', 'fixture-map', 'LT',
              'INSTALL_SUCCEEDED', 'SUCCEEDED', now())
  `, [eventIds.map, operationId]);
  await db.exec(input.legacyView + ';');
  return db;
}

async function runStatements(db, statements) {
  for (const statement of statements) await db.exec(statement + ';');
}

async function viewColumns(db) {
  const result = await db.query(`
    SELECT column_name, data_type, udt_name, ordinal_position
    FROM information_schema.columns
    WHERE table_schema = current_schema()
      AND table_name = 'compatibility_model_statistics'
    ORDER BY ordinal_position
  `);
  return result.rows;
}

async function visibleIdentities(db) {
  const result = await db.query(`
    SELECT compatibility_identity
    FROM compatibility_model_statistics
    ORDER BY compatibility_identity
  `);
  return result.rows.map(row => row.compatibility_identity);
}

async function assertReconciled(db) {
  const expectedColumns = [
    ['compatibility_evidence_event', 'statistics_exclusion_code'],
    ['compatibility_evidence_event', 'statistics_exclusion_reason'],
    ['compatibility_evidence_event', 'security_issue_code'],
    ['map_download_event', 'map_result_index'],
    ['map_download_event', 'statistics_exclusion_code'],
    ['map_download_event', 'statistics_exclusion_reason'],
    ['map_download_event', 'security_issue_code'],
  ];
  for (const [table, column] of expectedColumns) {
    const result = await db.query(`
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = current_schema() AND table_name = $1 AND column_name = $2
    `, [table, column]);
    assert.equal(result.rows.length, 1, `${table}.${column} exists`);
  }

  const indexes = await db.query(`
    SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()
  `);
  const indexNames = new Set(indexes.rows.map(row => row.indexname));
  for (const name of [
    'compatibility_statistics_exclusion_idx',
    'map_statistics_exclusion_idx',
    'statistics_exclusion_audit_pkey',
    'statistics_exclusion_audit_stream_event_id_exclusion_code_key',
    'statistics_exclusion_audit_event_idx',
  ]) assert(indexNames.has(name), `${name} exists`);

  const constraints = await db.query(`
    SELECT conname FROM pg_constraint
    WHERE conrelid = 'statistics_exclusion_audit'::regclass
  `);
  const constraintNames = new Set(constraints.rows.map(row => row.conname));
  for (const name of [
    'statistics_exclusion_audit_pkey',
    'statistics_exclusion_audit_stream_check',
    'statistics_exclusion_audit_stream_event_id_exclusion_code_key',
  ]) assert(constraintNames.has(name), `${name} constraint exists`);
}

async function cleanMigrationPath() {
  const db = await createFixture();
  const before062 = await viewColumns(db);
  assert.equal(before062.length, 29);
  // The checked-in beta already owns versions 060/061. Reconcile from the
  // legacy schema using 062 alone; never replay alternate untracked sources.
  await runStatements(db, input.migration062);
  const after062 = await viewColumns(db);
  assert.deepEqual(after062, before062, '062 replacement preserves legacy view signature');
  await assertReconciled(db);
  await db.query(`
    UPDATE compatibility_evidence_event SET statistics_exclusion_code = 'fixture-excluded'
    WHERE event_id = $1
  `, [eventIds.excluded]);
  assert.deepEqual(await visibleIdentities(db), ['Migration 062 included fixture']);
  await db.close();
  return after062;
}

async function liveLikeRepair() {
  const db = await createFixture();
  const before = await viewColumns(db);
  assert.equal(before.length, 29);
  const historicalBefore = await db.query(`
    SELECT event_id::text AS event_id, operation_id::text AS operation_id,
           event_type, outcome
    FROM map_download_event WHERE event_id = $1
  `, [eventIds.map]);

  // 060/061 are present in the migration ledger; only the additive 062 SQL
  // is executed against this intentionally drifted live-like schema.
  await runStatements(db, input.migration062);
  const after = await viewColumns(db);
  assert.deepEqual(after, before, '062 replacement preserves audited live view names/order/types');
  await assertReconciled(db);
  await db.query(`
    UPDATE compatibility_evidence_event SET statistics_exclusion_code = 'fixture-excluded'
    WHERE event_id = $1
  `, [eventIds.excluded]);
  assert.deepEqual(await visibleIdentities(db), ['Migration 062 included fixture']);

  const historicalAfter = await db.query(`
    SELECT event_id::text AS event_id, operation_id::text AS operation_id,
           event_type, outcome, map_result_index
    FROM map_download_event WHERE event_id = $1
  `, [eventIds.map]);
  assert.deepEqual({
    event_id: historicalAfter.rows[0].event_id,
    operation_id: historicalAfter.rows[0].operation_id,
    event_type: historicalAfter.rows[0].event_type,
    outcome: historicalAfter.rows[0].outcome,
  }, historicalBefore.rows[0]);
  assert.equal(historicalAfter.rows[0].map_result_index, null);

  const ledger = await db.query('SELECT version FROM schema_migrations ORDER BY version');
  assert.deepEqual(ledger.rows.map(row => row.version), ['060', '061']);
  await db.close();
  return after.length;
}

async function alreadyReconciledIdempotency() {
  const db = await createFixture();
  await runStatements(db, input.migration062);
  const before = await viewColumns(db);
  await runStatements(db, input.migration062);
  await runStatements(db, input.migration062);
  assert.deepEqual(await viewColumns(db), before);
  await assertReconciled(db);
  const legacy = await db.query(`
    SELECT map_result_index FROM map_download_event WHERE event_id = $1
  `, [eventIds.map]);
  assert.equal(legacy.rows[0].map_result_index, null);
  await db.close();
}

async function operatorChecks() {
  const db = await createFixture();
  await db.exec(`
    INSERT INTO schema_migrations(version)
    SELECT lpad(version::text, 3, '0')
    FROM generate_series(1, 59) AS versions(version)
  `);

  await db.exec('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
  const precheck = await db.exec(input.precheck);
  assert.equal(precheck[0].rows[0].gate, 'ABORT 062');
  assert.match(precheck[0].rows[0].abort_reasons, /^target database\/schema\/read-only transaction:/);
  assert.doesNotMatch(precheck[0].rows[0].abort_reasons, /\n/);
  await db.exec('ROLLBACK');

  await runStatements(db, input.migration062);
  await db.exec("INSERT INTO schema_migrations(version) VALUES ('062')");
  const postcheckSql = input.postcheck
    .replace('(NULL::bigint, NULL::bigint)', '(2::bigint, 1::bigint)');
  await db.exec('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
  const postcheck = await db.exec(postcheckSql);
  assert.equal(postcheck[0].rows[0].gate, 'ABORT POSTCHECK');
  assert.match(postcheck[0].rows[0].abort_reasons, /^target database\/schema\/read-only transaction:/);
  assert.doesNotMatch(postcheck[0].rows[0].abort_reasons, /\n/);
  await db.exec('ROLLBACK');
  await db.close();
}

async function auditTablePostcheck() {
  const db = await createFixture();
  await db.exec(`
    INSERT INTO schema_migrations(version)
    SELECT lpad(version::text, 3, '0')
    FROM generate_series(1, 59) AS versions(version)
  `);
  await runStatements(db, input.migration062);
  await db.exec("INSERT INTO schema_migrations(version) VALUES ('062')");

  const runPostcheck = async () => {
    const sql = input.postcheck
      .replace("current_database() = 'terento_catalog'", 'TRUE')
      .replace('(NULL::bigint, NULL::bigint)', '(2::bigint, 1::bigint)');
    await db.exec('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
    const result = await db.exec(sql);
    await db.exec('ROLLBACK');
    return result[0].rows[0];
  };

  const valid = await runPostcheck();
  assert.equal(valid.gate, 'POSTCHECK PASS 062', valid.abort_reasons);

  await db.exec('ALTER TABLE statistics_exclusion_audit ALTER COLUMN source DROP NOT NULL');
  const nullableSource = await runPostcheck();
  assert.equal(nullableSource.gate, 'ABORT POSTCHECK');
  assert.match(nullableSource.abort_reasons, /audit table shape.*column_mismatches=[1-9]/);

  await db.exec('ALTER TABLE statistics_exclusion_audit ALTER COLUMN source SET NOT NULL');
  await db.exec(`
    ALTER TABLE statistics_exclusion_audit DROP CONSTRAINT statistics_exclusion_audit_stream_check;
    ALTER TABLE statistics_exclusion_audit
      ADD CONSTRAINT statistics_exclusion_audit_stream_check CHECK (stream IS NOT NULL)
  `);
  const permissiveCheck = await runPostcheck();
  assert.equal(permissiveCheck.gate, 'ABORT POSTCHECK');
  assert.match(permissiveCheck.abort_reasons, /audit table shape.*stream_check=f/);
  await db.close();
}

(async () => {
  const viewContract = await cleanMigrationPath();
  await liveLikeRepair();
  await alreadyReconciledIdempotency();
  await operatorChecks();
  await auditTablePostcheck();
  console.log(JSON.stringify({
    cleanMigration: 'PASS',
    liveLikeRepair: 'PASS',
    alreadyReconciled: 'PASS',
    operatorPrecheck: 'PASS (only the intentional PGlite database-name gate aborts)',
    operatorPostcheck: 'PASS (only the intentional PGlite database-name gate aborts)',
    auditTablePostcheck: 'PASS (valid shape accepted, nullable source and permissive stream CHECK rejected)',
    historicalMapIndex: 'NULL',
    viewColumns: viewContract.length,
    viewContract,
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
