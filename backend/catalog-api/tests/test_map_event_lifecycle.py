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
