import copy
import json
from pathlib import Path
import unittest

from terento_catalog.device_labels import model_label, variant_label
from terento_catalog.admin import _identity_parts, _known_variant_description


class DeviceLabelTests(unittest.TestCase):
    def test_shared_display_contract_does_not_mutate_facts(self):
        fixtures = Path(__file__).resolve().parents[3] / 'contracts/fixtures/device-display-labels.json'
        for case in json.loads(fixtures.read_text()):
            with self.subTest(case=case):
                row = case['row']
                original = copy.deepcopy(row)
                self.assertEqual(model_label(row['model']), case['model'])
                self.assertEqual(variant_label(row), case['variant'])
                self.assertEqual(_known_variant_description(row), case['variant'] or '—')
                self.assertEqual(row, original)

    def test_approved_identity_and_counts_stay_unchanged(self):
        row = dict(model='fenix 9 Pro - inReach', variant='51mm',
                   compatibility_identity='fenix 9 Pro - inReach, 51mm',
                   canonical_device_id='garmin-fenix-9-pro-51-inreach',
                   successful_install_count=3, support_status='SUPPORTED',
                   public_review_status='APPROVED', screen_technology='AMOLED')
        original = copy.deepcopy(row)
        self.assertEqual(_identity_parts(row), ('fēnix 9 Pro', '51 mm, AMOLED, inReach', row['compatibility_identity']))
        self.assertEqual(row, original)

    def test_pending_partial_identity_is_not_enriched(self):
        row = dict(model='fenix 9 Pro', variant='47 mm, inReach', identity_state='PENDING')
        self.assertEqual(_identity_parts(row)[:2], ('fēnix 9 Pro', '47 mm, inReach'))
