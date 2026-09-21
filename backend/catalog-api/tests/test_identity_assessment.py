import unittest

from terento_catalog.identity_assessment import assess_identity, selected_identity_conflicts


class IdentityAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.device = dict(id='fenix8pro-51-amoled', model='fēnix 8 Pro', case_size_mm=51,
                           screen_technology='AMOLED', solar=False, inreach=True)
        self.event = dict(model='fēnix 8 Pro', rawMTPModel='fenix 8 Pro 51mm AMOLED inReach',
                          usbVendorID=2334, usbProductID=20920, garminModelPartNumber='006-B4631-00')
        self.mappings = [dict(kind=kind, value=value, device_model_id=self.device['id'],
                              status='APPROVED', source_url='https://example.org/evidence', source_version='1')
                         for kind, value in [('USB', '091e:51b8'), ('XML_PART_NUMBER', '006-B4631-00')]]


    def test_saved_assignment_and_conflicting_sources_stay_separate(self):
        from copy import deepcopy
        from terento_catalog.admin import _identity_checks_markup
        assessment = assess_identity(self.event, [self.device], self.mappings[:1])
        result = dict(canonical_device_model_id=self.device['id'], identity_assessment=assessment,
                      identity_decision={'decision': {'deviceId': self.device['id'], 'reason': 'Confirmed on device'}})
        original = deepcopy(result)
        markup = _identity_checks_markup([result])
        summary = markup.split('<details')[0]
        self.assertIn('Confirmed by administrator', summary)
        self.assertIn('Device codes', markup)
        self.assertNotIn('leave the review open', markup)
        self.assertEqual(result, original)
        result['current_identity_assessment'] = assess_identity(dict(self.event, rawMTPModel='fenix 7 Pro 47mm'), [self.device], self.mappings)
        summary = _identity_checks_markup([result]).split('<details')[0]
        self.assertIn('Conflicting assignment', summary)
        self.assertNotIn('No further model selection needed', summary)

    def test_automatic_assignment_has_complete_checks_without_admin_claim(self):
        from terento_catalog.admin import _identity_checks_markup
        assessment = assess_identity(self.event, [self.device], self.mappings)
        markup = _identity_checks_markup([dict(canonical_device_model_id=self.device['id'], identity_assessment=assessment)])
        summary = markup.split('<details')[0]
        self.assertIn('Assigned catalog model', summary)
        self.assertNotIn('confirmed by administrator', summary)

    def test_display_prefers_saved_catalog_name_without_mutating_report(self):
        from terento_catalog.admin import _identity_parts
        row = dict(model='EPIX Pro', compatibility_identity='EPIX Pro · 51 mm',
                   canonical_device_model_id='epix-pro-51', canonical_model='epix Pro (Gen 2)', variant='51 mm', screen_technology='AMOLED')
        self.assertEqual(_identity_parts(row)[:2], ('epix Pro (Gen 2)', '51 mm, AMOLED'))
        self.assertEqual(row['model'], 'EPIX Pro')

    def test_five_checks_required(self):
        result = assess_identity(self.event, [self.device], self.mappings)
        self.assertEqual(result['canonicalDeviceId'], self.device['id'])
        self.assertEqual(len(result['candidates'][0]['checks']), 5)
        self.assertIsNone(assess_identity(self.event, [self.device], self.mappings[:1])['canonicalDeviceId'])

    def test_legacy_review_status_is_missing_model_evidence(self):
        for label in ('Identity pending', 'Identity unresolved',
                      'Identity not identifiable', 'Identity resolved'):
            with self.subTest(label=label):
                event = dict(self.event, model=label, rawMTPModel=None,
                             canonicalDeviceId=self.device['id'])
                original = dict(event)
                result = assess_identity(event, [self.device], self.mappings)
                check = result['candidates'][0]['checks'][0]
                self.assertEqual(check['state'], 'MISSING')
                self.assertEqual(check['evidence'], [])
                self.assertFalse(result['candidates'][0]['conflict'])
                self.assertIsNone(result['canonicalDeviceId'])
                self.assertEqual(event, original)

    def test_legacy_review_status_does_not_hide_original_model_conflict(self):
        event = dict(self.event, model='Identity pending', rawMTPModel='fenix 7 Pro 51mm AMOLED')
        result = assess_identity(event, [self.device], self.mappings)
        self.assertEqual(result['candidates'][0]['checks'][0]['state'], 'CONFLICT')
        self.assertIsNone(result['canonicalDeviceId'])

    def test_legacy_review_status_does_not_replace_valid_original_model(self):
        result = assess_identity(dict(self.event, model='Identity pending'), [self.device], self.mappings)
        self.assertEqual(result['canonicalDeviceId'], self.device['id'])
        self.assertEqual(result['candidates'][0]['checks'][0]['evidence'][0]['source'], 'rawMTPModel')

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

    def test_matching_fenix_normalization_and_unknown_mapping_are_not_conflicts(self):
        device = dict(self.device, model='fēnix 8', case_size_mm='51', solar=None, inreach=None)
        event = {
            'model': 'fenix 8', 'rawMTPModel': 'fenix 8 – 51mm, AMOLED',
            'caseSizeMm': '51', 'displayType': 'AMOLED',
            'usbVendorID': 2334, 'usbProductID': 20920,
        }
        result = assess_identity(event, [device], [])
        self.assertFalse(result['candidates'][0]['conflict'])
        self.assertEqual(selected_identity_conflicts(event, device, []), [])
        self.assertNotEqual(result['candidates'][0]['checks'][0]['state'], 'CONFLICT')

    def test_unknown_features_and_unconfirmed_mapping_are_not_false_conflicts(self):
        device = dict(self.device, solar=None, inreach=None)
        event = dict(self.event, rawMTPModel='fenix 8 Pro 51mm AMOLED', displayType=None)
        pending = [dict(mapping, status='PENDING') for mapping in self.mappings]
        self.assertEqual(selected_identity_conflicts(event, device, pending), [])
        self.assertFalse(assess_identity(event, [device], pending)['candidates'][0]['conflict'])

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
        self.assertIn("class='identity-mappings'", rendered)
        self.assertEqual(rendered.count("class='identity-mapping-code'"), 1)
        self.assertNotIn('<details open', rendered)
        self.assertIn('2 sources', rendered)

    def test_admin_shows_six_facts_without_redundant_identity_details(self):
        from terento_catalog.admin import _identity_checks_markup, _identity_mapping_markup
        assessment = assess_identity(self.event, [self.device], self.mappings)
        rendered = _identity_checks_markup([{'identity_assessment': assessment, 'garmin_model_description': '<script>unsafe</script>'}])
        for label in ['Model', 'Case size', 'Display', 'Solar', 'inReach', 'Device codes']:
            self.assertIn(label, rendered)
        self.assertNotIn('Technical identity details', rendered)
        self.assertNotIn('identity-technical-evidence', rendered)
        self.assertNotIn('Automatic identity assessment', rendered)
        self.assertIn('&lt;script&gt;', rendered)
        device = dict(id='test', identityMappings=[dict(self.mappings[0], id=1, review_reason='Evidence', history=[])])
        self.assertIn('required', _identity_mapping_markup(device, 'csrf'))

    def test_review_summary_keeps_alternatives_collapsed(self):
        from terento_catalog.admin import _identity_checks_markup, _identity_recommendation
        other = dict(self.device, id='other', case_size_mm=47)
        assessment = assess_identity(self.event, [self.device, other], self.mappings)
        results = [{'identity_assessment': assessment}]
        markup = _identity_checks_markup(results)
        self.assertIn('Review model assignment', markup)
        self.assertEqual(markup.count('<li>'), 0)
        self.assertIn('Device codes', markup)
        self.assertNotIn('device-id other', markup)
        self.assertNotIn('identity-candidate', markup)
        self.assertNotIn('Technical identity details', markup)
        self.assertEqual(_identity_recommendation(results)['deviceId'], self.device['id'])

    def test_review_does_not_guess_when_ambiguous_missing_or_conflicting(self):
        from terento_catalog.admin import _identity_checks_markup, _identity_recommendation
        assessment = assess_identity(self.event, [self.device], self.mappings[:1])
        self.assertIn('Review model assignment', _identity_checks_markup([{'identity_assessment': assessment}]))
        for value in ({}, dict(assessment, candidates=[]),
                      dict(assessment, candidates=[assessment['candidates'][0]] * 2)):
            self.assertIsNone(_identity_recommendation([{'identity_assessment': value}]))
        conflict = assess_identity(dict(self.event, rawMTPModel='fenix 8 Pro 47mm'), [self.device], self.mappings)
        self.assertIsNone(_identity_recommendation([{'identity_assessment': conflict}]))
        self.assertIsNone(_identity_recommendation([{'identity_assessment': assessment}, {}]))

    def test_inreach_label_moves_to_variant_without_changing_identity(self):
        from terento_catalog.admin import _known_variant_description, _identity_parts
        self.assertEqual(_known_variant_description(dict(variant='51 mm', screen_technology='AMOLED', inreach=True)), '51 mm, AMOLED, inReach')
        self.assertEqual(_identity_parts(dict(model='fēnix 9 Pro · inReach', variant='51 mm'))[:2], ('fēnix 9 Pro', '51 mm, inReach'))

    def test_shared_model_keeps_name_but_does_not_guess_screen(self):
        from terento_catalog.admin import _identity_checks_markup, _identity_recommendation
        other = dict(self.device, id='microled', screen_technology='MicroLED')
        mappings = self.mappings + [dict(m, device_model_id=other['id']) for m in self.mappings]
        assessment = assess_identity(dict(self.event, rawMTPModel='fenix 8 Pro 51mm inReach'), [self.device, other], mappings)
        results = [{'identity_assessment': assessment}]
        summary = _identity_checks_markup(results).split('<details')[0]
        self.assertIn('fēnix 8 Pro', summary)
        self.assertIn('Display', summary)
        self.assertIsNone(_identity_recommendation(results))

    def test_diagnostic_summary_remains_above_identification(self):
        from terento_catalog.admin import _diagnostic_detail_dialog
        assessment = assess_identity(self.event, [self.device], self.mappings[:1])
        result = dict(identity_assessment=assessment, identity_resolution_state='UNRESOLVED',
                      operation_id='preview', phase_outcome='SUCCEEDED', provider='custom')
        markup = _diagnostic_detail_dialog('fēnix 8 Pro · 51 mm', 'preview', [result], resolved=False,
                    csrf_token='test', identity_devices=[dict(self.device, variant='51 mm')])
        summary = markup.split("<dl class='diagnostic-detail-summary'>")[1].split('</dl>')[0]
        for label in ('Device', 'Variant', 'Date', 'Map / region', 'Result', 'App version', 'Review state'):
            self.assertIn('<dt>' + label + '</dt>', summary)
        self.assertLess(markup.index("class='diagnostic-detail-summary'"), markup.index("class='identity-summary identity-outcome'"))
        self.assertIn("name='canonical_device_model_id'", markup)
        self.assertIn("value='fenix8pro-51-amoled'", markup)
        self.assertNotIn("name='identity_reason'", markup)

    def test_catalog_specs_can_derive_mip_from_model_size_and_solar(self):
        solar = dict(
            id='fenix7-47-solar-mip', model='fēnix 7', case_size_mm=47,
            screen_technology='MIP', solar=True, inreach=False,
            specification_evidence={
                'screen_technology': {'source': 'Garmin specifications'},
                'solar': {'source': 'Garmin specifications'},
                'inreach': {'source': 'Garmin specifications'},
            },
        )
        amoled = dict(solar, id='fenix7-47-amoled', screen_technology='AMOLED', solar=False)
        result = assess_identity(
            {'model': 'fēnix 7', 'caseSizeMm': 47, 'displayType': 'Solar'},
            [solar, amoled], [],
        )
        candidate = next(item for item in result['candidates'] if item['deviceId'] == solar['id'])
        screen = next(check for check in candidate['checks'] if check['name'] == 'screen')
        self.assertEqual(screen['state'], 'MATCH')
        self.assertEqual(screen['evidence'][0]['source'], 'catalog specification: Garmin specifications')
        self.assertEqual(result['facts']['solar'][0]['value'], True)
        from terento_catalog.admin import _identity_checks_markup, _identity_recommendation
        self.assertEqual(_identity_recommendation([{'identity_assessment': result}])['deviceId'], solar['id'])
        markup = _identity_checks_markup([{'identity_assessment': result}])
        self.assertIn('MIP', markup)
        self.assertIn('From catalog', markup)

    def test_display_type_solar_is_not_a_screen_and_variant_mip_is(self):
        solar_event = dict(self.event, rawMTPModel='fenix 8 Pro 51mm', displayType='Solar', variant=None)
        result = assess_identity(solar_event, [self.device], self.mappings)
        self.assertEqual(result['facts']['solar'][0]['value'], True)
        self.assertEqual(result['facts']['screenTechnology'], [])
        mip_result = assess_identity(dict(self.event, rawMTPModel='fenix 8 Pro 51mm', displayType='Solar', variant='51 mm MIP'), [self.device], self.mappings)
        self.assertEqual(mip_result['facts']['screenTechnology'][0]['value'], 'MIP')

    def test_true_false_and_unknown_features_keep_their_meaning(self):
        from terento_catalog.admin import _identity_checks_markup
        true_device = dict(self.device, id='solar', solar=True, inreach=True)
        true_result = assess_identity(dict(self.event, rawMTPModel='fenix 8 Pro 51mm Solar inReach'), [true_device], [])
        true_candidate = true_result['candidates'][0]
        true_features = true_candidate['checks'][0]['features']
        self.assertEqual({item['name']: item['evidence'][0]['value'] for item in true_features}, {'solar': True, 'inreach': True})

        false_result = assess_identity(dict(self.event, rawMTPModel='fenix 8 Pro 51mm'), [self.device], [])
        false_features = {item['name']: item for item in false_result['candidates'][0]['checks'][0]['features']}
        self.assertEqual(false_features['solar']['state'], 'MISSING')
        self.assertEqual(false_features['solar']['expected'], False)
        false_markup = _identity_checks_markup([{'identity_assessment': false_result}])
        self.assertIn('<span>Solar</span></div><strong>No</strong><small>From catalog</small>', false_markup)

        unknown_device = dict(self.device, id='unknown-features', solar=None, inreach=None)
        unknown_result = assess_identity(dict(self.event, rawMTPModel='fenix 8 Pro 51mm'), [unknown_device], [])
        unknown_markup = _identity_checks_markup([{'identity_assessment': unknown_result}])
        self.assertIn('<span>Solar</span></div><strong>Not reported</strong>', unknown_markup)
        self.assertIn('<span>inReach</span></div><strong>Not reported</strong>', unknown_markup)

    def test_multiple_variants_are_not_selected_by_order_and_labels_expose_inreach(self):
        from terento_catalog.admin import _identity_checks_markup, _identity_device_options, _identity_recommendation
        first = dict(self.device, id='fenix-47-no-inreach', inreach=False, screen_technology='AMOLED')
        second = dict(self.device, id='fenix-47-inreach', inreach=True, screen_technology='AMOLED')
        result = assess_identity({'model': 'fēnix 8 Pro', 'caseSizeMm': 51}, [first, second], [])
        self.assertIsNone(_identity_recommendation([{'identity_assessment': result}]))
        self.assertIn('Select catalog variant', _identity_checks_markup([{'identity_assessment': result}]))
        options, _ = _identity_device_options([first, second])
        self.assertIn("data-identity-device-id='fenix-47-no-inreach'", options)
        self.assertIn('inReach: No', options)
        self.assertIn("data-identity-device-id='fenix-47-inreach'", options)
        self.assertIn('inReach: Yes', options)

    def test_selected_catalog_id_does_not_create_reported_screen_evidence(self):
        result = assess_identity(
            {'model': 'fēnix 8 Pro', 'caseSizeMm': 51,
             'canonicalDeviceId': self.device['id']},
            [self.device], [],
        )
        screen = next(check for check in result['candidates'][0]['checks'] if check['name'] == 'screen')
        self.assertEqual(screen['state'], 'MISSING')
        self.assertEqual(screen['evidence'], [])
        self.assertEqual(result['facts']['screenTechnology'], [])
