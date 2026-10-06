// Line-delimited JSON bridge used by pglite_support.py.
//
// It applies the real catalog migrations to an in-memory PostgreSQL/WASM
// instance and then executes the exact SQL issued by terento_catalog.db. It is
// a test harness only and never connects to a production database.
const {PGlite} = require(process.argv[2]);
const readline = require('node:readline');

function encode(value) {
  if (value instanceof Date) return {$date: value.toISOString()};
  if (typeof value === 'bigint') return value.toString();
  if (value instanceof Uint8Array) return {$bytes: Buffer.from(value).toString('base64')};
  if (Array.isArray(value)) return value.map(encode);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, encode(item)]));
  }
  return value;
}

(async () => {
  const db = new PGlite();
  await db.waitReady;
  const reader = readline.createInterface({input: process.stdin, crlfDelay: Infinity});
  const reply = (payload) => process.stdout.write(JSON.stringify(payload) + '\n');
  for await (const line of reader) {
    if (!line.trim()) continue;
    let request;
    try {
      request = JSON.parse(line);
      if (request.op === 'close') {
        reply({ok: true});
        break;
      }
      if (request.op === 'exec') {
        await db.exec(request.sql);
        reply({ok: true});
        continue;
      }
      if (request.op === 'migrate') {
        await db.exec('BEGIN');
        try {
          for (const statement of request.statements) await db.exec(statement);
          await db.exec('COMMIT');
        } catch (error) {
          await db.exec('ROLLBACK');
          throw error;
        }
        reply({ok: true});
        continue;
      }
      const started = process.hrtime.bigint();
      const result = await db.query(request.sql, request.params || []);
      const elapsed = Number(process.hrtime.bigint() - started) / 1e6;
      reply({
        ok: true,
        rows: encode(result.rows),
        fields: result.fields.map((field) => ({name: field.name, type: field.dataTypeID})),
        affectedRows: result.affectedRows ?? 0,
        elapsedMs: elapsed,
      });
    } catch (error) {
      reply({ok: false, error: String(error && error.message || error), code: error && error.code});
    }
  }
  await db.close();
  process.exit(0);
})().catch((error) => {
  process.stderr.write(String(error && error.stack || error) + '\n');
  process.exit(1);
});
