import unittest

from terento_catalog.admin import _identity_checks_markup
from terento_catalog.identity_assessment import assess_identity


class IdentityVariantTests(unittest.TestCase):
    def device(self, **changes):
        row = dict(id='fenix9-47', model='fēnix 9 Pro', case_size_mm=47,
                   screen_technology='AMOLED', solar=False, inreach=True,
                   specification_evidence={key: {'source': 'https://example.org/spec', 'version': 'reviewed'}
                                           for key in ('screen_technology', 'solar', 'inreach')})
        return dict(row, **changes)

    def event(self, **changes):
        return dict(dict(model='fenix 9 Pro', rawMTPModel='fenix 9 Pro - inReach, 47mm',
                         garminModelDescription='fenix 9 Pro - inReach, 47mm',
                         garminModelPartNumber='006-B4953-00', usbVendorID=2334,
                         usbProductID=21337), **changes)

    def test_xml_selects_size_and_derives_reviewed_screen_and_solar(self):
        result = assess_identity(self.event(), [self.device(), self.device(id='fenix9-51', case_size_mm=51)], [])
        possible = [c for c in result['candidates'] if not c['conflict']]
        self.assertEqual([c['deviceId'] for c in possible], ['fenix9-47'])
        self.assertEqual(possible[0]['checks'][2]['state'], 'MATCH')
        self.assertEqual(possible[0]['checks'][0]['features'][0]['state'], 'MATCH')
        self.assertIn('catalog specification', str(possible))
        # Suggestions and catalog-derived facts do not approve an identity.
        self.assertEqual(result['state'], 'UNRESOLVED')

    def test_unknown_and_ambiguous_specs_stay_unknown(self):
        for devices in ([self.device(specification_evidence={})],
                        [self.device(), self.device(id='micro', screen_technology='MicroLED', solar=True)]):
            result = assess_identity(self.event(), devices, [])
            self.assertEqual(result['candidates'][0]['checks'][2]['state'], 'MISSING')
            self.assertEqual(result['candidates'][0]['checks'][0]['features'][0]['state'], 'MISSING')

    def test_unknown_feature_is_not_excluded_from_specification_consensus(self):
        devices = [self.device(), self.device(id='unknown-inreach', inreach=None, screen_technology='MicroLED')]
        result = assess_identity(self.event(), devices, [])
        self.assertEqual(result['candidates'][0]['checks'][2]['state'], 'MISSING')
        self.assertFalse(result['candidates'][1]['conflict'])

    def test_xml_mtp_conflict_cannot_derive_specs(self):
        result = assess_identity(self.event(rawMTPModel='fenix 8 Pro 47mm'), [self.device()], [])
        self.assertTrue(result['candidates'][0]['conflict'])
        self.assertEqual(result['candidates'][0]['checks'][2]['state'], 'MISSING')

    def test_received_unmapped_codes_and_reported_model_are_visible(self):
        e = self.event()
        result = assess_identity(e, [self.device()], [])
        markup = _identity_checks_markup([dict(current_identity_assessment=result,
            garmin_model_description=e['garminModelDescription'])])
        for text in ('006-B4953-00', '091e:5359', 'mapping not confirmed',
                     'fenix 9 Pro - inReach, 47mm'):
            self.assertIn(text, markup)
        missing = assess_identity(self.event(usbVendorID=None), [self.device()], [])
        self.assertIn('Not reported', _identity_checks_markup([dict(current_identity_assessment=missing)]))

    def test_normal_selector_excludes_conflicting_variants(self):
        from terento_catalog.admin import _diagnostic_detail_dialog
        devices = [self.device(), self.device(id='wrong-size', case_size_mm=51)]
        assessment = assess_identity(self.event(), devices, [])
        result = dict(identity_assessment=assessment, identity_resolution_state='UNRESOLVED',
                      operation_id='preview', phase_outcome='SUCCEEDED', provider='custom')
        markup = _diagnostic_detail_dialog('fenix 9 Pro', 'preview', [result], resolved=False,
                    csrf_token='test', identity_devices=devices)
        self.assertIn("name='canonical_device_model_id'", markup)
        self.assertIn("value='fenix9-47'", markup)
        self.assertIn("data-canonical-device-wrap hidden", markup)
        self.assertIn("<h4>Assign model</h4>", markup)
        self.assertIn("Selected model:", markup)
        self.assertNotIn("<option", markup)
        self.assertIn("data-identity-device-id='wrong-size'", markup)  # Edit can search the full catalog.
        self.assertIn('wrong-size', markup)  # technical evidence remains available

    def test_reported_inreach_prefers_specific_rows_but_keeps_real_screen_ambiguity(self):
        from terento_catalog.admin import _diagnostic_detail_dialog, _identity_recommendation
        # Shape observed in production: unspecified rows alongside explicit
        # inReach rows, with both AMOLED and Solar/MIP variants in the catalog.
        devices = [self.device(id='generic', inreach=None, solar=None),
                   self.device(id='inreach', solar=None),
                   self.device(id='generic-solar', inreach=None, solar=True, screen_technology='MIP'),
                   self.device(id='inreach-solar', solar=True, screen_technology='MIP')]
        assessment = assess_identity(self.event(), devices, [])
        result = dict(identity_assessment=assessment, identity_resolution_state='UNRESOLVED',
                      operation_id='preview', phase_outcome='SUCCEEDED', provider='custom')
        self.assertIsNone(_identity_recommendation([result]))
        markup = _diagnostic_detail_dialog('fenix 9 Pro', 'preview', [result], resolved=False,
                    csrf_token='test', identity_devices=devices)
        self.assertIn('Identity incomplete', markup)
        self.assertIn('<h4>Assign model</h4>', markup)
        self.assertIn("data-identity-device-id='inreach'", markup)
        self.assertIn('AMOLED', markup)
        self.assertIn('inReach: Yes', markup)
        self.assertIn("data-identity-device-id='inreach-solar'", markup)
        self.assertIn('MIP', markup)
        self.assertIn('Solar: Yes', markup)
        self.assertNotIn("data-identity-device-id='generic'", markup)
        self.assertNotIn("data-identity-device-id='generic-solar'", markup)
        self.assertEqual(len(assessment['candidates']), 4)  # authoritative evidence unchanged
        self.assertEqual(assessment['state'], 'UNRESOLVED')
