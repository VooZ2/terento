from __future__ import annotations

import unittest

from terento_catalog.admin import campaign_links_page
from terento_catalog.campaign_links import build_campaign_url, normalize_value


class CampaignLinkContractTests(unittest.TestCase):
    def test_normalization_keeps_valid_separators_and_removes_punctuation(self):
        self.assertEqual(normalize_value(" Garmin Forum-DE! "), "garmin_forum-de")
        self.assertEqual(normalize_value("Paid__social"), "paid_social")
        self.assertEqual(normalize_value("  "), "")

    def test_reddit_preset_shape_is_canonical(self):
        self.assertEqual(
            build_campaign_url(
                destination="home",
                source="reddit",
                medium="social",
                campaign="early_beta",
            ),
            "https://terento.app/?utm_source=reddit&utm_medium=social&utm_campaign=early_beta",
        )

    def test_optional_values_are_omitted(self):
        url = build_campaign_url(
            destination="compatibility",
            source="github",
            medium="community",
            campaign="early_beta",
            content="",
            term="",
        )
        self.assertNotIn("utm_content", url)
        self.assertNotIn("utm_term", url)

    def test_existing_query_is_preserved_and_utms_are_replaced(self):
        url = build_campaign_url(
            destination="other",
            custom_destination="https://terento.app/download/?ref=reddit&utm_source=old&utm_term=old#top",
            source="reddit",
            medium="social",
            campaign="early_beta",
            content="garminwatches",
        )
        self.assertEqual(
            url,
            "https://terento.app/download/?ref=reddit&utm_source=reddit&utm_medium=social&utm_campaign=early_beta&utm_content=garminwatches#top",
        )

    def test_custom_values_and_destination_are_restricted(self):
        self.assertEqual(
            build_campaign_url(
                destination="other",
                custom_destination="/community/",
                source="other",
                custom_source="forum",
                medium="other",
                custom_medium="community",
                campaign="launch",
            ),
            "https://terento.app/community/?utm_source=forum&utm_medium=community&utm_campaign=launch",
        )
        with self.assertRaises(ValueError):
            build_campaign_url(
                destination="other",
                custom_destination="https://example.com/",
                source="reddit",
                medium="social",
                campaign="launch",
            )

    def test_page_contains_builder_contract_and_accessible_help(self):
        body = campaign_links_page({"username": "operator"}, "csrf").decode()
        for text in (
            "Campaign links",
            "Create consistent tracking links for Terento campaigns.",
            "Campaign link builder",
            "Reddit community post",
            "Home",
            "Download",
            "Compatibility",
            "Custom Terento URL or path",
            "Copy link",
            "Umami attribution preview",
            "aria-controls='destination-info'",
            "aria-controls='campaign-info'",
            "window.TerentoCampaignLinkBuilder",
        ):
            self.assertIn(text, body)
        self.assertIn("grid-template-columns:repeat(2", body)
        self.assertIn('class="filter-bar admin-filter-bar campaign-preset-row"', body)
        self.assertIn(".campaign-preset-row{display:flex", body)
        self.assertIn("height:var(--admin-control-height)", body)
        self.assertIn(".campaign-field input,.campaign-field select,.campaign-preset-row select{height:var(--admin-control-height)", body)
        self.assertIn('font-family:"Inter"', body)
        self.assertIn("box-sizing:border-box", body)
        self.assertIn(".campaign-preset-row .campaign-label,.campaign-preset-row select{flex:none}", body)
        self.assertNotIn(">Generate<", body)


if __name__ == "__main__":
    unittest.main()
