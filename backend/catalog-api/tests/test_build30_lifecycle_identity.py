import json
from pathlib import Path
import unittest
from uuid import uuid4

from terento_catalog.identity_assessment import assess_identity
from terento_catalog.map_events import validate_map_event, MapEventValidationError
from terento_catalog.admin import _identity_checks_markup, _overview_map_activity_row


class Build30Tests(unittest.TestCase):
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
        for text in ('006-B4953-00', '091e:5359', 'Catalog mapping not confirmed',
                     'Reported device: fenix 9 Pro - inReach, 47mm'):
            self.assertIn(text, markup)
        missing = assess_identity(self.event(usbVendorID=None), [self.device()], [])
        self.assertIn('Not received', _identity_checks_markup([dict(current_identity_assessment=missing)]))

    def test_normal_selector_excludes_conflicting_variants(self):
        from terento_catalog.admin import _diagnostic_detail_dialog
        devices = [self.device(), self.device(id='wrong-size', case_size_mm=51)]
        assessment = assess_identity(self.event(), devices, [])
        result = dict(identity_assessment=assessment, identity_resolution_state='UNRESOLVED',
                      operation_id='preview', phase_outcome='SUCCEEDED', provider='custom')
        markup = _diagnostic_detail_dialog('fenix 9 Pro', 'preview', [result], resolved=False,
                    csrf_token='test', identity_devices=devices)
        self.assertIn("value='fenix9-47' selected", markup)
        self.assertIn("<div hidden>", markup)
        self.assertIn("Model selected from the reported device.", markup)
        self.assertNotIn("<option value='wrong-size'", markup)
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
        self.assertIn('Screen / Solar variant', markup)
        self.assertIn("<option value='inreach'>AMOLED · Solar: not confirmed</option>", markup)
        self.assertIn("<option value='inreach-solar'>MIP · Solar: yes</option>", markup)
        self.assertNotIn("<option value='generic'", markup)
        self.assertNotIn("<option value='generic-solar'", markup)
        self.assertEqual(len(assessment['candidates']), 4)  # authoritative evidence unchanged
        self.assertEqual(assessment['state'], 'UNRESOLVED')

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

    def test_download_title_expands_start_duration_finish_and_preserves_map_link(self):
        row = dict(event_type='DOWNLOAD_SUCCEEDED', provider_id='freizeitkarte', region='FRA',
                   lifecycle=[dict(type='DOWNLOAD_STARTED', at='2026-09-15T23:59:00Z'),
                              dict(type='DOWNLOAD_PROCESSING', at='2026-09-16T00:01:00Z'),
                              dict(type='DOWNLOAD_SUCCEEDED', at='2026-09-16T00:01:30Z')])
        markup = _overview_map_activity_row(row)
        summary = markup.split('<summary>')[1].split('</summary>')[0]
        self.assertIn('Download completed', summary)
        self.assertIn('download-context', summary)
        self.assertIn('/admin/map-statistics?', summary)
        self.assertNotIn('Download history', markup)
        self.assertNotIn("class='download-history' open", markup)
        self.assertIn('>2m 30s</span>', markup)
        self.assertIn('2026-09-15T23:59:00', markup)
        self.assertIn('2026-09-16T00:01:30', markup)
        self.assertEqual(markup.count("class='download-elapsed'"), 1)
        self.assertNotIn('>0s</span>', markup)
        row['lifecycle'][0]['at'] = None
        self.assertNotIn('download-elapsed', _overview_map_activity_row(row))


    def test_download_history_uses_requested_fontawesome_icons(self):
        phases = ('STARTED', 'PROCESSING', 'SUCCEEDED')
        row = dict(event_type='DOWNLOAD_SUCCEEDED', lifecycle=[
            dict(type='DOWNLOAD_' + phase, at='2026-09-14T12:00:00Z') for phase in phases])
        markup = _overview_map_activity_row(row)
        for phase, icon in zip(phases, ('hourglass-start', 'spinner', 'hourglass-end')):
            self.assertIn('fa-' + icon, markup)
            self.assertIn(phase.title(), markup)
        self.assertEqual(markup.count('Font Awesome Free 7.3.1'), 4)
        self.assertNotIn('fa-spin', markup.replace('fa-spinner', ''))


    def test_admin_shows_missing_outcome_component_and_timeline(self):
        row = dict(event_type='DOWNLOAD_PROCESSING', component_kind='contours',
                   lifecycle=[dict(type='DOWNLOAD_STARTED', at='2026-09-14T12:00:00Z'),
                              dict(type='DOWNLOAD_PROCESSING', at='2026-09-14T12:01:00Z')])
        markup = _overview_map_activity_row(row)
        for text in ('Outcome not received', 'Contours', "class='download-history'", 'Processing'):
            self.assertIn(text, markup)
        legacy = _overview_map_activity_row(dict(event_type='DOWNLOAD_STARTED', has_recorded_outcome=True))
        self.assertIn('Outcome recorded', legacy)
        self.assertNotIn('Outcome not received', legacy)
        for event_type in ('DOWNLOAD_CANCELLED', 'DOWNLOAD_INTERRUPTED'):
            self.assertNotIn('failed', _overview_map_activity_row(dict(event_type=event_type)))
