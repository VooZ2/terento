"""Installations, Devices and model detail on the shared kit (ADM-06/12/13, DES-01)."""

from __future__ import annotations

import unittest

from admin_test_utils import metric_tone, metric_value
from terento_catalog.admin import (
    _admin_device_payload,
    _diagnostic_detail_dialog,
    _operation_result,
    dashboard_page,
    device_detail_page,
    devices_page,
)


DEVICE_ROW = {
    "device_id": "garmin-fenix-8-47", "model": "fēnix 8", "variant": "47 mm", "family_name": "fēnix",
    "map_capable": True, "support_status": "SUPPORTED", "active": True,
    "attempted_install_count": 2, "successful_install_count": 1, "failed_install_count": 1,
    "usb_identities": [],
}
CATALOG = [
    {"device_id": f"model-{index}", "model": f"Watch {index}", "variant": "47 mm"} for index in range(12)
]


class EvidenceFromStoredFactTests(unittest.TestCase):
    def test_name_classifier_never_sets_evidence(self):
        # "fēnix" is recognised as map-capable by the name classifier, but the
        # stored catalog fact is No and there are no successes (ADM-12).
        stored_no = _admin_device_payload([dict(DEVICE_ROW, map_capable=False, successful_install_count=0)], None)
        self.assertIsNone(stored_no["devices"][0]["evidenceStatus"])
        stored_unknown = _admin_device_payload([dict(DEVICE_ROW, map_capable=None, successful_install_count=0)], None)
        self.assertIsNone(stored_unknown["devices"][0]["evidenceStatus"])
        stored_yes = _admin_device_payload([dict(DEVICE_ROW, successful_install_count=0)], None)
        self.assertEqual(stored_yes["devices"][0]["evidenceStatus"], "TESTING")
        observed = _admin_device_payload([dict(DEVICE_ROW, map_capable=None, successful_install_count=1)], None)
        self.assertEqual(observed["devices"][0]["evidenceStatus"], "TESTED")


class DevicesPageTests(unittest.TestCase):
    def test_summary_tiles_replace_prose_and_developer_note(self):
        body = devices_page([DEVICE_ROW], None, {"username": "operator"}, "csrf").decode()
        self.assertNotIn("backend-derived", body)
        self.assertNotIn("models covered", body)
        for label in ("Models", "Maps: Yes", "Verified", "Covered", "Pending policy"):
            self.assertIsNotNone(metric_value(body, label), label)
        self.assertEqual(metric_value(body, "Models"), "1")

    def test_duplicate_sticky_header_is_hidden_from_assistive_technology(self):
        body = devices_page([DEVICE_ROW], None, {"username": "operator"}, "csrf").decode()
        sticky = body.split("id=\"device-sticky-header\"", 1)[1].split("</table>", 1)[0]
        self.assertIn('aria-hidden="true"', body.split("id=\"device-sticky-header\"", 1)[1][:40])
        self.assertIn('role="presentation"', sticky)
        self.assertNotIn("<caption", sticky)
        self.assertEqual(sticky.count('tabindex="-1"'), 8)
        # The real table keeps its caption and focusable sort buttons.
        real = body.split('class="table-wrap device-table-wrap"', 1)[1]
        self.assertIn("<caption class=\"sr-only\">Device catalog", real)


class InstallationsPageTests(unittest.TestCase):
    def test_tiles_have_no_scope_chips_and_positive_only_danger(self):
        rows = [{"model": "fēnix 8", "compatibility_identity": "fēnix 8", "attempted_install_count": 4,
                 "successful_install_count": 4, "failed_install_count": 0, "recognized_map_capable_evidence": True}]
        body = dashboard_page(rows, {"username": "operator"}, "csrf").decode()
        self.assertEqual(metric_value(body, "Failed"), "0")
        self.assertEqual(metric_tone(body, "Failed"), "neutral")
        kpis = body.split('class="admin-card installation-kpis"', 1)[1].split("</section>", 1)[0]
        self.assertNotIn("admin-scope-chip", kpis)  # owner decision 2026-10-06
        self.assertIn('>Evidence <span class="sort-indicator" aria-hidden="true" data-sort="none"></span>', body)

    def test_identity_review_filter_targets_rows_with_pending_identity(self):
        rows = [
            {"model": "Unassigned watch", "compatibility_identity": "Unassigned watch",
             "attempted_install_count": 1, "successful_install_count": 1, "failed_install_count": 0},
            {"model": "fēnix 8", "compatibility_identity": "fēnix 8", "attempted_install_count": 1,
             "successful_install_count": 1, "failed_install_count": 0},
        ]
        summary = {
            "identity:Unassigned watch": {"attempts": 1, "successful": 1, "failed": 0, "open_errors": 0, "identity_pending": 1},
            "identity:fēnix 8": {"attempts": 1, "successful": 1, "failed": 0, "open_errors": 0, "identity_pending": 0},
        }
        body = dashboard_page(rows, {"username": "operator"}, "csrf", diagnostic_summary=summary).decode()
        self.assertIn('data-installation-filter="identity-pending"', body)
        self.assertIn("data-identity-pending='1'", body)
        self.assertIn("data-identity-pending='0'", body)


