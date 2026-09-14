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

    def test_installation_variants_use_only_the_linked_catalog_record(self):
        from terento_catalog.admin import dashboard_page
        cases = [
            ('fenix 9 Pro', 47, False),
            ('fenix 8 Pro', 51, True),
            ('fenix 9 Pro - inReach', 51, True),
            ('fenix 8', 43, False),
            ('fenix 8 Pro', 47, True),
        ]
        devices, rows = [], []
        for index, (model, size, inreach) in enumerate(cases):
            devices.append(dict(id=str(index), model=model, variant=f'{size} mm',
                                screenTechnology='AMOLED', inReach=inreach))
            rows.append(dict(model=model, variant=f'{size} mm',
                             canonical_device_model_id=str(index),
                             successful_install_count=2, attempted_install_count=2))
        # An unresolved lookalike must not borrow any catalog specifications.
        rows.append(dict(model='fenix 8 Pro', variant='47 mm'))
        original = copy.deepcopy((rows, devices))
        body = dashboard_page(rows, {'username': 'operator'}, 'csrf', identity_devices=devices).decode()
        rendered = body.split('<tbody id="evidence-rows">')[1].split('</tbody>')[0].split('</tr>')
        for index, (_, size, inreach) in enumerate(cases):
            expected = f'{size} mm, AMOLED' + (', inReach' if inreach else '')
            self.assertIn(f'<td>{expected}</td>', rendered[index])
            self.assertIn(f'/admin/devices/{index}', rendered[index])
        self.assertIn('<td>47 mm</td>', rendered[5])
        self.assertNotIn('AMOLED', rendered[5])
        self.assertEqual((rows, devices), original)
