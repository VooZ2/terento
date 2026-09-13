import unittest

from terento_catalog.identity_assessment import assess_identity


class IdentityAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.device = dict(id='fenix8pro-51-amoled', model='fēnix 8 Pro', case_size_mm=51,
                           screen_technology='AMOLED', solar=False, inreach=True)
        self.event = dict(model='fēnix 8 Pro', rawMTPModel='fenix 8 Pro 51mm AMOLED inReach',
                          usbVendorID=2334, usbProductID=20920, garminModelPartNumber='006-B4631-00')
        self.mappings = [dict(kind=kind, value=value, device_model_id=self.device['id'],
                              status='APPROVED', source_url='https://example.org/evidence', source_version='1')
                         for kind, value in [('USB', '091e:51b8'), ('XML_PART_NUMBER', '006-B4631-00')]]

    def test_five_checks_required(self):
        result = assess_identity(self.event, [self.device], self.mappings)
        self.assertEqual(result['canonicalDeviceId'], self.device['id'])
        self.assertEqual(len(result['candidates'][0]['checks']), 5)
        self.assertIsNone(assess_identity(self.event, [self.device], self.mappings[:1])['canonicalDeviceId'])

    def test_observed_retail_sku_uses_its_own_registry_kind(self):
        sku = dict(self.mappings[1], kind='RETAIL_SKU', value='010-03199-00')
        event = dict(self.event, garminModelPartNumber=sku['value'])
        result = assess_identity(event, [self.device], [self.mappings[0], sku])
        self.assertEqual(result['canonicalDeviceId'], self.device['id'])
        self.assertEqual(result['candidates'][0]['checks'][3]['codeKind'], 'RETAIL_SKU')
        self.assertIsNone(assess_identity(event, [self.device], [self.mappings[0], dict(sku, kind='XML_PART_NUMBER')])['canonicalDeviceId'])

    def test_shared_codes_do_not_choose_screen(self):
        other = dict(self.device, id='fenix8pro-51-microled', screen_technology='MicroLED')
        mappings = self.mappings + [dict(m, device_model_id=other['id']) for m in self.mappings]
        event = dict(self.event, rawMTPModel='fenix 8 Pro 51mm inReach')
        result = assess_identity(event, [self.device, other], mappings)
        self.assertIsNone(result['canonicalDeviceId'])
        self.assertEqual(len([c for c in result['candidates'] if not c['conflict']]), 2)

    def test_client_id_cannot_override_screen(self):
        event = dict(self.event, canonicalDeviceId=self.device['id'], rawMTPModel='fenix 8 Pro 51mm MicroLED')
        result = assess_identity(event, [self.device], self.mappings)
        self.assertIsNone(result['canonicalDeviceId'])
        self.assertTrue(result['candidates'][0]['conflict'])

    def test_pending_mapping_not_evidence(self):
        mappings = [dict(m, status='PENDING') for m in self.mappings]
        self.assertIsNone(assess_identity(self.event, [self.device], mappings)['canonicalDeviceId'])

    def test_partially_reviewed_shared_code_cannot_appear_unique(self):
        other = dict(self.device, id='fenix8pro-51-microled', screen_technology='MicroLED')
        mappings = self.mappings + [dict(m, device_model_id=other['id'], status='PENDING') for m in self.mappings]
        result = assess_identity(self.event, [self.device, other], mappings)
        self.assertIsNone(result['canonicalDeviceId'])
        self.assertEqual([c['state'] for c in result['candidates'][0]['checks'][-2:]], ['MISSING', 'MISSING'])

    def test_explicit_solar_conflicts_with_non_solar(self):
        event = dict(self.event, rawMTPModel='fenix 8 Pro Solar 51mm')
        self.assertTrue(assess_identity(event, [self.device], self.mappings)['candidates'][0]['conflict'])

    def test_xml_mtp_disagreement_is_retained(self):
        event = dict(self.event, garminModelDescription='fenix 8 Pro 47mm AMOLED')
        self.assertTrue(assess_identity(event, [self.device], self.mappings)['candidates'][0]['conflict'])

    def test_unknown_features_are_not_negative_checks(self):
        device = dict(self.device, solar=None, inreach=None)
        result = assess_identity(self.event, [device], self.mappings)
        self.assertIsNone(result['canonicalDeviceId'])
        self.assertEqual(result['candidates'][0]['checks'][0]['state'], 'MISSING')

    def test_variant_field_cannot_hide_solar_conflict(self):
        result = assess_identity(dict(self.event, variant='Solar'), [self.device], self.mappings)
        self.assertTrue(result['candidates'][0]['conflict'])

    def test_corrections_keep_provenance_and_original(self):
        from terento_catalog.identity_assessment import apply_corrections, validate_correction
        original = dict(self.event)
        effective = apply_corrections(original, [{'id': 7, 'field': 'rawMTPModel', 'corrected_value': 'fenix 8 Pro 47mm AMOLED'}])
        result = assess_identity(effective, [self.device], self.mappings)
        self.assertEqual(original, self.event)
        self.assertTrue(result['candidates'][0]['conflict'])
        self.assertIn('admin correction 7', str(result))
        for field, value in [('usbVendorID', True), ('garminModelPartNumber', '006/invalid'), ('unitID', '123456')]:
            with self.assertRaises(ValueError):
                validate_correction(field, value)

    def test_imports_preserve_shared_codes_and_require_review(self):
        import json
        from terento_catalog.identity_registry import prepare_mappings
        other = dict(self.device, id='fenix8pro-51-microled', screen_technology='MicroLED')
        content = json.dumps([{'name': 'fenix 8 Pro', 'partNumber': '006-B4631-00', 'additionalNames': []}])
        rows = prepare_mappings('garmin', content, [self.device, other])
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r['status'] == 'PENDING' and len(r['source_version']) == 64 for r in rows))

    def test_import_explicit_size_narrows_candidates_and_retains_source_name(self):
        import json
        from terento_catalog.identity_registry import prepare_mappings
        other = dict(self.device, id='fenix8pro-47-amoled', case_size_mm=47)
        name = 'fenix 8 Pro 51mm AMOLED'
        rows = prepare_mappings('garmin', json.dumps([{'name': name, 'partNumber': '006-B4631-00'}]), [self.device, other])
        self.assertEqual([r['device_model_id'] for r in rows], [self.device['id']])
        self.assertEqual(rows[0]['source_names'], [name])

    def test_admin_groups_repeated_sources_under_one_collapsed_code(self):
        from terento_catalog.admin import _identity_mapping_markup
        mapping = dict(self.mappings[0], id=1, history=[])
        rendered = _identity_mapping_markup(dict(id='test', identityMappings=[mapping, dict(mapping, id=2, source_version='2')]), 'csrf')
        self.assertIn('1 codes · 0 awaiting review', rendered)
        self.assertEqual(rendered.count("class='identity-mapping-code'"), 1)
        self.assertNotIn('<details open', rendered)
        self.assertIn('2 source(s)', rendered)

    def test_admin_shows_five_checks_sources_and_escaped_raw_metadata(self):
        from terento_catalog.admin import _identity_checks_markup, _identity_mapping_markup
        assessment = assess_identity(self.event, [self.device], self.mappings)
        rendered = _identity_checks_markup([{'identity_assessment': assessment, 'garmin_model_description': '<script>unsafe</script>'}])
        for label in ['Model and variant', 'Case size', 'Screen technology', 'Device XML part number', 'USB VID/PID', 'not independent observations']:
            self.assertIn(label, rendered)
        self.assertIn('Automatically assigned', rendered)
        self.assertNotIn('<script>unsafe', rendered)
        self.assertIn('&lt;script&gt;', rendered)
        device = dict(id='test', identityMappings=[dict(self.mappings[0], id=1, review_reason='Evidence', history=[])])
        self.assertIn('required', _identity_mapping_markup(device, 'csrf'))
