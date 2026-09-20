"""Schema/runtime parity, privacy, persistence, and per-result context presentation."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from terento_catalog.compatibility_evidence import validate_event, EvidenceValidationError
from terento_catalog.failure_context import CONTEXT_ENUMS, PROTECTION_ENUMS, COUNT_FIELDS, TARGET_FIELDS, BOUNDARIES, BOUNDARY_STAGES
from terento_catalog.admin import _github_issue_report, _failure_context_summary, _diagnostic_technical_details
from test_operation_diagnostic_delivery import IntakeDatabase
from test_compatibility_evidence import event as legacy_event

ROOT = Path(__file__).resolve().parents[3]


def fixture(name='preflight'):
    return json.loads((ROOT / f'contracts/fixtures/compatibility-event.valid-context-{name}.json').read_text())


class FailureContextTests(unittest.TestCase):
    def setUp(self):
        self.schema = Draft202012Validator(json.loads((ROOT / 'contracts/compatibility-event.schema.json').read_text()))

    def check(self, event, accepted=True):
        if accepted:
            self.schema.validate(event)
            self.assertEqual(validate_event(json.dumps(event).encode()), event)
        else:
            self.assertFalse(self.schema.is_valid(event), event)
            with self.assertRaises(EvidenceValidationError):
                validate_event(json.dumps(event).encode())

    def test_fixtures_and_legacy_versions(self):
        for name in ('preflight', 'cleanup', 'contours-cleanup'):
            self.check(fixture(name))
        for version in (1, 2, 3, 4):
            event = legacy_event(schemaVersion=version) if version < 3 else fixture()
            event.pop('failureContext', None)
            event['schemaVersion'] = version
            if version < 4:
                event['deletionToken'] = 'a' * 64
            self.check(event)
            if version < 4:
                for key in ('failureContext', 'originalFailureContext'):
                    candidate = deepcopy(event)
                    candidate[key] = fixture()['failureContext']
                    self.check(candidate, False)

    def test_enums_are_closed_and_schema_matches_runtime(self):
        schema = self.schema.schema['$defs']['failureContext']
        for key, values in CONTEXT_ENUMS.items():
            self.assertEqual(schema['properties'][key]['enum'], list(values))
            for hostile in ('/Users/private/map.img', {'raw': 'secret'}, ['native'], None):
                candidate = fixture()
                candidate['failureContext'][key] = hostile
                self.check(candidate, False)
        for key, values in PROTECTION_ENUMS.items():
            self.assertEqual(schema['properties']['protection']['properties'][key]['enum'], list(values))

    def test_privacy_and_nonrecursive_allowlist(self):
        for key in ('rawPath', 'filename', 'serial', 'unitID', 'objectID', 'parentID', 'hash', 'sha256', 'nativeError', 'classSource', 'failureContext', 'originalFailureContext'):
            for location in ('context', 'protection', 'original'):
                candidate = fixture('cleanup')
                target = candidate['originalFailureContext'] if location != 'context' else candidate['failureContext']
                if location == 'protection':
                    target = target['protection']
                target[key] = 'private'
                self.check(candidate, False)
        for key in ('failureContext', 'originalFailureContext'):
            for bad in (None, [], 'private'):
                candidate = fixture('cleanup')
                candidate[key] = bad
                self.check(candidate, False)

    def test_numeric_bounds_and_nullable_targets(self):
        for field, low, high in (('retryCount', 0, 255), ('nativeResultCode', -(2**31), 2**31 - 1)):
            for value in (low, high, low - 1, high + 1, True, False, '1'):
                candidate = fixture()
                candidate['failureContext'][field] = value
                self.check(candidate, type(value) is int and low <= value <= high)
        for field in COUNT_FIELDS + ('stableIdentityComparisonVersion',):
            low, high = (1, 2) if field == 'stableIdentityComparisonVersion' else (0, 16384)
            for value in (low, high, low - 1, high + 1, True, '1', None):
                candidate = fixture('cleanup')
                candidate['originalFailureContext']['protection'][field] = value
                self.check(candidate, type(value) is int and low <= value <= high)
        for field in TARGET_FIELDS:
            for value in (True, False, None, 0, 1, 'private'):
                candidate = fixture('cleanup')
                candidate['originalFailureContext']['protection'][field] = value
                self.check(candidate, value is None or type(value) is bool)
        for field in ('nativeCodeNamespace', 'nativeResultCode'):
            candidate = fixture()
            del candidate['failureContext'][field]
            self.check(candidate, False)

    def test_cleanup_and_optional_component_consistency(self):
        candidate = fixture('cleanup')
        del candidate['failureContext']
        self.check(candidate, False)
        for field, value in (('boundary', 'write'), ('componentKind', 'contours')):
            candidate = fixture('cleanup')
            candidate['failureContext'][field] = value
            self.check(candidate, False)
        for boundary in ('write', 'cleanup', 'initial_inventory', 'prewrite_protection'):
            candidate = fixture('cleanup')
            candidate['originalFailureContext']['boundary'] = boundary
            self.check(candidate, False)
        candidate = fixture('cleanup')
        candidate['failureStage'] = 'verify'
        self.check(candidate, False)
        for field, value in (('optionalComponentSelected', False), ('optionalComponentOutcome', 'VERIFIED'), ('optionalComponentFailureStage', 'verify')):
            candidate = fixture('contours-cleanup')
            candidate[field] = value
            self.check(candidate, False)
        candidate = fixture('contours-cleanup')
        candidate['failureContext']['componentKind'] = 'main'
        self.check(candidate, False)
        candidate = fixture('contours-cleanup')
        del candidate['failureContext']['componentKind']
        self.check(candidate, False)
        candidate = fixture()
        candidate.update(phaseOutcome='NOT_STARTED', automaticFinishingResult='NOT_REACHED')
        self.check(candidate, False)

    def test_persistence_roundtrip_duplicate_and_old_null(self):
        db = IntakeDatabase()
        self.addCleanup(db.sqlite.close)
        candidate = validate_event(json.dumps(fixture('cleanup')).encode())
        self.assertTrue(db.insert_compatibility_event(candidate))
        row = db.rows()[0]
        self.assertEqual(row['failure_context'], candidate['failureContext'])
        self.assertEqual(row['original_failure_context'], candidate['originalFailureContext'])
        replacement = deepcopy(candidate)
        replacement['failureContext']['devicePresence'] = 'absent'
        self.assertFalse(db.insert_compatibility_event(replacement))
        self.assertEqual(db.rows()[0]['failure_context'], candidate['failureContext'])
        old = fixture()
        del old['failureContext']
        old['id'] = 'aabbccdd-1111-4111-8111-111111111112'
        self.assertTrue(db.insert_compatibility_event(old))
        self.assertIsNone(db.rows()[1]['failure_context'])
        self.assertIsNone(db.rows()[1]['original_failure_context'])

    def test_observed_contradictions_and_cleanup_attempt(self):
        for name in ('cleanup', 'contours-cleanup'):
            candidate = fixture(name)
            candidate.update(cleanupAttempted=False, cleanupSucceeded=False)
            self.check(candidate, False)
            del candidate['originalFailureContext']
            self.check(candidate, False)
        for reason, field, bad in (
            ('target-present-before-write', 'targetPresent', False),
            ('target-missing', 'targetPresent', True),
            ('target-duplicate', 'targetUnique', True),
            ('target-duplicate', 'targetPresent', False),
            ('target-filename-mismatch', 'targetFilenameMatches', True),
            ('target-size-mismatch', 'targetSizeMatches', True),
        ):
            for original in (False, True):
                candidate = fixture('cleanup')
                context = candidate['originalFailureContext']
                context['protection'] = {'protectionBoundary': 'post-write', 'protectionReason': reason, field: bad}
                if reason == 'target-present-before-write':
                    context['boundary'] = 'prewrite_protection'
                    context['protection']['protectionBoundary'] = 'pre-write'
                if not original:
                    candidate['failureContext'] = candidate.pop('originalFailureContext')
                    candidate['failureStage'] = BOUNDARY_STAGES[context['boundary']]
                    candidate['failureCode'] = 'INSTALL_FAILED_PROTECTION_VIOLATION'
                self.check(candidate, False)
                context['protection'][field] = None
                self.check(candidate)
                del context['protection'][field]
                self.check(candidate)

    def test_protection_reason_boundary_matrix(self):
        allowed = {
            'target-present-before-write': {'prewrite_protection'},
            'target-missing': {'target_validation', 'postwrite_protection'},
            'target-duplicate': {'target_validation', 'postwrite_protection'},
            'target-invalid': {'target_validation', 'postwrite_protection'},
            'target-filename-mismatch': {'target_validation', 'postwrite_protection'},
            'target-size-mismatch': {'target_validation', 'postwrite_protection'},
            'non-target-object-added': {'prewrite_protection', 'postwrite_protection'},
            'preexisting-object-removed': {'prewrite_protection', 'postwrite_protection'},
            'preexisting-object-changed': {'prewrite_protection', 'postwrite_protection'},
            'inventory-ambiguous': {'prewrite_protection', 'postwrite_protection'},
        }
        self.assertEqual(set(allowed), set(PROTECTION_ENUMS['protectionReason']))
        for reason, boundaries in allowed.items():
            for boundary in BOUNDARIES:
                for original in (False, True):
                    for nullable in (False, True):
                        with self.subTest(reason=reason, boundary=boundary, original=original, nullable=nullable):
                            candidate = fixture('cleanup')
                            context = candidate['originalFailureContext']
                            context['boundary'] = boundary
                            context['protection'] = {
                                'protectionReason': reason,
                                'protectionBoundary': 'pre-write' if boundary == 'prewrite_protection' else 'post-write',
                            }
                            if nullable:
                                context['protection'].update(dict.fromkeys(TARGET_FIELDS))
                            if not original:
                                candidate['failureContext'] = candidate.pop('originalFailureContext')
                                candidate['failureStage'] = BOUNDARY_STAGES[boundary]
                            self.check(candidate, boundary in boundaries)

    def test_report_preserves_zero_false_and_unknown(self):
        context = fixture()['failureContext']
        context['nativeResultCode'] = 0
        row = {'map_result_index': 0, 'failure_context': context}
        _, report = _github_issue_report('Test watch', [row])
        self.assertIn('Failure retry count: 0', report)
        self.assertIn('Failure native result code: 0', report)
        row['failure_context'] = fixture('cleanup')['originalFailureContext']
        row['failure_context']['protection']['targetItemIDMatches'] = False
        _, report = _github_issue_report('Test watch', [row])
        self.assertIn('Failure targetitemidmatches: False', report)
        self.assertIn('Failure targetpathmatches: unavailable', report)

    def test_reports_keep_component_and_result_provenance(self):
        db = IntakeDatabase()
        self.addCleanup(db.sqlite.close)
        candidate = fixture('contours-cleanup')
        candidate.update(provider='custom', region='custom', mapRelease='custom')
        db.insert_compatibility_event(candidate)
        row = db.rows()[0]
        sibling = dict(row, provider='opentopomap', map_result_index=1, failure_context=None, original_failure_context=None)
        _, report = _github_issue_report('Test watch', [sibling, row])
        first, second = report.split('## mapResultIndex 0 diagnostics')
        self.assertIn('Source: Custom import', second)
        self.assertIn('manually imported IMG', second)
        self.assertIn('Original file provenance: not tracked', second)
        self.assertIn('Failure stage: cleanup', second)
        self.assertIn('Failure component: contours', second)
        self.assertIn('Original failure protection reason: preexisting-object-changed', second)
        self.assertIn('Failure boundary: unavailable', first)
        self.assertNotIn('postwrite_protection', first)
        self.assertIn('cleanup', _failure_context_summary([row]))
        technical = _diagnostic_technical_details(row, 1)
        self.assertIn('targetItemIDMatches', technical)
        self.assertNotIn('postwrite_protection', _failure_context_summary([sibling]))
        malicious = dict(row, failure_context={'boundary': '/Users/private', 'filename': 'secret.img'})
        _, report = _github_issue_report('Test watch', [malicious])
        self.assertNotIn('/Users/private', report)
        self.assertNotIn('secret.img', report)
