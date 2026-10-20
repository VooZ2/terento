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
        from terento_catalog.admin import _identity_review_form
        assessment = assess_identity(self.event, [self.device], self.mappings[:1])
        result = dict(canonical_device_model_id=self.device['id'], identity_assessment=assessment,
                      identity_decision={'decision': {'deviceId': self.device['id'], 'reason': 'Confirmed on device'}})
        original = deepcopy(result)
        form = _identity_review_form('key', [result], csrf_token='t', identity_devices=[self.device],
                                     return_to='/admin', id_suffix='x')
        self.assertNotIn('data-identity-conflict', form)
        self.assertEqual(result, original)
        result['current_identity_assessment'] = assess_identity(dict(self.event, rawMTPModel='fenix 7 Pro 47mm'), [self.device], self.mappings)
        form = _identity_review_form('key', [result], csrf_token='t', identity_devices=[self.device],
                                     return_to='/admin', id_suffix='x')
        self.assertIn('data-identity-conflict', form)
        self.assertIn('Case size: reported 47', form)
        self.assertNotIn('data-manual-confirm hidden', form)

    def test_display_prefers_saved_catalog_name_without_mutating_report(self):
        from terento_catalog.admin import _identity_parts
        row = dict(model='EPIX Pro', compatibility_identity='EPIX Pro · 51 mm',
                   canonical_device_model_id='epix-pro-51', canonical_model='epix Pro (Gen 2)', variant='51 mm', screen_technology='AMOLED')
        self.assertEqual(_identity_parts(row)[:2], ('epix Pro (Gen 2)', '51 mm, AMOLED'))
        self.assertEqual(row['model'], 'EPIX Pro')

    def test_five_checks_required(self):
        result = assess_identity(self.event, [self.device], self.mappings)
        self.assertEqual(result['canonicalDeviceId'], self.device['id'])
        self.assertEqual(result['resolution'], 'EXACT')
        self.assertEqual(len(result['candidates'][0]['checks']), 5)
        single = assess_identity(self.event, [self.device], self.mappings[:1])
        self.assertEqual(single['candidates'][0]['checks'][3]['state'], 'MISSING')
        self.assertEqual((single['canonicalDeviceId'], single['resolution']), (self.device['id'], 'SINGLE_MATCH'))

    def test_single_matching_model_resolves_without_codes(self):
        sibling = dict(self.device, id='fenix8pro-47-amoled', case_size_mm=47)
        result = assess_identity(self.event, [self.device, sibling], [])
        self.assertEqual(result['state'], 'RESOLVED')
        self.assertEqual((result['canonicalDeviceId'], result['resolution']), (self.device['id'], 'SINGLE_MATCH'))

    def test_two_possible_models_stay_unresolved(self):
        sibling = dict(self.device, id='fenix8pro-51-microled', screen_technology='MicroLED')
        event = dict(self.event, rawMTPModel='fenix 8 Pro 51mm inReach')
        result = assess_identity(event, [self.device, sibling], [])
        self.assertEqual((result['state'], result['canonicalDeviceId'], result['resolution']),
                         ('UNRESOLVED', None, None))

    def test_reported_solar_prefers_the_solar_row_over_an_unknown_one(self):
        solar = dict(self.device, id='fenix8pro-51-solar', solar=True)
        unknown = dict(self.device, id='fenix8pro-51-unknown', solar=None)
        event = dict(self.event, rawMTPModel='fenix 8 Pro Solar 51mm AMOLED inReach')
        result = assess_identity(event, [solar, unknown], [])
        self.assertEqual((result['canonicalDeviceId'], result['resolution']), (solar['id'], 'SINGLE_MATCH'))
        both = assess_identity(event, [solar, dict(unknown, solar=True)], [])
        self.assertIsNone(both['canonicalDeviceId'])

    def test_reviewed_alias_and_reported_size_resolve_the_epix_pro_size_row(self):
        # Garmin's epix Pro reports "epix Pro - 47mm" without "(Gen 2)"; the catalog
        # keeps an unsized legacy row next to the 42, 47 and 51 mm rows.
        rows = [dict(id='epix-pro', model='epix Pro (Gen 2)', case_size_mm=None, screen_technology=None)] + [
            dict(id=f'epix-pro-{size}', model='epix Pro (Gen 2)', case_size_mm=size, screen_technology='AMOLED')
            for size in (42, 47, 51)]
        for text, expected in (('epix pro - 47mm', 'epix-pro-47'), ('EPIX PRO - 51mm', 'epix-pro-51')):
            result = assess_identity(dict(rawMTPModel=text), rows, [])
            self.assertEqual((result['canonicalDeviceId'], result['resolution']), (expected, 'SINGLE_MATCH'))
            self.assertEqual(result['facts']['model'], [{'source': 'rawMTPModel', 'value': text}])
        # No reported size: the 42, 47 and 51 mm rows and the unsized row stay possible.
        self.assertIsNone(assess_identity(dict(rawMTPModel='epix pro'), rows, [])['canonicalDeviceId'])
        # A real catalog "epix Pro" row takes the name itself; the alias is not applied.
        real = dict(id='epix-pro-original', model='epix Pro', case_size_mm=None, screen_technology=None)
        result = assess_identity(dict(rawMTPModel='epix pro - 47mm'), rows + [real], [])
        self.assertEqual([c['deviceId'] for c in result['candidates']], ['epix-pro-original'])
        # The alias is exact: another model name never reaches the epix Pro rows.
        self.assertEqual(assess_identity(dict(rawMTPModel='epix - 47mm'), rows, [])['candidates'], [])

    def test_ambiguous_epix_name_keeps_both_generations_until_a_code_decides(self):
        # Production 2026-10-19: an epix (Gen 2) reports "EPIX", the same name as
        # the original epix, so the name alone never picks a generation.
        gen1 = dict(id='epix-gen-1', model='epix', case_size_mm=None, screen_technology=None)
        gen2 = dict(id='epix-gen-2-47', model='epix (Gen 2)', case_size_mm=47, screen_technology=None)
        quatix = dict(id='quatix-7', model='quatix 7', case_size_mm=47, screen_technology=None)
        rows = [gen1, gen2, quatix]
        event = dict(rawMTPModel='EPIX', model='EPIX', garminModelDescription='EPIX',
                     garminModelPartNumber='006-B3943-00', usbVendorID=0x091E, usbProductID=0x4F67)
        result = assess_identity(event, rows, [])
        self.assertEqual([c['deviceId'] for c in result['candidates']], ['epix-gen-1', 'epix-gen-2-47'])
        self.assertTrue(all(c['checks'][0]['observedState'] == 'MATCH' for c in result['candidates']))
        self.assertEqual((result['state'], result['canonicalDeviceId']), ('UNRESOLVED', None))
        self.assertEqual(result['candidates'][1]['checks'][0]['evidence'][0],
                         {'source': 'rawMTPModel (reviewed ambiguous name)', 'value': 'epix gen 2'})
        # Pending links decide nothing.
        def link(kind, value, device_id, status):
            return dict(kind=kind, value=value, device_model_id=device_id, status=status,
                        source_url='https://example.org/evidence', source_version='1')
        pending = [link('XML_PART_NUMBER', '006-B3943-00', 'epix-gen-2-47', 'PENDING'),
                   link('XML_PART_NUMBER', '006-B3943-00', 'quatix-7', 'PENDING'),
                   link('USB', '091e:4f67', 'epix-gen-2-47', 'PENDING')]
        self.assertIsNone(assess_identity(event, rows, pending)['canonicalDeviceId'])
        # Reviewed codes exclude the original epix; the Gen 2 row is the single match.
        approved = [dict(m, status='APPROVED') for m in pending]
        result = assess_identity(event, rows, approved)
        self.assertEqual((result['canonicalDeviceId'], result['resolution']), ('epix-gen-2-47', 'SINGLE_MATCH'))
        # An original epix with its own reviewed code resolves to the original row.
        original = dict(rawMTPModel='EPIX', garminModelPartNumber='006-B1988-00')
        result = assess_identity(original, rows, [link('XML_PART_NUMBER', '006-B1988-00', 'epix-gen-1', 'APPROVED')])
        self.assertEqual((result['canonicalDeviceId'], result['resolution']), ('epix-gen-1', 'SINGLE_MATCH'))
        # Without a real "epix" row nothing is added: the name never reaches Gen 2 alone.
        self.assertEqual(assess_identity(dict(rawMTPModel='EPIX'), [gen2], [])['candidates'], [])
        # Explicit generation names stay exact.
        self.assertEqual([c['deviceId'] for c in assess_identity(dict(rawMTPModel='epix (Gen 2)'), rows, [])['candidates']],
                         ['epix-gen-2-47'])
        # Assigning either generation to an "EPIX" report is no model contradiction.
        self.assertEqual(selected_identity_conflicts(dict(rawMTPModel='EPIX'), gen2), [])
        self.assertEqual(selected_identity_conflicts(dict(rawMTPModel='EPIX'), gen1), [])
        self.assertEqual([c['field'] for c in selected_identity_conflicts(dict(rawMTPModel='EPIX'), quatix)], ['model'])

    def test_code_without_reported_model_name_stays_unresolved(self):
        event = dict(self.event, model=None, rawMTPModel=None)
        result = assess_identity(event, [self.device], self.mappings)
        self.assertFalse(result['candidates'][0]['conflict'])
        self.assertIsNone(result['canonicalDeviceId'])

    def test_unreviewed_code_for_another_model_stays_unresolved(self):
        other = dict(self.device, id='forerunner-965', model='Forerunner 965', case_size_mm=47)
        pending = dict(self.mappings[0], device_model_id=other['id'], status='PENDING')
        result = assess_identity(self.event, [self.device, other], [pending])
        self.assertEqual([c['deviceId'] for c in result['candidates']], [self.device['id']])
        self.assertIsNone(result['canonicalDeviceId'])

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
        wrong_kind = assess_identity(event, [self.device], [self.mappings[0], dict(sku, kind='XML_PART_NUMBER')])
        self.assertEqual(wrong_kind['candidates'][0]['checks'][3]['state'], 'MISSING')
        self.assertEqual(wrong_kind['resolution'], 'SINGLE_MATCH')

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
        result = assess_identity(self.event, [self.device], mappings)
        self.assertEqual([c['state'] for c in result['candidates'][0]['checks'][-2:]], ['MISSING', 'MISSING'])
        self.assertNotEqual(result['resolution'], 'EXACT')

    def test_partially_reviewed_shared_code_cannot_appear_unique(self):
        other = dict(self.device, id='fenix8pro-51-microled', screen_technology='MicroLED')
        mappings = self.mappings + [dict(m, device_model_id=other['id'], status='PENDING') for m in self.mappings]
        result = assess_identity(self.event, [self.device, other], mappings)
        self.assertEqual([c['state'] for c in result['candidates'][0]['checks'][-2:]], ['MISSING', 'MISSING'])
        # The reported AMOLED screen excludes the other target; the name decides.
        self.assertEqual(result['resolution'], 'SINGLE_MATCH')

    def test_explicit_solar_conflicts_with_non_solar(self):
        event = dict(self.event, rawMTPModel='fenix 8 Pro Solar 51mm')
        self.assertTrue(assess_identity(event, [self.device], self.mappings)['candidates'][0]['conflict'])

    def test_xml_mtp_disagreement_is_retained(self):
        event = dict(self.event, garminModelDescription='fenix 8 Pro 47mm AMOLED')
        self.assertTrue(assess_identity(event, [self.device], self.mappings)['candidates'][0]['conflict'])

    def test_unknown_features_are_not_negative_checks(self):
        device = dict(self.device, solar=None, inreach=None)
        result = assess_identity(self.event, [device], self.mappings)
        self.assertNotEqual(result['resolution'], 'EXACT')
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

    @staticmethod
    def _import(kind, entries, devices):
        import json
        from terento_catalog.identity_registry import prepare_mappings
        content = json.dumps(entries) if kind == 'garmin' else ''.join(
            f'  {{ "Garmin", 0x091e, "{name}", {pid}, DEVICE_FLAGS_ANDROID_BUGS }},\n' for name, pid in entries)
        return sorted((r['value'], r['device_model_id']) for r in prepare_mappings(kind, content, devices))

    def test_import_stated_screen_or_solar_variant_names_only_that_variant(self):
        # Garmin's device list, 2026-10-19: one code per screen/power variant.
        devices = [dict(id='amoled-47', model='fēnix 8', case_size_mm=47, screen_technology='AMOLED', solar=None),
                   dict(id='solar-47', model='fēnix 8', case_size_mm=47, screen_technology='MIP', solar=True),
                   dict(id='dual-power-47', model='fēnix 8 Dual Power', case_size_mm=47, screen_technology='MIP', solar=None)]
        rows = self._import('garmin', [
            {'partNumber': '006-B4532-00', 'name': 'fēnix® 8 Solar (47mm)', 'additionalNames': ['fēnix® 8 Dual Power (47mm)']},
            {'partNumber': '006-B4536-00', 'name': 'fēnix® 8 AMOLED (47mm/51mm)', 'additionalNames': []}], devices)
        self.assertEqual(rows, [('006-B4532-00', 'dual-power-47'), ('006-B4532-00', 'solar-47'), ('006-B4536-00', 'amoled-47')])
        usb = self._import('usb', [('Fenix 8 AMOLED', '0x51b8'), ('Fenix 8 Solar Sapphire', '0x51b5')], devices)
        self.assertEqual(usb, [('091e:51b5', 'solar-47'), ('091e:51b8', 'amoled-47')])

    def test_import_code_without_solar_skips_rows_another_code_names_solar(self):
        devices = [dict(id='pro-47', model='fēnix 9 Pro', case_size_mm=47, screen_technology='AMOLED', solar=None),
                   dict(id='pro-47-solar', model='fēnix 9 Pro', case_size_mm=47, screen_technology='MIP', solar=True)]
        rows = self._import('garmin', [
            {'partNumber': '006-B4953-00', 'name': 'fenix® 9 Pro - 47 mm', 'additionalNames': ['fenix® 9 Pro - inReach 47 mm']},
            {'partNumber': '006-B4955-00', 'name': 'fenix® 9 Pro - Solar 47 mm', 'additionalNames': []}], devices)
        self.assertEqual(rows, [('006-B4953-00', 'pro-47'), ('006-B4955-00', 'pro-47-solar')])
        # One code for a model and its Solar Edition keeps both rows open.
        shared = [dict(id='7x-pro', model='fēnix 7X Pro', variant='Historical', case_size_mm=None, solar=None),
                  dict(id='7x-pro-no-wifi', model='fēnix 7X Pro', variant='Solar (no Wi-Fi)', case_size_mm=None, solar=None)]
        rows = self._import('garmin', [
            {'partNumber': '006-B4376-00', 'name': 'fēnix® 7X Pro', 'additionalNames': ['fēnix® 7X Pro– Sapphire Solar Edition']},
            {'partNumber': '006-B4596-00', 'name': 'fēnix® 7X Pro No Wi-Fi', 'additionalNames': []}], shared)
        self.assertEqual(rows, [('006-B4376-00', '7x-pro'), ('006-B4596-00', '7x-pro-no-wifi')])

    def test_import_checks_each_product_name_of_a_code_and_applies_bare_tags(self):
        # Garmin's device list, 2026-10-19: one code names a model and its Dual
        # Power variant; another code names the AMOLED variant only.
        devices = [dict(id='crossover', model='Instinct Crossover', screen_technology='MIP', solar=False),
                   dict(id='crossover-solar', model='Instinct Crossover Solar', screen_technology='MIP', solar=True),
                   dict(id='crossover-amoled', model='Instinct Crossover AMOLED', screen_technology='AMOLED', solar=None)]
        rows = self._import('garmin', [
            {'partNumber': '006-B4155-00', 'name': 'Instinct® Crossover', 'additionalNames': ['Instinct® Crossover Dual Power']},
            {'partNumber': '006-B4678-00', 'name': 'Instinct® Crossover AMOLED', 'additionalNames': []}], devices)
        self.assertEqual(rows, [('006-B4155-00', 'crossover'), ('006-B4155-00', 'crossover-solar'),
                                ('006-B4678-00', 'crossover-amoled')])
        # "tactix 8 – 51 mm" with the tag "AMOLED" is the AMOLED 51 mm row.
        tactix = [dict(id='51-amoled', model='tactix 8', case_size_mm=51, screen_technology='AMOLED', solar=None),
                  dict(id='51-solar', model='tactix 8', case_size_mm=51, screen_technology='MIP', solar=True)]
        rows = self._import('garmin', [
            {'partNumber': '006-B4775-00', 'name': 'tactix® 8 – 47 mm, AMOLED', 'additionalNames': ['tactix® 8 – 51 mm', 'AMOLED']},
            {'partNumber': '006-B4776-00', 'name': 'tactix® 8 – 51 mm, Solar', 'additionalNames': ['tactix® 8 – 51 mm', 'Solar', 'Elite']}], tactix)
        self.assertEqual(rows, [('006-B4775-00', '51-amoled'), ('006-B4776-00', '51-solar')])
        # A model sold only as Solar keeps its row for a plain name.
        quatix = [dict(id='quatix-7x-solar', model='quatix 7X Solar', screen_technology='MIP', solar=True)]
        rows = self._import('garmin', [
            {'partNumber': '006-B3907-00', 'name': 'fēnix® 7X', 'additionalNames': ['quatix® 7X – Solar Edition']},
            {'partNumber': '006-B3910-00', 'name': 'fēnix® 7X', 'additionalNames': ['quatix® 7X']}], quatix)
        self.assertEqual(rows, [('006-B3907-00', 'quatix-7x-solar'), ('006-B3910-00', 'quatix-7x-solar')])

    def test_import_reads_trademark_names_generation_alias_and_stated_sizes(self):
        devices = [dict(id='enduro-2', model='Enduro 2', case_size_mm=None),
                   dict(id='epix-pro', model='epix Pro (Gen 2)', variant='Historical', case_size_mm=None),
                   dict(id='epix-pro-47', model='epix Pro (Gen 2)', case_size_mm=47, screen_technology='AMOLED'),
                   dict(id='quatix-7-pro', model='quatix 7 Pro', case_size_mm=None)]
        rows = self._import('garmin', [
            {'partNumber': '006-B4341-00', 'name': 'Enduro™ 2', 'additionalNames': []},
            {'partNumber': '006-B4313-00', 'name': 'epix™ Pro (47mm)', 'additionalNames': ['quatix® 7 Pro']}], devices)
        # The unsized legacy row is left to the stated 47 mm row.
        self.assertEqual(rows, [('006-B4313-00', 'epix-pro-47'), ('006-B4313-00', 'quatix-7-pro'), ('006-B4341-00', 'enduro-2')])

    def test_import_splits_libmtp_product_lists_only_into_full_names(self):
        devices = [dict(id='fenix-7x', model='fēnix 7X', case_size_mm=51), dict(id='enduro-2', model='Enduro 2'),
                   dict(id='fenix-7', model='fēnix 7', case_size_mm=47), dict(id='fenix-5', model='fēnix 5')]
        rows = self._import('usb', [('Fenix 7X/tactix 7/quatix 7X Solar/Enduro 2', '0x4f43'), ('Fenix 5/5S/5X Plus', '0x4b54')], devices)
        self.assertEqual(rows, [('091e:4f43', 'enduro-2'), ('091e:4f43', 'fenix-7x')])

    def test_trademark_signs_do_not_join_the_model_name(self):
        from terento_catalog.identity_assessment import model_label
        self.assertEqual(model_label('epix™ Pro (51mm)'), 'epix pro')
        self.assertEqual(model_label('Enduro™ 2'), model_label('Enduro 2'))

    def test_admin_keeps_repeated_sources_actionable_with_one_technical_disclosure(self):
        from terento_catalog.admin import _identity_mapping_markup
        mapping = dict(self.mappings[0], id=1, history=[])
        rendered = _identity_mapping_markup(dict(id='test', identityMappings=[mapping, dict(mapping, id=2, source_version='2')]), 'csrf')
        self.assertIn("class='identity-mappings'", rendered)
        self.assertEqual(rendered.count("class='admin-card identity-mapping-source'"), 2)
        self.assertEqual(rendered.count('<summary>Technical details</summary>'), 1)
        self.assertNotIn('identity-mapping-code', rendered)
        self.assertNotIn('2 sources', rendered)

    def test_identity_form_escapes_catalog_text_and_mapping_requires_a_reason(self):
        from terento_catalog.admin import _identity_mapping_markup, _identity_review_form
        assessment = assess_identity(self.event, [self.device], self.mappings)
        rendered = _identity_review_form('key', [{'identity_assessment': assessment}], csrf_token='t',
                                         identity_devices=[dict(self.device, variant='<script>unsafe</script>')],
                                         return_to='/admin', id_suffix='x')
        self.assertIn('&lt;script&gt;', rendered)
        self.assertNotIn('<script>unsafe', rendered)
        device = dict(id='test', identityMappings=[dict(self.mappings[0], id=1, review_reason='Evidence', history=[])])
        self.assertIn('required', _identity_mapping_markup(device, 'csrf'))

    def test_review_summary_keeps_alternatives_collapsed(self):
        from terento_catalog.admin import _identity_recommendation
        other = dict(self.device, id='other', case_size_mm=47)
        assessment = assess_identity(self.event, [self.device, other], self.mappings)
        results = [{'identity_assessment': assessment}]
        self.assertEqual(_identity_recommendation(results)['deviceId'], self.device['id'])

    def test_review_does_not_guess_when_ambiguous_missing_or_conflicting(self):
        from terento_catalog.admin import _identity_recommendation
        assessment = assess_identity(self.event, [self.device], self.mappings[:1])
        self.assertEqual(_identity_recommendation([{'identity_assessment': assessment}])['deviceId'], self.device['id'])
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
        from terento_catalog.admin import _identity_recommendation
        other = dict(self.device, id='microled', screen_technology='MicroLED')
        mappings = self.mappings + [dict(m, device_model_id=other['id']) for m in self.mappings]
        assessment = assess_identity(dict(self.event, rawMTPModel='fenix 8 Pro 51mm inReach'), [self.device, other], mappings)
        results = [{'identity_assessment': assessment}]
        self.assertEqual(assessment['facts']['screenTechnology'], [])
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
        # Device identity is the last section; the separate "Identity incomplete" notice is gone
        # (owner decision 2026-10-06).
        self.assertLess(markup.index("class='diagnostic-detail-summary'"), markup.index("class='diagnostic-section diagnostic-identity-section'"))
        self.assertNotIn("Identity incomplete", markup)
        self.assertIn("Assign the exact catalog model in Device identity below.", markup)
        self.assertIn(">Device identity</h3>", markup)
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
        from terento_catalog.admin import _identity_recommendation
        self.assertEqual(_identity_recommendation([{'identity_assessment': result}])['deviceId'], solar['id'])

    def test_display_type_solar_is_not_a_screen_and_variant_mip_is(self):
        solar_event = dict(self.event, rawMTPModel='fenix 8 Pro 51mm', displayType='Solar', variant=None)
        result = assess_identity(solar_event, [self.device], self.mappings)
        self.assertEqual(result['facts']['solar'][0]['value'], True)
        self.assertEqual(result['facts']['screenTechnology'], [])
        mip_result = assess_identity(dict(self.event, rawMTPModel='fenix 8 Pro 51mm', displayType='Solar', variant='51 mm MIP'), [self.device], self.mappings)
        self.assertEqual(mip_result['facts']['screenTechnology'][0]['value'], 'MIP')

    def test_true_false_and_unknown_features_keep_their_meaning(self):
        true_device = dict(self.device, id='solar', solar=True, inreach=True)
        true_result = assess_identity(dict(self.event, rawMTPModel='fenix 8 Pro 51mm Solar inReach'), [true_device], [])
        true_candidate = true_result['candidates'][0]
        true_features = true_candidate['checks'][0]['features']
        self.assertEqual({item['name']: item['evidence'][0]['value'] for item in true_features}, {'solar': True, 'inreach': True})

        false_result = assess_identity(dict(self.event, rawMTPModel='fenix 8 Pro 51mm'), [self.device], [])
        false_features = {item['name']: item for item in false_result['candidates'][0]['checks'][0]['features']}
        self.assertEqual(false_features['solar']['state'], 'MISSING')
        self.assertEqual(false_features['solar']['expected'], False)

        unknown_device = dict(self.device, id='unknown-features', solar=None, inreach=None)
        unknown_result = assess_identity(dict(self.event, rawMTPModel='fenix 8 Pro 51mm'), [unknown_device], [])
        unknown_features = {item['name']: item for item in unknown_result['candidates'][0]['checks'][0]['features']}
        self.assertEqual((unknown_features['solar']['state'], unknown_features['solar']['expected']), ('MISSING', None))
        self.assertEqual((unknown_features['inreach']['state'], unknown_features['inreach']['expected']), ('MISSING', None))

    def test_multiple_variants_are_not_selected_by_order_and_labels_expose_inreach(self):
        from terento_catalog.admin import _identity_device_options, _identity_recommendation
        first = dict(self.device, id='fenix-47-no-inreach', inreach=False, screen_technology='AMOLED')
        second = dict(self.device, id='fenix-47-inreach', inreach=True, screen_technology='AMOLED')
        result = assess_identity({'model': 'fēnix 8 Pro', 'caseSizeMm': 51}, [first, second], [])
        self.assertIsNone(_identity_recommendation([{'identity_assessment': result}]))
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

    def test_label_normalization_is_cached_and_unchanged(self):
        import re
        import unicodedata
        from terento_catalog import identity_assessment as module

        def reference_normalized(value):
            text = unicodedata.normalize('NFKD', str(value or '')).lower()
            text = ''.join(c for c in text if not unicodedata.combining(c))
            return re.sub(r'[^a-z0-9]+', ' ', text).strip()

        def reference_model_label(value):
            text = reference_normalized(value).removeprefix('garmin ')
            return re.split(r'\b(?:\d{2,3}\s*mm|amoled|microled|mip|solar|sapphire|inreach)\b', text)[0].strip()

        for value in (None, '', 0, 47, False, 'Garmin fēnix 8 Pro 51mm AMOLED', 'ＥＰＩＸ Pro (Gen 2)',
                      'Forerunner® 965', '  tactix 7 – Solar  ', 'Identity pending'):
            with self.subTest(value=value):
                self.assertEqual(module.normalized(value), reference_normalized(value))
                self.assertEqual(module.model_label(value), reference_model_label(value))
        # A device page assesses hundreds of reports against the whole catalog;
        # each catalog name is normalized once, not once per report.
        devices = [dict(id=f'device-{index}', model=f'Catalog Watch {index}', case_size_mm=47)
                   for index in range(40)]
        module._model_label_text.cache_clear()
        for index in range(25):
            assess_identity(dict(self.event, rawMTPModel=f'fenix 8 Pro 51mm unit {index}'), devices, self.mappings)
        self.assertLessEqual(module._model_label_text.cache_info().misses, len(devices) + 2 * 25 + 5)