class BlockedBeforeWritingTests(unittest.TestCase):
    PREWRITE = {
        "operation_key": "prewrite", "canonical_device_model_id": "garmin-fenix-8-47",
        "occurred_at": "2026-09-01T10:00:00Z", "phase_outcome": "FAILED", "write_started": False,
        "failure_stage": "preflight", "failure_code": "INSTALL_BLOCKED_INSUFFICIENT_SPACE",
    }

    def test_prewrite_result_is_blocked_not_failed(self):
        self.assertEqual(_operation_result([self.PREWRITE]), "NOT_STARTED")

    def test_history_shows_blocked_with_its_own_filter_and_keeps_open_review(self):
        device = _admin_device_payload([DEVICE_ROW], None)["devices"][0]
        body = device_detail_page(device, {"username": "operator"}, "csrf", operations=[self.PREWRITE],
                                  open_problem_count=1).decode()
        row = body.split("<tbody id='diagnostic-rows'>", 1)[1].split("</tr>", 1)[0]
        self.assertIn("data-diagnostic-result='not_started'", row)
        self.assertIn("<span>Blocked before writing</span>", row)
        # Pre-write storage blocks remain open problems that need review.
        self.assertIn("data-review-open='true'", row)
        self.assertIn("data-status='OPEN'", row)
        self.assertIn("data-history-filter='blocked'", body)
        self.assertIn("selected === 'blocked' && row.dataset.diagnosticResult === 'not_started'", body)
        self.assertIn("Installation blocked before writing", body)


class ModelHistoryLayoutTests(unittest.TestCase):
    """Desktop history: compact table rows at >=1024 px, cards below (review 2026-10-06)."""

    def test_history_rows_keep_columns_labels_filters_and_inspect(self):
        device = _admin_device_payload([DEVICE_ROW], None)["devices"][0]
        body = device_detail_page(device, {"username": "operator"}, "csrf",
                                  operations=[BlockedBeforeWritingTests.PREWRITE], open_problem_count=1).decode()
        table = body.split("<table class='diagnostic-list-table model-history-table mobile-record-table'>", 1)[1].split("</table>", 1)[0]
        headers = ["Date", "Map", "Result", "Error", "GitHub issue", "App version", "Action"]
        self.assertEqual([h for h in headers if f">{h}</th>" in table], headers)
        row = table.split("<tbody id='diagnostic-rows'>", 1)[1].split("</tr>", 1)[0]
        for label in headers:
            self.assertIn(f"data-label='{label}'", row)
        self.assertIn("class='secondary-button diagnostic-review'", row)
        self.assertIn("data-history-filter='failed'", body)

    def test_desktop_table_rule_and_tablet_card_rule_do_not_overlap(self):
        from terento_catalog.admin import ADMIN_STYLES
        desktop = ADMIN_STYLES.split("@media(min-width:1024px){\n  .model-evidence-grid", 1)[1].split("\n}", 1)[0]
        self.assertIn(".model-evidence-history .model-history-table{min-width:0;width:100%;table-layout:fixed}", desktop)
        self.assertIn(".model-evidence-grid{grid-template-columns:minmax(0,2fr) minmax(0,3fr)}", "  .model-evidence-grid" + desktop)
        # The GitHub issue column is shown only when a listed row has an issue.
        self.assertIn(":not(:has(td[data-label='GitHub issue'] a)) :is(th,td):nth-child(5){display:none}", desktop)
        self.assertNotIn("tbody tr{display:grid", desktop)
        self.assertIn("@media(min-width:901px) and (max-width:1023px){\n  .model-evidence-history .table-wrap:has(.mobile-record-table)", ADMIN_STYLES)
        self.assertNotIn("@media(min-width:901px){\n  .model-evidence-history", ADMIN_STYLES)


class PickerTemplateTests(unittest.TestCase):
    def test_model_detail_renders_the_catalog_picker_once_per_page(self):
        device = _admin_device_payload([DEVICE_ROW], None)["devices"][0]
        operations = [{
            "operation_key": f"op-{index}", "operation_id": f"op-{index}",
            "canonical_device_model_id": None, "identity_resolution_state": "UNRESOLVED",
            "occurred_at": f"2026-09-0{index + 1}T10:00:00Z", "phase_outcome": "SUCCEEDED",
            "automatic_finishing_result": "VERIFIED", "write_started": True,
        } for index in range(5)]
        for operation in operations:
            operation["canonical_device_model_id"] = device["id"]
        body = device_detail_page(device, {"username": "operator"}, "csrf", operations=operations,
                                  identity_devices=CATALOG).decode()
        self.assertEqual(body.count("<dialog class='diagnostic-detail-dialog'"), 5)
        self.assertEqual(body.count("<template id='identity-picker-catalog'>"), 1)
        self.assertEqual(body.count("data-identity-device-id='model-3'"), 1)
        self.assertIn("data-identity-catalog='page'", body)
        self.assertIn("dialog.dispatchEvent(new Event('terento-dialog-open'))", body)

    def test_direct_dialog_keeps_inline_options_for_other_callers(self):
        markup = _diagnostic_detail_dialog("Unknown", "op", [{"phase_outcome": "FAILED"}], resolved=False,
                                           csrf_token="csrf", identity_devices=CATALOG)
        self.assertIn("data-identity-device-id='model-3'", markup)
        self.assertNotIn("data-identity-catalog='page'", markup)


if __name__ == "__main__":
    unittest.main()
