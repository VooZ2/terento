"""Offline public payload contracts, shared with Swift and website consumers."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from terento_catalog.catalog import build_catalog, serialize_catalog
from terento_catalog.device_catalog import build_device_catalog, serialize_device_catalog
from terento_catalog.compatibility_evidence import ALLOWED_KEYS, EvidenceValidationError, validate_event
from terento_catalog.map_events import ALLOWED_EVENT_KEYS, MapEventValidationError, validate_map_event
from test_http_api import FakeDatabase
from test_compatibility_evidence import event as legacy_event

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / 'contracts'
FIXTURES = CONTRACTS / 'fixtures'
NAMES = ('map-catalog', 'device-catalog', 'compatibility-event', 'map-event')


def fixture(name):
    return json.loads((FIXTURES / f'{name}.json').read_text())


def validator(name):
    return Draft202012Validator(json.loads((CONTRACTS / f'{name}.schema.json').read_text()))


class SharedContractTests(unittest.TestCase):
    def test_schemas_and_all_shared_fixtures(self):
        self.assertEqual({p.stem.removesuffix('.schema') for p in CONTRACTS.glob('*.schema.json')}, set(NAMES))
        intended = {
            'map-catalog.invalid-missing-schema-version': ('required', [], 'schemaVersion'),
            'map-catalog.invalid-missing-providers': ('required', [], 'providers'),
            'device-catalog.invalid-missing-canonical-model': ('required', ['devices', 0], 'canonicalModel'),
            'compatibility-event.invalid-disallowed-field': ('additionalProperties', [], 'serialNumber'),
            'compatibility-event.invalid-inconsistent-success': ('enum', ['automaticFinishingResult'], 'VERIFIED'),
            'map-event.invalid-disallowed-field': ('additionalProperties', [], 'serialNumber'),
            'map-event.invalid-custom-provider': ('not', ['providerId'], 'custom'),
        }
        for name in NAMES:
            v = validator(name)
            v.check_schema(v.schema)
            self.assertEqual(v.schema['$id'], f'{name}.schema.json')
            # All references stay within the file, so validation cannot fetch a URL.
            def check_refs(value):
                if isinstance(value, dict):
                    if '$ref' in value:
                        self.assertTrue(value['$ref'].startswith('#/$defs/'))
                    for child in value.values():
                        check_refs(child)
                elif isinstance(value, list):
                    for child in value:
                        check_refs(child)
            check_refs(v.schema)
            for path in FIXTURES.glob(f'{name}.*.json'):
                with self.subTest(fixture=path.name):
                    errors = list(v.iter_errors(fixture(path.stem)))
                    if '.valid' in path.stem:
                        self.assertEqual(errors, [])
                    else:
                        kind, location, detail = intended[path.stem]
                        self.assertTrue(any(e.validator == kind and list(e.absolute_path) == location and detail in e.message for e in errors), errors)

    def test_backend_serialized_projections(self):
        database = FakeDatabase()
        for name, builder, serializer, snapshot in (
            ('map-catalog', build_catalog, serialize_catalog, database.catalog_snapshot()),
            ('device-catalog', build_device_catalog, serialize_device_catalog, database.device_catalog_snapshot()),
        ):
            validator(name).validate(json.loads(serializer(builder(*snapshot))))
            rows, timestamp = copy.deepcopy(snapshot)
            if name == 'map-catalog':
                rows[0]['install_size_bytes'] = None
            else:
                rows[0]['asset_status'] = 'MISSING'
                rows[0]['map_capable'] = None
                rows[0]['source_image_url'] = None
            validator(name).validate(json.loads(serializer(builder(rows, timestamp))))
        rows, timestamp = database.catalog_snapshot()
        base = rows[0]
        neutral = dict(base, package_id='freizeitkarte-deu', package_region='DE',
                       package_name='Germany', package_country='Germany',
                       release='2026-08', artifact_id='freizeitkarte-deu-main',
                       artifact_kind='main', artifact_source_url=base['source_url'],
                       artifact_size_bytes=12345, artifact_install_size_bytes=None)
        document = json.loads(serialize_catalog(build_catalog([neutral], timestamp)))
        validator('map-catalog').validate(document)
        self.assertEqual(document['providers'][0]['maps'][0]['availability'], 'AVAILABLE')

    def test_events_match_current_allowlists_and_acceptance(self):
        self.assertEqual(set(validator('compatibility-event').schema['properties']), ALLOWED_KEYS)
        self.assertEqual(set(validator('map-event').schema['properties']), ALLOWED_EVENT_KEYS)
        for name, validate, error in (
            ('compatibility-event', validate_event, EvidenceValidationError),
            ('map-event', validate_map_event, MapEventValidationError),
        ):
            value = fixture(f'{name}.valid')
            validator(name).validate(value)
            validate(json.dumps(value).encode())
            for path in FIXTURES.glob(f'{name}.invalid-*.json'):
                with self.subTest(fixture=path.name), self.assertRaises(error):
                    validate(path.read_bytes())
        for version in (1, 2, 3, 4):
            value = legacy_event(schemaVersion=version) if version < 3 else fixture('compatibility-event.valid')
            value['schemaVersion'] = version
            if version == 3:
                value['deletionToken'] = 'a' * 64
            validator('compatibility-event').validate(value)
            validate_event(json.dumps(value).encode())
        for changes in (
            {'provider': 'CUSTOM', 'region': 'custom', 'mapRelease': 'custom'},
            {'phaseOutcome': 'FAILED', 'automaticFinishingResult': 'FAILED', 'failureStage': 'write', 'failureCode': 'INSTALL_FAILED_WRITE'},
            {'phaseOutcome': 'NOT_STARTED', 'automaticFinishingResult': 'NOT_REACHED', 'writeStarted': False, 'remoteObjectCreated': False, 'failureStage': 'preflight', 'failureCode': 'INSTALL_NOT_STARTED_AFTER_EARLIER_FAILURE'},
        ):
            value = dict(fixture('compatibility-event.valid'), **changes)
            validator('compatibility-event').validate(value)
            validate_event(json.dumps(value).encode())

    def test_existing_privacy_and_diagnostic_rejections(self):
        for changes in (
            {'model': '/Users/synthetic/watch'}, {'usbVendorID': 70000},
            {'rawMTPModel': 'model\nserial'}, {'identityResolutionCode': 'UNIT_ID:123'},
            {'releaseLabel': 'file:///Users/synthetic/build'},
            {'nativeFailureCode': 'RAW: log'}, {'remoteObjectCreated': True, 'writeStarted': False},
            {'cleanupSucceeded': True, 'cleanupAttempted': False},
            {'mapVisibleAfterReconnect': True, 'reconnectVerified': False},
            {'deletionToken': 'a' * 64}, {'selectedMapCount': 0},
        ):
            value = dict(fixture('compatibility-event.valid'), **changes)
            with self.subTest(changes=changes):
                self.assertFalse(validator('compatibility-event').is_valid(value))
                with self.assertRaises(EvidenceValidationError):
                    validate_event(json.dumps(value).encode())

    def test_procedural_server_constraints_remain_authoritative(self):
        # Draft 2020-12 has no general sibling-value comparison. Do not add $data.
        value = dict(fixture('compatibility-event.valid'), mapResultIndex=1, selectedMapCount=1)
        validator('compatibility-event').validate(value)
        with self.assertRaisesRegex(EvidenceValidationError, 'invalid_map_result_position'):
            validate_event(json.dumps(value).encode())
        for changes in ({'timestamp': '2026-09-01T12:00:00'}, {'id': 'invalid-uuid'}):
            with self.assertRaises(MapEventValidationError):
                validate_map_event(json.dumps(dict(fixture('map-event.valid'), **changes)).encode())

    def test_bundled_catalog_is_the_legacy_decoder_projection(self):
        path = ROOT / 'app/TerentoCore/Sources/TerentoPoC/Resources/Maps/catalog.json'
        bundled = json.loads(path.read_text())
        self.assertEqual(bundled['catalogVersion'], 1)
        self.assertNotIn('schemaVersion', bundled)
        self.assertIn('providers', bundled)
        self.assertIn('bundled', (CONTRACTS / 'README.md').read_text())
