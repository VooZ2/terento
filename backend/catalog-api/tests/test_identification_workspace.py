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
        content = body.split("id='identification-list'", 1)[1].split('</main>', 1)[0]
        self.assertIn('Rejected', content)
        self.assertNotIn('Sources reviewed', content)
        self.assertNotIn('identification-approved', content)

    def test_workspace_name_is_specific_and_duplicate_intro_is_removed(self):
        body = self.render([device()], device_id='watch')
        self.assertIn('<title>Model sources · Terento</title>', body)
        self.assertIn('<h1>Model sources</h1>', body)
        self.assertNotIn('Review required', body)
        self.assertNotIn('identification-next', body)
        self.assertNotIn('Model codes', body)
        self.assertNotIn('Review guidance', body)
        self.assertIn('<summary>Technical details</summary>', body)
        self.assertIn('Missing imported sources:', body)
        for heading in ('Source says', 'Catalog model', 'Confirm'):
            self.assertIn(f'<h3>{heading}</h3>', body)
        # Source and catalog model are compared side by side.
        compare = body.split("class='identification-compare'", 1)[1].split("</div>\n", 1)[0]
        self.assertLess(compare.index('Source says'), compare.index('Catalog model'))

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
        for text in ('Same code', 'device=other', 'Rejected', 'Source says',
                     'fenix® 9 Pro - inReach 47 mm', 'Missing imported sources:', 'USB connection code'):
            self.assertIn(text, body)
        self.assertNotIn('Compare 1 other model', body)
        self.assertEqual(rows, before)

    def test_review_has_no_default_approval_and_preserves_exact_target(self):
        body = self.render([device()], device_id='watch')
        for text in ("name='status' value='APPROVED'>Approve match", "name='status' value='REJECTED'>Reject match",
                     "name='mapping_id' value='1'", "name='csrf_token' value='csrf-test'", "name='reason' required",
                     'does not change installations, installation permission or public compatibility',
                     "action='/admin/devices/identity-mapping'", 'new FormData(form, event.submitter)'):
            self.assertIn(text, body)
        self.assertNotIn("<select name='status'", body)

    def test_unknown_model_and_empty_search_give_recovery(self):
        self.assertIn('select an existing model', self.render([device()], device_id='missing'))
        self.assertIn('Clear search', self.render([device()], query='<missing>'))
        self.assertIn('&lt;missing&gt;', self.render([device()], query='<missing>'))
        self.assertIn('Open device catalog', self.render([]))
        self.assertIn('No source reported', self.render([device(identityMappings=[])], device_id='watch'))

    def test_source_values_are_escaped_and_unsafe_source_is_not_linked(self):
        body = self.render([device(identityMappings=[mapping(source_url='javascript:alert(1)',
                    source_names=['<img src=x onerror=alert(1)>'], review_reason='<script>bad</script>')])], device_id='watch')
        self.assertNotIn('href="javascript:', body)
        self.assertNotIn('<img src=x', body)
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', body)
        self.assertIn('Source link unavailable', body)

    def test_code_priority_is_preserved_inside_one_technical_disclosure(self):
        rows = [device(identityMappings=[mapping(kind='RETAIL_SKU', value='010-1'), mapping(), mapping(kind='USB', value='091e:5359')])]
        body = self.render(rows, device_id='watch')
        self.assertLess(body.index('006-B4953-00'), body.index('091e:5359'))
        self.assertLess(body.index('091e:5359'), body.index('010-1'))
        self.assertEqual(body.count('<summary>Technical details</summary>'), 1)
        self.assertNotIn('identity-mapping-code', body)

    def test_approved_and_rejected_decisions_keep_change_and_history_available(self):
        for status in ('APPROVED', 'REJECTED'):
            body = self.render([device(identityMappings=[mapping(status, history=[dict(previous_status='PENDING', new_status=status,
                              reason='Evidence checked', reviewed_by=1, created_at='2026-09-15')])])], device_id='watch')
            # The decision state is a status pill: text plus an icon.
            decision = body.split("class='identification-existing-decision'>", 1)[1].split('</p>', 1)[0]
            self.assertIn('<strong>Current decision:</strong>', decision)
            self.assertIn(f"data-status='{status}'", decision)
            self.assertIn("class='admin-icon", decision)
            self.assertIn(f'<span>{status.title()}</span>', decision)
            self.assertIn('Decision history', body)
            self.assertIn('Evidence checked', body)
            self.assertIn('Approve match', body)
            self.assertIn('Reject match', body)

    def test_review_feedback_and_singular_counts_are_wired(self):
        body = self.render([device()])
        self.assertIn("data-source-filter='pending' aria-pressed='true'>Needs review</button>", body)
        self.assertIn("id='identification-results-count' aria-live='polite'>1 model</p>", body)
        self.assertNotIn('model shown', body)
        self.assertIn("document.querySelectorAll('.identity-mapping-review')", body)
        self.assertIn('controller.abort(), 20000', body)
        self.assertIn('Could not confirm the save.', body)
        self.assertIn('Your session expired.', body)
        self.assertIn("if (!response.redirected) throw new Error('save')", body)

    def test_summary_is_one_kpi_card_with_plain_numbers(self):
        rows = [device('pending'), device('approved', identityMappings=[mapping('APPROVED')]),
                device('rejected', identityMappings=[mapping('REJECTED')]), device('missing', identityMappings=[])]
        main = self.render(rows).split('<main', 1)[1]
        opening = "<section class='admin-card installation-kpis identification-kpis'"
        self.assertEqual(main.count(opening), 1)
        card = main.split(opening, 1)[1].split('</section>', 1)[0]
        for label in ('Needs review', 'Approved', 'Rejected', 'No source'):
            self.assertIn(f"<span class='admin-metric-label'>{label}</span>", card)
        self.assertEqual(card.count(">1</strong>"), 4)
        # Plain numbers: no scope chips, icons or failure tone.
        for absent in ('admin-scope-chip', 'admin-icon', "data-tone='danger'", '>Now<', 'All time'):
            self.assertNotIn(absent, card)

    def test_filter_bar_uses_installations_design_with_server_search(self):
        body = self.render([device(), device('approved', identityMappings=[mapping('APPROVED')])])
        opening = ("<form method='get' action='/admin/device-identification' class='filter-bar admin-filter-bar "
                   "identification-filter-bar' id='identification-filters' role='search'>")
        bar = body.split(opening, 1)[1].split('</form>', 1)[0]
        self.assertLess(bar.index("class='quick-filter-group'"), bar.index("id='identification-search'"))
        self.assertLess(bar.index("id='identification-search'"), bar.index("class='results-count'"))
        self.assertLess(bar.index("class='results-count'"), bar.index('data-filter-clear'))
        self.assertIn("data-default-filter='pending'", bar)
        for state, label in (('all', 'All'), ('pending', 'Needs review'), ('approved', 'Approved'),
                             ('rejected', 'Rejected'), ('missing', 'No source')):
            pressed = 'true' if state == 'pending' else 'false'
            self.assertIn(f"data-source-filter='{state}' aria-pressed='{pressed}'>{label}</button>", bar)
        self.assertIn("name='q'", bar)
        self.assertIn("aria-label='Clear model source filters' hidden>Clear</a>", bar)
        searched = self.render([device()], query='fēnix')
        self.assertIn("value='fēnix'", searched)
        self.assertIn("data-has-query='true' aria-label='Clear model source filters'>Clear</a>", searched)
        # Needs review is not preselected when no listed model needs review.
        reviewed = self.render([device(identityMappings=[mapping('APPROVED')])])
        self.assertIn("data-source-filter='all' aria-pressed='true'>All</button>", reviewed)

    def test_table_sorts_without_records_line_and_uses_shared_pagination(self):
        body = self.render([device()])
        table = body.split("<table class='admin-table identification-table'>", 1)[1].split('</table>', 1)[0]
        self.assertIn("<th scope='col'>Model</th><th scope='col'>Garmin code</th><th scope='col'>Source</th>"
                      "<th scope='col' class='column-status'>State</th></tr>", table)
        self.assertNotIn('Action', table)
        self.assertIn("data-sort-value='0'", table)
        self.assertIn("class='provider-pagination' id='identification-pagination'", body)
        self.assertIn("addEventListener('admin:table-sorted'", body)
        self.assertNotIn('records', body.split('<main', 1)[1].split('<script', 1)[0])

    def test_detail_is_admin_cards_and_keeps_workflow_and_post_form(self):
        main = self.render([device(), device('next', model='ZZZ')], device_id='watch').split('<main', 1)[1].split('</main>', 1)[0]
        self.assertLess(main.index("class='back-link identification-workspace-nav'"), main.index('<h1>Model sources</h1>'))
        self.assertIn('Next in queue', main)
        self.assertIn("<article class='admin-card identity-mapping-source'>", main)
        self.assertIn("<details class='admin-card admin-disclosure identification-technical'>", main)
        self.assertNotIn('installation-kpis', main)
        self.assertNotIn('identification-filters', main)
        self.assertEqual(main.count("method='post' action='/admin/devices/identity-mapping'"), 1)
        self.assertIn("name='csrf_token' value='csrf-test'", main)
