-- 061 installation/statistics schema preflight. Run inside an already active
-- READ ONLY transaction against the intended DB. Only SELECT statements.
-- Catalog only: no application rows, credentials, event IDs or DDL are read.
-- A clean result is necessary, not sufficient: review all definitions below
-- against migrations 001-061 and current db.py before authorizing a migration.
-- In particular, schema_migrations.version=060 does not prove 060's objects.
SELECT current_database() AS database_name, current_schema() AS inspected_schema,
       current_setting('transaction_read_only') AS transaction_read_only,
       version() AS postgres_version;

-- Expected objects and code paths. 011 intentionally dropped
-- compatibility_evidence_confirmation; its absence is not drift.
WITH expected(object_name, kind, code_path, required_migration) AS (
  VALUES
    ('schema_migrations','r','migrate.py migration ordering','001/bootstrap'),
    ('compatibility_evidence_event','r','compatibility_evidence.py; db.py ingest, result aggregation, review','009, 011-060'),
    ('map_download_event','r','map_events.py; db.py ingestion, statistics, result linkage','026, 035, 049, 055, 060-061'),
    ('statistics_exclusion_audit','r','db.py exclusion audit persistence','060 or 061'),
    ('compatibility_model_review','r','db.py public review; compatibility_model_statistics','009, 010, 012, 013, 023'),
    ('compatibility_evidence_identity_correction','r','db.py historical identity audit','013'),
    ('compatibility_diagnostic_lifecycle_audit','r','db.py diagnostic review audit','021, 040'),
    ('compatibility_identity_resolution_audit','r','db.py identity review audit','021, 047'),
    ('compatibility_device_card_failure_epoch','r','db.py device card denominator','025'),
    ('public_compatibility_review_audit','r','db.py publication review audit','023'),
    ('device_authorization_audit','r','db.py support-status review audit','021'),
    ('device_identity_mapping','r','db.py identity assessment/review','047'),
    ('device_identity_mapping_audit','r','db.py mapping review audit','047'),
    ('device_identity_source_correction','r','db.py source correction audit','047'),
    ('device_model','r','installation_policy.py; compatibility_model_statistics; review','002, 013-047'),
    ('device_family','r','device catalog identity','002'),
    ('device_usb_identity','r','reviewed hardware identity','002'),
    ('device_collection_run','r','device_model collection provenance FK','002, 014'),
    ('map_provider','r','map_download_event FK; map statistics labels','001, 026'),
    ('map','r','map_package legacy_map_id FK','001, 026'),
    ('map_package','r','map_download_event FK; map result region identity','026, later metadata'),
    ('admin_user','r','review/audit actor FKs','010'),
    ('admin_session','r','authenticated review session','010'),
    ('admin_audit_log','r','db.py operator audit','026'),
    ('compatibility_model_statistics','v','db.py compatibility and public statistics read model','060 view replacement')
), live AS (
  SELECT e.*, c.oid, c.relkind, n.nspname
  FROM expected e LEFT JOIN pg_namespace n ON n.nspname = current_schema()
  LEFT JOIN pg_class c ON c.relnamespace = n.oid AND c.relname = e.object_name
)
SELECT object_name AS object, kind AS expected,
       COALESCE(nspname || '.' || object_name || ' (' || relkind::text || ')','MISSING') AS live,
       CASE WHEN oid IS NULL THEN 'MISSING'
            WHEN relkind = kind THEN 'MATCH' ELSE 'DIFFERENT' END AS match,
       code_path AS required_by_code_path, required_migration
FROM live ORDER BY object_name;

