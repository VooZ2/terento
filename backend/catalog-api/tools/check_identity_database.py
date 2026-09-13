"""Identity transactions exercised only by the guarded disposable CI database."""
import json
from pathlib import Path
from uuid import uuid4

from terento_catalog.compatibility_evidence import validate_event


def check_identity_database(database):
    from urllib.parse import urlparse
    assert urlparse(database.dsn).path == '/terento_ci'
    from terento_catalog.migrate import _statements
    from terento_catalog.db import migration_directory
    with database.connection() as c:
        family = c.execute('SELECT family_id FROM device_model LIMIT 1').fetchone()['family_id']
        c.execute('''INSERT INTO device_model (id,family_id,manufacturer,model,canonical_model,variant,
            case_size_mm,display_type,part_number,product_url,source_url)
            VALUES ('garmin-fenix-9-pro-51-inreach',%s,'Garmin','fēnix 9 Pro','fenix 9 pro','inReach, 51 mm',
                    51,NULL,'010-preserved','https://www.garmin.com/en-US/p/1953453/','https://www.garmin.com/')
            ON CONFLICT DO NOTHING''', (family,))
        assignments = c.execute('SELECT event_id,canonical_device_model_id FROM compatibility_evidence_event ORDER BY event_id').fetchall()
        identifiers = c.execute('SELECT id FROM device_model ORDER BY id').fetchall()
        for statement in _statements((migration_directory() / '048_reviewed_garmin_specifications.sql').read_text()):
            c.execute(statement)
        row = c.execute("SELECT * FROM device_model WHERE id='garmin-fenix-9-pro-51-inreach'").fetchone()
        assert row['screen_technology'] == 'AMOLED' and row['inreach'] is True and row['solar'] is None
        assert row['display_type'] is None and row['part_number'] == '010-preserved'
        assert row['specification_evidence']['display_resolution']['value'] == '466 x 466 pixels'
        assert assignments == c.execute('SELECT event_id,canonical_device_model_id FROM compatibility_evidence_event ORDER BY event_id').fetchall()
        assert identifiers == c.execute('SELECT id FROM device_model ORDER BY id').fetchall()
        skus = c.execute("SELECT status FROM device_identity_mapping WHERE device_model_id=%s AND kind='RETAIL_SKU'", (row['id'],)).fetchall()
        assert len(skus) == 4 and all(m['status'] == 'APPROVED' for m in skus)
        assert not c.execute("SELECT 1 FROM device_identity_mapping WHERE device_model_id=%s AND value='006-B4953-00'", (row['id'],)).fetchone()
    print('PASS: reviewed SKU/specification seed preserves IDs, legacy fields and assignments; exact case-size import scope')
    fixture = json.loads((Path(__file__).resolve().parents[3] / 'contracts/fixtures/compatibility-event.valid.json').read_text())
    with database.connection() as c:
        admin = c.execute("INSERT INTO admin_user (username,password_hash) VALUES ('identity-ci','not-a-login-hash') RETURNING id").fetchone()['id']
        family = c.execute('SELECT family_id FROM device_model LIMIT 1').fetchone()['family_id']
        for technology in ('AMOLED', 'MicroLED'):
            c.execute('''INSERT INTO device_model (id,family_id,manufacturer,model,canonical_model,variant,
                case_size_mm,display_type,screen_technology,solar,inreach,product_url,source_url,map_capable)
                VALUES (%s,%s,'Garmin','Identity CI Watch','identity ci watch',%s,51,%s,%s,false,true,
                'https://example.org/ci','https://example.org/ci',true)''',
                ('identity-ci-' + technology.lower(), family, technology, technology, technology))
        for kind, value in [('XML_PART_NUMBER', '006-B9999-00'), ('USB', '091e:ffff')]:
            for technology in ('AMOLED', 'MicroLED'):
                c.execute('''INSERT INTO device_identity_mapping (kind,value,device_model_id,source_url,source_version)
                    VALUES (%s,%s,%s,'https://example.org/synthetic','ci')''', (kind, value, 'identity-ci-' + technology.lower()))
        mappings = c.execute("SELECT id FROM device_identity_mapping WHERE source_version='ci'").fetchall()
    def send(**changes):
        event = dict(fixture, id=str(uuid4()), operationId=str(uuid4()), model='Identity CI Watch',
                     rawMTPModel='Identity CI Watch 51mm AMOLED inReach',
                     garminModelDescription='Identity CI Watch 51mm AMOLED inReach',
                     garminModelPartNumber='006-B9999-00', usbProductID=65535, **changes)
        # Public-labelled synthetic fixtures are confined to this disposable DB.
        value = validate_event(json.dumps(event).encode())
        assert database.insert_compatibility_event(value)
        assert not database.insert_compatibility_event(value)
        with database.connection() as c:
            return c.execute('SELECT * FROM compatibility_evidence_event WHERE event_id=%s', (event['id'],)).fetchone()
    pending = send()
    assert pending['canonical_device_model_id'] is None
    for mapping in mappings:
        database.review_identity_mapping(mapping['id'], 'APPROVED', 'Synthetic fixture review', admin)
    exact = send()
    assert exact['canonical_device_model_id'] == 'identity-ci-amoled', exact['identity_assessment']
    assert exact['garmin_model_part_number'] == '006-B9999-00'
    assert all(ch['state'] == 'MATCH' for ca in exact['identity_assessment']['candidates'] if ca['deviceId'] == 'identity-ci-amoled' for ch in ca['checks'])
    # A checked assignment never silently rewrites a pre-existing event.
    with database.connection() as c:
        assert c.execute('SELECT canonical_device_model_id FROM compatibility_evidence_event WHERE event_id=%s', (pending['event_id'],)).fetchone()['canonical_device_model_id'] is None
        c.execute("INSERT INTO compatibility_model_review (model,identity_key,review_status,public_statistics_enabled) VALUES ('Identity CI Watch','Identity CI Watch','APPROVED',true)")
    incomplete = dict(fixture, id=str(uuid4()), operationId=str(uuid4()), model='Identity CI Watch',
                      canonicalDeviceId='identity-ci-amoled', usbProductID=65535)
    assert database.insert_compatibility_event(validate_event(json.dumps(incomplete).encode()))
    public = database.public_compatibility_statistics(500)
    assert not any(r['canonical_device_model_id'] is None and r['canonical_model'] == 'Identity CI Watch' for r in public)
    # Wrong client and manual selections encounter the same contradiction.
    try:
        database.resolve_compatibility_identity(str(exact['operation_id']), action='ASSIGN',
            canonical_device_model_id='identity-ci-microled', admin_user_id=admin, reason='Cannot override a conflict')
        raise AssertionError('conflict accepted')
    except ValueError:
        pass
    for field in ('rawMTPModel', 'garminModelDescription'):
        database.correct_identity_source(str(exact['event_id']), field, 'Identity CI Watch 51mm MicroLED inReach', 'Synthetic corrected source', admin)
    with database.connection() as c:
        original = c.execute('SELECT * FROM compatibility_evidence_event WHERE event_id=%s', (exact['event_id'],)).fetchone()
        assert original['canonical_device_model_id'] == 'identity-ci-amoled'
        assert original['garmin_model_description'].endswith('AMOLED inReach')
    database.resolve_compatibility_identity(str(exact['operation_id']), action='ASSIGN',
        canonical_device_model_id='identity-ci-microled', admin_user_id=admin, reason='Two audited source corrections')
    details = database.compatibility_operation_details()
    corrected = next(r for r in details if r['event_id'] == exact['event_id'])
    assert corrected['identity_decision']['decision']['method'] == 'ADMIN'
    assert corrected['identity_assessment'] == exact['identity_assessment']
    assert corrected['canonical_device_model_id'] == 'identity-ci-microled'
    assert len(corrected['identity_source_corrections']) == 2
    with database.connection() as c:
        assert c.execute('SELECT count(*) AS n FROM device_identity_mapping_audit WHERE mapping_id = ANY(%s)',
                         ([m['id'] for m in mappings],)).fetchone()['n'] == 4
        assert c.execute('SELECT count(*) AS n FROM compatibility_identity_resolution_audit WHERE event_id=%s', (exact['event_id'],)).fetchone()['n'] == 1
    # Additive projections and original retail fields remain readable.
    database.device_catalog_snapshot()
    rows, sync = database.admin_device_snapshot()
    from terento_catalog.admin import devices_page
    assert b"Review assignment audit" in devices_page(rows, sync, {"username": "CI owner"}, "csrf")
    audit = database.identity_assignment_audit()
    assert audit['readOnly'] and audit['approvalRequiredBeforeReassignment']
    assert audit['counterImpact']
    database.public_compatibility_models(500)
    print('PASS: PostgreSQL identity intake, replay, five checks, shared codes, manual conflict, corrections, audit and public-count isolation')
