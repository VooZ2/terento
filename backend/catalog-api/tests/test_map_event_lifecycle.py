import json
import unittest
from pathlib import Path
from uuid import uuid4

from terento_catalog.map_events import MapEventValidationError, validate_map_event


class MapEventLifecycleTests(unittest.TestCase):
    def map_event(self, **changes):
        path = Path(__file__).resolve().parents[3] / 'contracts/fixtures/map-event.valid.json'
        return dict(json.loads(path.read_text()), **changes)

    def test_old_client_and_component_events_are_accepted(self):
        validate_map_event(json.dumps(self.map_event()).encode())
        for kind in ('main', 'contours'):
            for event_type in ('DOWNLOAD_PROCESSING', 'DOWNLOAD_CANCELLED', 'DOWNLOAD_INTERRUPTED'):
                e = self.map_event(acquisitionId=str(uuid4()), componentKind=kind,
                                   eventType=event_type, outcome='UNKNOWN')
                parsed = validate_map_event(json.dumps(e).encode())
                self.assertEqual(parsed['componentKind'], kind)

    def test_invalid_lifecycle_pairs_and_outcomes_are_rejected(self):
        for fields in (dict(acquisitionId=str(uuid4())), dict(componentKind='main'),
                       dict(acquisitionId='bad', componentKind='main'),
                       dict(acquisitionId=str(uuid4()), componentKind='private-file.img'),
                       dict(eventType='DOWNLOAD_INTERRUPTED', outcome='UNKNOWN'),
                       dict(acquisitionId=str(uuid4()), componentKind='main',
                            eventType='DOWNLOAD_CANCELLED', outcome='SUCCEEDED')):
            with self.assertRaises(MapEventValidationError):
                validate_map_event(json.dumps(self.map_event(**fields)).encode())

    def test_acquisition_purpose_is_explicit_and_download_only(self):
        for purpose in ('install', 'update', None):
            event = self.map_event(acquisitionId=str(uuid4()), componentKind='main',
                                  acquisitionPurpose=purpose, eventType='DOWNLOAD_SUCCEEDED', outcome='SUCCEEDED')
            self.assertEqual(validate_map_event(json.dumps(event).encode())['acquisitionPurpose'], purpose)
        legacy = validate_map_event(json.dumps(self.map_event()).encode())
        self.assertNotIn('acquisitionPurpose', legacy)
        for fields in (
            dict(acquisitionPurpose='install'),
            dict(acquisitionId=str(uuid4()), componentKind='main', acquisitionPurpose='INSTALL', eventType='DOWNLOAD_STARTED', outcome='UNKNOWN'),
            dict(acquisitionId=str(uuid4()), componentKind='main', acquisitionPurpose=True, eventType='DOWNLOAD_STARTED', outcome='UNKNOWN'),
            dict(acquisitionId=str(uuid4()), componentKind='main', acquisitionPurpose='update', eventType='MAP_UPDATE_SUCCEEDED', outcome='SUCCEEDED'),
        ):
            with self.subTest(fields=fields), self.assertRaises(MapEventValidationError):
                validate_map_event(json.dumps(self.map_event(**fields)).encode())

    def test_legacy_terminal_type_and_outcome_must_agree(self):
        for event_type, expected in (
            ('DOWNLOAD_STARTED', 'UNKNOWN'), ('DOWNLOAD_SUCCEEDED', 'SUCCEEDED'),
            ('DOWNLOAD_FAILED', 'FAILED'), ('INSTALL_SUCCEEDED', 'SUCCEEDED'),
            ('INSTALL_FAILED', 'FAILED'), ('MAP_UPDATE_SUCCEEDED', 'SUCCEEDED'),
            ('MAP_UPDATE_FAILED', 'FAILED'),
        ):
            for outcome in ('UNKNOWN', 'SUCCEEDED', 'FAILED'):
                with self.subTest(event_type=event_type, outcome=outcome):
                    raw = json.dumps(self.map_event(eventType=event_type, outcome=outcome)).encode()
                    if outcome == expected:
                        validate_map_event(raw)
                    else:
                        with self.assertRaises(MapEventValidationError):
                            validate_map_event(raw)

    def test_result_index_rejects_boolean_float_and_integer_overflow(self):
        for index in (True, False, 0.0, 1.5, -1, 2147483648):
            with self.subTest(index=index), self.assertRaisesRegex(MapEventValidationError, 'invalid_mapResultIndex'):
                validate_map_event(json.dumps(self.map_event(mapResultIndex=index)).encode())
        for index in (None, 0, 2147483647):
            validate_map_event(json.dumps(self.map_event(mapResultIndex=index)).encode())