-- Whole-column inventory, including type, NULL/default, identity/generated
-- state and ordinal. Output includes *every* live column on scoped relations,
-- so unexpected columns and unexpected nullable/default changes are visible.
-- The expected columns checked below are the current-code boundary fields;
-- compare all remaining live rows with the named source migrations above.
WITH scope(name) AS (VALUES
  ('schema_migrations'),('compatibility_evidence_event'),('map_download_event'),
  ('statistics_exclusion_audit'),('compatibility_model_review'),
  ('compatibility_evidence_identity_correction'),('compatibility_diagnostic_lifecycle_audit'),
  ('compatibility_identity_resolution_audit'),('compatibility_device_card_failure_epoch'),
  ('public_compatibility_review_audit'),('device_authorization_audit'),
  ('device_identity_mapping'),('device_identity_mapping_audit'),
  ('device_identity_source_correction'),('device_model'),('device_family'),
  ('device_usb_identity'),('device_collection_run'),('map_provider'),('map'),
  ('map_package'),('admin_user'),('admin_session'),('admin_audit_log'),
  ('compatibility_model_statistics')
)
SELECT c.relname AS object, a.attnum AS ordinal, a.attname AS column_name,
       format_type(a.atttypid,a.atttypmod) AS live_type,
       NOT a.attnotnull AS live_nullable,
       pg_get_expr(d.adbin,d.adrelid) AS live_default,
       a.attidentity AS identity_kind, a.attgenerated AS generated_kind
FROM scope s JOIN pg_namespace n ON n.nspname=current_schema()
JOIN pg_class c ON c.relnamespace=n.oid AND c.relname=s.name
JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
ORDER BY c.relname,a.attnum;

