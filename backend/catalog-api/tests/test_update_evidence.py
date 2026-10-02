from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from terento_catalog.compatibility_evidence import EvidenceValidationError, validate_event
from terento_catalog.db import Database

CONTRACTS = Path(__file__).resolve().parents[3] / 'contracts'
SCHEMA = Draft202012Validator(json.loads((CONTRACTS / 'compatibility-event.schema.json').read_text()))


def update_event(**changes):
    value = json.loads((CONTRACTS / 'fixtures/compatibility-event.valid-update-failed.json').read_text())
    value.update(changes)
    return value


class CaptureUpdateDatabase(Database):
    def __init__(self):
        super().__init__('unused')
        self.queries = []
        self.ids = set()

    @contextmanager
    def connection(self):
        database = self

        class Connection:
            def execute(self, query, parameters):
                database.queries.append((query, parameters))
                event_id = parameters[0]
                inserted = event_id not in database.ids
                database.ids.add(event_id)

                class Result:
                    def fetchone(self):
                        return {'event_id': event_id} if inserted else None
                return Result()
        yield Connection()


class UpdateEvidenceTests(unittest.TestCase):
    def validate(self, value):
        SCHEMA.validate(value)
        return validate_event(json.dumps(value).encode())

    def reject(self, value):
        self.assertFalse(SCHEMA.is_valid(value))
        with self.assertRaises(EvidenceValidationError):
            validate_event(json.dumps(value).encode())

    def test_update_failure_code_allowlist_and_legacy_install_separation(self):
        for code in SCHEMA.schema['$defs']['updateFailureCode']['enum']:
            if code is None:
                continue
            with self.subTest(code=code):
                self.assertEqual(self.validate(update_event(failureCode=code))['failureCode'], code)
                install = update_event(failureCode=code)
                del install['operationKind']
                del install['oldMapPreserved']
                self.reject(install)
        self.reject(update_event(failureCode='INSTALL_FAILED_WRITE'))
        self.reject(update_event(failureCode='UPDATE_UNKNOWN_FAILURE'))

    def test_update_facts_require_explicit_kind_and_version_four(self):
        for kind in ('install', 'remove', '', True, 7, {}, []):
            with self.subTest(kind=kind):
                self.reject(update_event(operationKind=kind))
        for fact in (None, 'true', 1, {}, []):
            with self.subTest(fact=fact):
                self.reject(update_event(oldMapPreserved=fact))
        missing = update_event()
        del missing['oldMapPreserved']
        self.reject(missing)
        for version in (1, 2, 3):
            self.reject(update_event(schemaVersion=version, deletionToken='a' * 64))
        self.reject(update_event(operationKind=None))

    def test_unmeasured_progress_is_optional_only_for_updates(self):
        value = update_event()
        del value['transferProgressBucket']
        self.assertNotIn('transferProgressBucket', self.validate(value))
        value.pop('operationKind')
        value.pop('oldMapPreserved')
        value['failureCode'] = 'INSTALL_FAILED_WRITE'
        self.reject(value)
        self.reject(update_event(transferProgressBucket=None))

    def test_private_and_raw_fields_are_not_allowed(self):
        for field in ('serialNumber', 'unitID', 'localPath', 'manifest', 'rawLog', 'errorMessage'):
            with self.subTest(field=field):
                self.reject(update_event(**{field: '/Users/example/private'}))

    def test_prewrite_success_and_preservation_facts(self):
        prewrite = self.validate(update_event(
            phaseOutcome='NOT_STARTED', automaticFinishingResult='NOT_REACHED',
            failureStage='preflight', failureCode='UPDATE_BLOCKED_INSUFFICIENT_SPACE',
            writeStarted=False, remoteObjectCreated=False, cleanupAttempted=False,
            cleanupSucceeded=False, transferProgressBucket='0'))
        self.assertFalse(prewrite['writeStarted'])
        self.reject(dict(prewrite, writeStarted=True))
        self.reject(dict(prewrite, remoteObjectCreated=True))
        success = self.validate(update_event(
            phaseOutcome='SUCCEEDED', automaticFinishingResult='VERIFIED',
            failureStage=None, failureCode=None, oldMapPreserved=False))
        self.assertFalse(success['oldMapPreserved'])
        self.reject(dict(success, failureCode='UPDATE_FAILED_WRITE'))

    def test_update_local_classification_comes_from_release_label(self):
        for label, expected in (('1.0.0-beta.15-local', True), ('1.0.0-beta.15', False), ('1.0.0-localized', False)):
            database = CaptureUpdateDatabase()
            event = self.validate(update_event(releaseLabel=label))
            database.insert_compatibility_event(event)
            query, parameters = database.queries[-1]
            self.assertIn('is_local_test', query)
            self.assertIs(parameters[-1], expected)

    def test_insert_only_uses_update_diagnostics_and_is_idempotent(self):
        database = CaptureUpdateDatabase()
        for changes in ({}, {
            'id': 'aabbccdd-1111-4111-8111-111111111112',
            'phaseOutcome': 'SUCCEEDED', 'automaticFinishingResult': 'VERIFIED',
            'failureStage': None, 'failureCode': None, 'oldMapPreserved': False,
        }):
            event = self.validate(update_event(**changes))
            self.assertTrue(database.insert_compatibility_event(event))
            self.assertFalse(database.insert_compatibility_event(event))
        self.assertEqual(len(database.queries), 4)
        for query, parameters in database.queries:
            self.assertIn('INSERT INTO map_update_diagnostic', query)
            self.assertIn('ON CONFLICT DO NOTHING', query)
            for forbidden in ('compatibility_evidence_event', 'compatibility_evidence_operation', 'device_model', 'map_download_event'):
                self.assertNotIn(forbidden, query)
            stored = json.loads(parameters[-2])
            self.assertEqual(stored['operationKind'], 'update')
            self.assertEqual(stored['operationId'], parameters[1])
            self.assertEqual(stored['phaseOutcome'], parameters[5])


if __name__ == '__main__':
    unittest.main()
