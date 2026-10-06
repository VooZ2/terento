"""Shared diagnostic recovery controls, evidence boundaries and exact-model history."""
import unittest
from html.parser import HTMLParser
from terento_catalog.admin import (_diagnostic_detail_dialog, _github_issue_controls,
    _installation_explanation, device_detail_page, github_issue_queue_page)
from terento_catalog.update_diagnostics import (update_diagnostics_page, _update_issue_report,
    update_history_markup)

EVENT = '22222222-2222-4222-8222-222222222222'
MODEL = 'fenix-8-51-amoled'
DEVICE = {'id': MODEL, 'model': 'fēnix 8', 'variant': '51 mm, AMOLED', 'case_size_mm': 51, 'screen_technology': 'AMOLED'}


class Controls(HTMLParser):
    def __init__(self, markup):
        super().__init__(); self.details = []; self.prepare_hidden = []
        self.feed(markup)
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'details': self.details.append('open' in attrs)
        if 'data-github-create' in attrs: self.prepare_hidden.append(any(not x for x in self.details))
    def handle_endtag(self, tag):
        if tag == 'details' and self.details: self.details.pop()


class DiagnosticParityTests(unittest.TestCase):
    def report(self, **fields):
        row = dict(event_id=EVENT, operation_id=EVENT, provider='bbbike', region='FRA', outcome='FAILED',
            canonical_device_model_id=MODEL, device=DEVICE, diagnostic_status='ACTIVE',
            payload={'failureCode': 'UPDATE_FAILED_WRITE', 'failureStage': 'write', 'model': 'Reported model',
                'variant': 'reported', 'mapRelease': '2026-09', 'writeStarted': True, 'oldMapPreserved': True,
                'terentoVersion': 'beta.15', 'appBuild': '37'})
        return {**row, **fields}

    def test_same_visible_recovery_hierarchy_and_shared_controls(self):
        install = _diagnostic_detail_dialog('fēnix 8 · 51 mm', EVENT,
            [{'event_id': EVENT, 'canonical_device_model_id': MODEL, 'phase_outcome': 'FAILED',
              'provider': 'bbbike', 'region': 'FRA', 'failure_stage': 'verify', 'failure_code': 'INSTALL_FAILED_HASH_MISMATCH'}],
            resolved=False, csrf_token='csrf', identity_devices=[DEVICE])
        update = update_diagnostics_page({'detail': self.report()}, {'username': 'admin'}, 'csrf').decode()
        for body in (install, update):
            for text in ('What happened', 'Next action', 'Safety facts', 'Prepare GitHub issue',
                         'Copy issue report', 'Preview issue report', 'Link issue', 'Review administration', 'Technical details'):
                self.assertIn(text, body)
            self.assertEqual(Controls(body).prepare_hidden, [False])
            self.assertIn("data-url-limit='7000'", body)
            self.assertIn("role='status' aria-live='polite'", body)
        self.assertIn('Installation failed</h2>', install)
        self.assertIn('Map update failed</h2>', update)
        for body in (install, update): self.assertIn('France · BBBike', body)
        self.assertIn('did not pass device verification', install)
        self.assertNotIn('Installation error', install)
        self.assertIn("action='/admin/diagnostics/resolve'", install)
        self.assertIn("action='/admin/update-diagnostics/resolve'", update)

    def test_report_uses_native_field_names_and_allowlist(self):
        row = self.report(); row['payload'].update({'unitId': 'PRIVATE UNIT', 'rawLogs': 'PRIVATE LOG',
            'localPath': '/private/secret', 'mapRelease': '/Users/alice/map secret=EXPOSED'})
        title, body = _update_issue_report(row)
        self.assertIn('Map version:', body)
        self.assertIn('redacted', body)
        for private in ('PRIVATE UNIT', 'PRIVATE LOG', '/private/secret', 'EXPOSED', '/Users/alice'):
            self.assertNotIn(private, title + body)
        title, body = _update_issue_report(self.report())
        self.assertIn('Map version: 2026-09', body)
        self.assertIn('Previous map confirmed preserved: Yes', body)
        controls = _github_issue_controls(title, body * 200, issue=None, csrf_token='csrf', identifier=EVENT, return_to='/admin/update-diagnostics')
        self.assertIn("data-prefilled='false'", controls)
        self.assertIn('Report is too large to prefill', controls)

    def test_structured_context_and_resolution_are_reviewable(self):
        row = self.report(diagnostic_status='RESOLVED', resolution_code='FIXED',
            resolution_note='Reviewed <unsafe>', resolved_at='2026-10-02T12:00:00Z')
        row['payload'].update(automaticFinishingResult='FAILED', transferProgressBucket='25_49',
            firmwareVersion='19.10', transport='MTP',
            failureContext={'boundary': 'readback', 'classificationSource': 'native',
                'devicePresence': 'present', 'nativeCodeNamespace': 'terento_file_range', 'nativeResultCode': -1},
            originalFailureContext={'boundary': 'write', 'classificationSource': 'derived', 'devicePresence': 'unknown'})
        _, body = _update_issue_report(row)
        for fact in ('Automatic finishing result: FAILED', 'Firmware: 19.10',
                     'Failure boundary: readback', 'Failure native result code: -1', 'Original failure boundary: write'):
            self.assertIn(fact, body)
        page = update_diagnostics_page({'detail': row}, {'username': 'admin'}, 'csrf').decode()
        self.assertIn('Resolution reason</dt><dd>FIXED', page)
        self.assertIn('Reviewed &lt;unsafe&gt;', page)
        self.assertIn('Resolved at', page)
        self.assertIn('Reopen diagnostic', page)
        row['payload']['failureContext']['rawLogs'] = 'PRIVATE CONTEXT'
        _, body = _update_issue_report(row)
        self.assertNotIn('PRIVATE CONTEXT', body)
        self.assertIn('Failure boundary: unavailable', body)

    def test_identity_link_requires_assessed_model(self):
        known = update_diagnostics_page({'detail': self.report()}, {'username': 'admin'}, 'csrf').decode()
        unknown = update_diagnostics_page({'detail': self.report(canonical_device_model_id=None, device=None)}, {'username': 'admin'}, 'csrf').decode()
        self.assertIn('/admin/devices/' + MODEL, known)
        self.assertNotIn('/admin/devices/' + MODEL, unknown)
        self.assertIn('exact identity unassigned', unknown)
        self.assertIn('Reported model', unknown)

    def test_queue_joined_catalog_names_are_authoritative(self):
        row = self.report(device=None, canonical_device_model_name='fēnix 8',
            canonical_device_variant='51 mm, AMOLED', linked_github_issue='#325')
        body = github_issue_queue_page([], [], {'username': 'admin'}, 'csrf', update_diagnostics=[row]).decode()
        self.assertIn('>fēnix 8</a>', body)
        self.assertIn('51 mm, AMOLED', body)
        self.assertNotIn('Catalog model', body)
        self.assertNotIn('Reported model', body)
        row['canonical_device_model_id'] = None
        body = github_issue_queue_page([], [], {'username': 'admin'}, 'csrf', update_diagnostics=[row]).decode()
        self.assertNotIn('/admin/devices/' + MODEL, body)
        self.assertIn('exact identity unassigned', body)

    def test_model_update_history_and_counts_remain_separate(self):
        device = {**DEVICE, 'installationStats': {'attempts': 12, 'successful': 11, 'failed': 1},
            'update_statistics': {'successfulUpdateCount': 7, 'failedUpdateCount': 2, 'notStartedCount': 1}}
        body = device_detail_page(device, {'username': 'admin'}, 'csrf',
            update_history={'rows': [self.report()], 'device_id': MODEL, 'offset': 50, 'has_more': True}).decode()
        self.assertIn('Installation history', body); self.assertIn('Update history', body)
        self.assertIn('>Update reports</h2>', body)
        self.assertNotIn("admin-glossary-link", body)
        self.assertIn('outcome=succeeded', body); self.assertIn('outcome=failed', body)
        self.assertIn('updateOffset=100', body); self.assertIn('updateOffset=0', body)
        self.assertIn('diagnosticId=' + EVENT, body)
        from terento_catalog.admin import ADMIN_GLOSSARY
        self.assertIn('never change installation totals', dict((a, d) for a, _, d in ADMIN_GLOSSARY)['update-report'])

    def test_unknown_reason_and_update_queue_do_not_guess_or_reuse_install(self):
        reason, action = _installation_explanation([{'phase_outcome': 'FAILED', 'failure_code': 'UNRECOGNIZED'}])
        self.assertIn('does not establish the cause', reason); self.assertIn('local Terento diagnostic report', action)
        body = github_issue_queue_page([], [], {'username': 'admin'}, 'csrf',
            update_diagnostics=[self.report(linked_github_issue='#325')]).decode()
        self.assertIn('Inspect update', body); self.assertIn('diagnosticId=' + EVENT, body)
        self.assertNotIn("<dialog class='diagnostic-detail-dialog'", body)
        success = self.report(outcome='SUCCEEDED', linked_github_issue='#325')
        rendered = update_diagnostics_page({'detail': success}, {'username': 'admin'}, 'csrf').decode()
        self.assertIn('The update succeeded', rendered)
        self.assertNotIn("action='/admin/update-diagnostics/resolve'", rendered)

if __name__ == '__main__': unittest.main()