-- Machine-check the columns on which 060/061 and current statistics code
-- depend. Each specification is: relation, column, format_type, nullable,
-- default (NULL means no default). Historical event index MUST be nullable.
WITH expected(object_name,column_name,expected_type,nullable,expected_default,code_path,required_migration) AS (
  VALUES
  ('compatibility_evidence_event','event_id','uuid',false,NULL,'ingest idempotency','009'),
  ('compatibility_evidence_event','occurred_at','timestamp with time zone',false,NULL,'event time','009'),
  ('compatibility_evidence_event','received_at','timestamp with time zone',false,'now()','receipt time','009'),
  ('compatibility_evidence_event','model','text',false,NULL,'reported identity','009'),
  ('compatibility_evidence_event','compatibility_identity','text',false,NULL,'review identity','012'),
  ('compatibility_evidence_event','variant','text',true,NULL,'review identity','012'),
  ('compatibility_evidence_event','case_size_mm','integer',true,NULL,'review identity','012'),
  ('compatibility_evidence_event','display_type','text',true,NULL,'review identity','013'),
  ('compatibility_evidence_event','operation_id','uuid',true,NULL,'result grouping/linkage','017'),
  ('compatibility_evidence_event','map_result_index','integer',true,NULL,'result grouping/linkage','017'),
  ('compatibility_evidence_event','selected_map_count','integer',true,NULL,'result grouping','017'),
  ('compatibility_evidence_event','provider','text',false,NULL,'result provider identity','009/029'),
  ('compatibility_evidence_event','region','text',false,NULL,'result region identity','009'),
  ('compatibility_evidence_event','phase_outcome','text',false,NULL,'fresh install classification','009/017'),
  ('compatibility_evidence_event','automatic_finishing_result','text',false,NULL,'fresh install success','009'),
  ('compatibility_evidence_event','reconnect_verified','boolean',false,'false','successful result evidence','012'),
  ('compatibility_evidence_event','firmware_version','text',true,NULL,'compatibility coverage','009'),
  ('compatibility_evidence_event','error_category','text',true,NULL,'failure category statistics','009'),
  ('compatibility_evidence_event','failure_stage','text',true,NULL,'failure category statistics','017'),
  ('compatibility_evidence_event','failure_code','text',true,NULL,'failure category statistics','017'),
  ('compatibility_evidence_event','app_build','text',true,NULL,'legacy failure classification','017'),
  ('compatibility_evidence_event','release_label','text',true,NULL,'legacy failure classification','017'),
  ('compatibility_evidence_event','write_started','boolean',true,NULL,'prewrite exclusion/classification','017'),
  ('compatibility_evidence_event','remote_object_created','boolean',true,NULL,'exclusion security guard','017'),
  ('compatibility_evidence_event','cleanup_attempted','boolean',true,NULL,'diagnostic review','017'),
  ('compatibility_evidence_event','cleanup_succeeded','boolean',true,NULL,'diagnostic review','017'),
  ('compatibility_evidence_event','transfer_progress_bucket','text',true,NULL,'diagnostic review','017'),
  ('compatibility_evidence_event','diagnostic_status','text',false,'''ACTIVE''::text','compatibility view','019'),
  ('compatibility_evidence_event','diagnostic_workflow_status','text',false,'''OPEN''::text','review queue','040'),
  ('compatibility_evidence_event','is_local_test','boolean',false,'false','public statistics filter','035'),
  ('compatibility_evidence_event','statistics_exclusion_code','text',true,NULL,'all statistics filters','060'),
  ('compatibility_evidence_event','statistics_exclusion_reason','text',true,NULL,'exclusion evidence','060'),
  ('compatibility_evidence_event','security_issue_code','text',true,NULL,'security review','060'),
  ('compatibility_evidence_event','canonical_device_model_id','text',true,NULL,'device aggregation','013'),
  ('compatibility_evidence_event','identity_assessment','jsonb',true,NULL,'device aggregation','047'),
  ('compatibility_evidence_event','failure_context','jsonb',true,NULL,'failure review','059'),
  ('compatibility_evidence_event','original_failure_context','jsonb',true,NULL,'failure review','059'),
  ('map_download_event','event_id','uuid',false,NULL,'ingest idempotency/review','026'),
  ('map_download_event','operation_id','uuid',false,NULL,'result linkage','026'),
  ('map_download_event','map_result_index','integer',true,NULL,'result linkage; legacy NULL retained','060 or 061'),
  ('map_download_event','acquisition_id','uuid',true,NULL,'component lifecycle','049'),
  ('map_download_event','component_kind','text',true,NULL,'component lifecycle','049'),
  ('map_download_event','provider_id','text',false,NULL,'provider statistics','026'),
  ('map_download_event','map_package_id','text',true,NULL,'region/map identity','026'),
  ('map_download_event','region','text',true,NULL,'region/map identity','026'),
  ('map_download_event','event_type','text',false,NULL,'statistics population','026/049/055'),
  ('map_download_event','outcome','text',false,NULL,'statistics population','026'),
  ('map_download_event','occurred_at','timestamp with time zone',false,NULL,'statistics time','026'),
  ('map_download_event','received_at','timestamp with time zone',false,'now()','ingest audit','026'),
  ('map_download_event','app_build','text',true,NULL,'version statistics','026'),
  ('map_download_event','release_label','text',true,NULL,'local test classification','035'),
  ('map_download_event','is_local_test','boolean',false,'false','public statistics filter','035'),
  ('map_download_event','statistics_exclusion_code','text',true,NULL,'all statistics filters','060'),
  ('map_download_event','statistics_exclusion_reason','text',true,NULL,'exclusion evidence','060'),
  ('map_download_event','security_issue_code','text',true,NULL,'security review','060'),
  ('statistics_exclusion_audit','id','bigint',false,'nextval','exclusion audit PK','060 or 061'),
  ('statistics_exclusion_audit','stream','text',false,NULL,'audit stream','060 or 061'),
  ('statistics_exclusion_audit','event_id','uuid',false,NULL,'audit event identity','060 or 061'),
  ('statistics_exclusion_audit','exclusion_code','text',false,NULL,'audit exclusion identity','060 or 061'),
  ('statistics_exclusion_audit','reason','text',false,NULL,'audit reason','060 or 061'),
  ('statistics_exclusion_audit','security_issue_code','text',true,NULL,'audit security issue','060 or 061'),
  ('statistics_exclusion_audit','source','text',false,NULL,'audit provenance','060 or 061'),
  ('statistics_exclusion_audit','created_at','timestamp with time zone',false,'now()','audit timestamp','060 or 061'),
  ('compatibility_model_review','identity_key','text',true,NULL,'publication review join','012'),
  ('compatibility_model_review','model','text',false,NULL,'legacy review identity','009'),
  ('compatibility_model_review','review_status','text',false,'''PENDING''::text','publication review','009'),
  ('compatibility_model_review','physical_device_evidence_count','integer',false,'0','review evidence','009'),
  ('compatibility_model_review','review_notes','text',false,'''\'\'''::text','review display','009'),
  ('compatibility_model_review','public_statistics_enabled','boolean',false,'false','publication gate','010/013'),
  ('compatibility_model_review','public_display_name','text',true,NULL,'public display','010'),
  ('compatibility_model_review','updated_at','timestamp with time zone',false,'now()','review precedence','009'),
  ('device_model','id','text',false,NULL,'canonical identity FK','002'),
  ('device_model','active','boolean',false,'true','installation policy','002'),
  ('device_model','map_capable','boolean',true,NULL,'installation policy/statistics','013/021'),
  ('device_model','support_status','text',false,'''NOT_EVALUATED''::text','operator metadata','014/021'),
  ('map_package','id','text',false,NULL,'map result FK','026'),
  ('map_package','provider_region_id','text',false,NULL,'map result region identity','026'),
  ('map_package','canonical_region_id','text',false,NULL,'map result region identity','026'),
  ('map_package','region','text',false,NULL,'map result region identity','026'),
  ('map_package','map_type','text',true,NULL,'map statistics grouping','044'),
  ('map_package','geographic_region_id','text',true,NULL,'map statistics grouping','later region migration')
), live AS (
 SELECT e.*,a.attname,format_type(a.atttypid,a.atttypmod) AS live_type,
        NOT a.attnotnull AS live_nullable,pg_get_expr(d.adbin,d.adrelid) AS live_default
 FROM expected e LEFT JOIN pg_namespace n ON n.nspname=current_schema()
 LEFT JOIN pg_class c ON c.relnamespace=n.oid AND c.relname=e.object_name
 LEFT JOIN pg_attribute a ON a.attrelid=c.oid AND a.attname=e.column_name
                         AND a.attnum>0 AND NOT a.attisdropped
 LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
)
SELECT object_name||'.'||column_name AS object,
       expected_type||' '||CASE WHEN nullable THEN 'NULL' ELSE 'NOT NULL' END||
         COALESCE(' DEFAULT '||expected_default,'') AS expected,
       COALESCE(live_type||' '||CASE WHEN live_nullable THEN 'NULL' ELSE 'NOT NULL' END||
         COALESCE(' DEFAULT '||live_default,''),'MISSING') AS live,
       CASE WHEN attname IS NULL THEN 'MISSING'
            WHEN live_type<>expected_type OR live_nullable IS DISTINCT FROM nullable
              OR (CASE WHEN expected_default='nextval' THEN NOT COALESCE(live_default LIKE 'nextval(%',false)
                       ELSE live_default IS DISTINCT FROM expected_default END)
              THEN 'DIFFERENT' ELSE 'MATCH' END AS match,
       code_path AS required_by_code_path,required_migration
FROM live ORDER BY object_name,column_name;

-- Full index inventory: definitions, uniqueness, validity/readiness, attached
-- constraints and partial predicates. A same-named index with another shape
-- does not satisfy the migration contract.
SELECT t.relname AS object, i.relname AS index_name, pg_get_indexdef(i.oid) AS definition,
       x.indisunique AS is_unique,x.indisprimary AS is_primary,
       x.indisvalid AS is_valid,x.indisready AS is_ready,
       pg_get_expr(x.indpred,x.indrelid) AS predicate,
       co.conname AS attached_constraint
FROM pg_namespace n JOIN pg_class t ON t.relnamespace=n.oid
JOIN pg_index x ON x.indrelid=t.oid JOIN pg_class i ON i.oid=x.indexrelid
LEFT JOIN pg_constraint co ON co.conindid=i.oid
WHERE n.nspname=current_schema() AND t.relname IN (
 'compatibility_evidence_event','map_download_event','statistics_exclusion_audit',
 'compatibility_model_review','compatibility_evidence_identity_correction',
 'compatibility_diagnostic_lifecycle_audit','compatibility_identity_resolution_audit',
 'compatibility_device_card_failure_epoch','public_compatibility_review_audit',
 'device_authorization_audit','device_identity_mapping','device_identity_mapping_audit',
 'device_identity_source_correction','device_model','device_usb_identity',
 'device_collection_run','map','map_package','map_provider','admin_audit_log',
 'admin_user','admin_session')
ORDER BY t.relname,i.relname;

-- Assert key index names separately; compare their shapes in the inventory.
WITH expected(object_name,index_name,code_path,required_migration) AS (VALUES
 ('compatibility_evidence_event','compatibility_evidence_event_pkey','event idempotency','009'),
 ('compatibility_evidence_event','compatibility_evidence_operation_idx','operation linkage','017'),
 ('compatibility_evidence_event','compatibility_statistics_exclusion_idx','exclusion filtering','060'),
 ('map_download_event','map_download_event_pkey','event idempotency','026'),
 ('map_download_event','map_download_event_legacy_dedup_idx','legacy deduplication','049'),
 ('map_download_event','map_download_event_acquisition_phase_idx','acquisition phase deduplication','049'),
 ('map_download_event','map_download_event_acquisition_terminal_idx','terminal deduplication','049'),
 ('map_download_event','map_statistics_exclusion_idx','exclusion filtering','060'),
 ('statistics_exclusion_audit','statistics_exclusion_audit_pkey','audit identity','060 or 061'),
 ('statistics_exclusion_audit','statistics_exclusion_audit_stream_event_id_exclusion_code_key','audit deduplication','060 or 061'),
 ('statistics_exclusion_audit','statistics_exclusion_audit_event_idx','audit lookup','060 or 061'),
 ('compatibility_model_review','compatibility_model_review_identity_idx','review identity','012')
)
SELECT e.object_name||'.'||e.index_name AS object,'valid index' AS expected,
       COALESCE(pg_get_indexdef(i.oid),'MISSING') AS live,
       CASE WHEN i.oid IS NULL THEN 'MISSING'
            WHEN x.indisvalid AND x.indisready THEN 'MATCH_NAME_AND_VALIDITY; REVIEW_SHAPE'
            ELSE 'DIFFERENT' END AS match,
       e.code_path AS required_by_code_path,e.required_migration
FROM expected e LEFT JOIN pg_namespace n ON n.nspname=current_schema()
LEFT JOIN pg_class t ON t.relnamespace=n.oid AND t.relname=e.object_name
LEFT JOIN pg_class i ON i.relnamespace=n.oid AND i.relname=e.index_name AND i.relkind='i'
LEFT JOIN pg_index x ON x.indrelid=t.oid AND x.indexrelid=i.oid
ORDER BY e.object_name,e.index_name;

-- Every unique/check/FK/PK constraint and its enforcement properties. Also
-- inspect FKs *into* the scoped relations before interpreting any missing FK.
SELECT t.relname AS object,co.conname,co.contype,
       pg_get_constraintdef(co.oid,true) AS definition,co.convalidated,
       co.condeferrable,co.condeferred,
       referenced.relname AS referenced_table,
       co.confdeltype AS on_delete_code
FROM pg_namespace n JOIN pg_class t ON t.relnamespace=n.oid
JOIN pg_constraint co ON co.conrelid=t.oid
LEFT JOIN pg_class referenced ON referenced.oid=co.confrelid
WHERE n.nspname=current_schema() AND (t.relname IN (
 'compatibility_evidence_event','map_download_event','statistics_exclusion_audit',
 'compatibility_model_review','compatibility_evidence_identity_correction',
 'compatibility_diagnostic_lifecycle_audit','compatibility_identity_resolution_audit',
 'public_compatibility_review_audit','device_authorization_audit',
 'device_identity_mapping','device_identity_mapping_audit','device_identity_source_correction',
 'device_model','device_usb_identity','device_collection_run','map',
 'map_provider','map_package','admin_audit_log','admin_user','admin_session')
 OR referenced.relname IN ('compatibility_evidence_event','map_download_event','device_model','map_package'))
ORDER BY t.relname,co.contype,co.conname;

-- Expected constraints most liable to drift. Check full definitions above,
-- including action, key order, CHECK values and validation; names alone do
-- not establish parity.
WITH expected(object_name,constraint_name,code_path,required_migration) AS (VALUES
 ('map_download_event','map_download_event_provider_id_fkey','provider identity','026'),
 ('map_download_event','map_download_event_map_package_id_fkey','package identity','026'),
 ('map_download_event','map_download_event_acquisition_pair','component identity','049'),
 ('map_download_event','map_download_event_event_type_check','event allowlist','055'),
 ('statistics_exclusion_audit','statistics_exclusion_audit_stream_check','stream allowlist','060 or 061'),
 ('statistics_exclusion_audit','statistics_exclusion_audit_stream_event_id_exclusion_code_key','audit uniqueness','060 or 061'),
 ('compatibility_evidence_event','compatibility_evidence_event_canonical_device_model_id_fkey','canonical identity','013'),
 ('compatibility_evidence_event','compatibility_evidence_event_phase_outcome_check','result state','017')
)
SELECT e.object_name||'.'||e.constraint_name AS object,'validated constraint' AS expected,
       COALESCE(pg_get_constraintdef(co.oid,true),'MISSING') AS live,
       CASE WHEN co.oid IS NULL THEN 'MISSING'
            WHEN co.convalidated THEN 'MATCH_NAME_AND_VALIDITY; REVIEW_DEFINITION'
            ELSE 'DIFFERENT' END AS match,
       e.code_path AS required_by_code_path,e.required_migration
FROM expected e LEFT JOIN pg_namespace n ON n.nspname=current_schema()
LEFT JOIN pg_class t ON t.relnamespace=n.oid AND t.relname=e.object_name
LEFT JOIN pg_constraint co ON co.conrelid=t.oid AND co.conname=e.constraint_name
ORDER BY e.object_name,e.constraint_name;

-- All views/materialized views in this schema; report the entire definition
-- of the statistics projection and any other view depending on scope tables.
-- pg_depend is included because a view may reference the same table without
-- mentioning it by name in its final output.
SELECT v.relname AS object,
       CASE v.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW' END AS kind,
       pg_get_viewdef(v.oid,true) AS definition,
       array_remove(array_agg(DISTINCT base.relname),NULL) AS dependent_on,
       CASE WHEN v.relname='compatibility_model_statistics' THEN
         CASE WHEN position('statistics_exclusion_code' IN pg_get_viewdef(v.oid))>0
                AND position('map_result_index' IN pg_get_viewdef(v.oid))>0
              THEN 'TEXT MARKERS PRESENT; REVIEW FULL SEMANTICS'
              ELSE 'DIFFERENT OR UNVERIFIED: 060 FILTER/RESULT MARKER MISSING' END
         ELSE 'REVIEW IF RELATED' END AS assessment
FROM pg_namespace n JOIN pg_class v ON v.relnamespace=n.oid AND v.relkind IN ('v','m')
LEFT JOIN pg_rewrite rw ON rw.ev_class=v.oid
LEFT JOIN pg_depend dep ON dep.objid=rw.oid AND dep.refclassid='pg_class'::regclass
LEFT JOIN pg_class base ON base.oid=dep.refobjid AND base.oid<>v.oid
WHERE n.nspname=current_schema()
GROUP BY v.oid,v.relname,v.relkind
ORDER BY v.relname;

-- Function contract used by the derived view.
SELECT p.proname AS object,pg_get_function_identity_arguments(p.oid) AS arguments,
       pg_get_function_result(p.oid) AS result_type,
       pg_get_functiondef(p.oid) AS definition
FROM pg_namespace n JOIN pg_proc p ON p.pronamespace=n.oid
WHERE n.nspname=current_schema() AND p.proname='terento_compatibility_status';
