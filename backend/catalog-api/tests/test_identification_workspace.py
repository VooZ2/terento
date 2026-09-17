"""Presentation contract: source decisions are never exact-model approval."""
import unittest
from copy import deepcopy
from terento_catalog.admin import device_identification_page


def mapping(status='PENDING', **changes):
    return dict(dict(id=1, kind='XML_PART_NUMBER', value='006-B4953-00', status=status,
                     source_url='https://apps.garmin.com/source', source_version='reviewed revision',
                     source_names=['fenix® 9 Pro - 47 mm', 'fenix® 9 Pro - inReach 47 mm'], history=[]), **changes)


def device(key='watch', **changes):
    return dict(dict(id=key, model='fēnix 9 Pro', variant='47 mm, AMOLED, inReach',
                     identityMappings=[mapping()]), **changes)


class IdentificationWorkspaceTests(unittest.TestCase):
    def render(self, devices, **kwargs):
        return device_identification_page(devices, {'username': 'operator'}, 'csrf-test', **kwargs).decode()

    def test_rejected_only_is_not_presented_as_approved_or_ready(self):
        body = self.render([device(identityMappings=[mapping('REJECTED')])])
        content = body.split("class='identification-choices'", 1)[1].split('</main>', 1)[0]
        self.assertIn('1 rejected', content)
        self.assertNotIn('Sources reviewed', content)
        self.assertNotIn('identification-approved', content)

    def test_pending_models_sort_first_and_codes_are_searchable(self):
        rows = [device('approved', model='AAA', identityMappings=[mapping('APPROVED')]), device('pending', model='ZZZ')]
        body = self.render(rows)
        self.assertLess(body.index('device=pending'), body.index('device=approved'))
        self.assertIn('device=pending', self.render(rows, query='006-b4953'))
        self.assertNotIn("name='mapping_id'", body)

    def test_shared_code_shows_other_models_and_each_review_state(self):
        rows = [device(), device('other', variant='51 mm', identityMappings=[mapping('REJECTED')])]
        before = deepcopy(rows)
        body = self.render(rows, device_id='watch')
        for text in ('Compare 1 other model', 'device=other', '1 rejected', 'Model names in the source',
                     'fenix® 9 Pro - inReach 47 mm', 'not live results', 'Missing reference sources:', 'USB connection code'):
            self.assertIn(text, body)
        self.assertEqual(rows, before)

    def test_review_has_no_default_approval_and_preserves_exact_target(self):
        body = self.render([device()], device_id='watch')
        for text in ("name='status' required><option value=''>Choose a decision", "name='mapping_id' value='1'",
                     "name='csrf_token' value='csrf-test'", "name='reason' required", 'Save source decision',
                     'does not change saved installations, allow installation or publish compatibility',
                     'If the evidence is unclear, leave it pending.', "action='/admin/devices/identity-mapping'"):
            self.assertIn(text, body)

    def test_unknown_model_and_empty_search_give_recovery(self):
        self.assertIn('select an existing model', self.render([device()], device_id='missing'))
        self.assertIn('Clear search', self.render([device()], query='<missing>'))
        self.assertIn('&lt;missing&gt;', self.render([device()], query='<missing>'))
        self.assertIn('Open device catalog', self.render([]))
        self.assertIn('There is nothing to approve', self.render([device(identityMappings=[])], device_id='watch'))

    def test_source_values_are_escaped_and_unsafe_source_is_not_linked(self):
        body = self.render([device(identityMappings=[mapping(source_url='javascript:alert(1)',
                    source_names=['<img src=x onerror=alert(1)>'], review_reason='<script>bad</script>')])], device_id='watch')
        self.assertNotIn('href="javascript:', body)
        self.assertNotIn('<img src=x', body)
        self.assertIn('&lt;script&gt;bad', body)
        self.assertIn('Source link unavailable', body)

    def test_code_priority_and_only_first_pending_code_expands(self):
        rows = [device(identityMappings=[mapping(kind='RETAIL_SKU', value='010-1'), mapping(), mapping(kind='USB', value='091e:5359')])]
        body = self.render(rows, device_id='watch')
        self.assertLess(body.index('Code reported by the watch ·'), body.index('USB connection code ·'))
        self.assertLess(body.index('USB connection code ·'), body.index('Retail product code ·'))
        self.assertEqual(body.count("class='identity-mapping-code' open"), 1)

    def test_approved_and_rejected_decisions_keep_change_and_history_available(self):
        for status in ('APPROVED', 'REJECTED'):
            body = self.render([device(identityMappings=[mapping(status, history=[dict(previous_status='PENDING', new_status=status,
                              reason='Evidence checked', reviewed_by=1, created_at='2026-09-15')])])], device_id='watch')
            self.assertIn('Change decision', body)
            self.assertIn('Previous decisions', body)
            self.assertIn('Evidence checked', body)
            self.assertNotIn("class='identity-mapping-code' open", body)

    def test_review_feedback_and_singular_counts_are_wired(self):
        body = self.render([device()])
        self.assertIn('1 model needs source review.', body)
        self.assertIn('1 model shown', body)
        self.assertIn("document.querySelectorAll('.identity-mapping-review')", body)
        self.assertIn('controller.abort(), 20000', body)
        self.assertIn('Could not confirm the save.', body)
        self.assertIn('Your session expired.', body)
        self.assertIn("if (!response.redirected) throw new Error('save')", body)
