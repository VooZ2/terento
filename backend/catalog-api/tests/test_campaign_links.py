from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from html.parser import HTMLParser

from terento_catalog.admin import ADMIN_STYLES, _campaign_links_script, campaign_links_page
from terento_catalog.campaign_links import (
    CAMPAIGN_SUGGESTIONS,
    CHANNELS,
    DESTINATION_OPTIONS,
    DESTINATIONS,
    MAX_VALUE_LENGTH,
    MEDIUM_OPTIONS,
    SOURCE_OPTIONS,
    build_campaign_url,
    channel_source_medium,
    normalize_value,
)


class CampaignLinkContractTests(unittest.TestCase):
    def test_normalization_keeps_valid_separators_and_removes_punctuation(self):
        self.assertEqual(normalize_value(" Garmin Forum-DE! "), "garmin_forum-de")
        self.assertEqual(normalize_value("Paid__social"), "paid_social")
        self.assertEqual(normalize_value("  "), "")

    def test_channels_map_to_one_fixed_source_and_medium(self):
        expected = {
            "reddit": ("Reddit post", "reddit", "community"),
            "garmin_forum": ("Garmin forum", "garmin_forum", "community"),
            "github": ("GitHub", "github", "referral"),
            "discord": ("Discord", "discord", "community"),
            "facebook": ("Facebook group", "facebook", "social"),
            "x": ("X post", "x", "social"),
            "email": ("Email", "email", "email"),
        }
        fixed = {channel.key: (channel.label, channel.source, channel.medium) for channel in CHANNELS if channel.key != "other"}
        self.assertEqual(fixed, expected)
        self.assertEqual(CHANNELS[-1].key, "other")
        self.assertEqual(CHANNELS[0].key, "reddit", "Reddit post is the default channel")
        sources = {value for value, _ in SOURCE_OPTIONS}
        mediums = {value for value, _ in MEDIUM_OPTIONS}
        for channel in CHANNELS:
            with self.subTest(channel=channel.key):
                self.assertTrue(channel.content_hint)
                if channel.key == "other":
                    continue
                # The fixed values are part of the shared vocabulary and already canonical.
                self.assertIn(channel.source, sources)
                self.assertIn(channel.medium, mediums)
                self.assertEqual(normalize_value(channel.source), channel.source)
                # Fixed channels ignore custom input so one place is always counted the same way.
                self.assertEqual(
                    channel_source_medium(channel.key, custom_source="ignored", medium="other", custom_medium="ignored"),
                    (channel.source, channel.medium),
                )

    def test_option_tuples_are_extended_additively(self):
        sources = [value for value, _ in SOURCE_OPTIONS]
        for value in ("reddit", "github", "discord", "facebook", "x", "linkedin", "email", "other", "garmin_forum"):
            self.assertIn(value, sources)
        self.assertEqual(
            [value for value, _ in MEDIUM_OPTIONS],
            ["social", "community", "email", "referral", "paid_social", "other"],
        )
        self.assertEqual(CAMPAIGN_SUGGESTIONS, ("early_beta", "launch", "compatibility", "community"))
        self.assertEqual([key for key, _ in DESTINATION_OPTIONS], list(DESTINATIONS))

    def test_other_channel_uses_custom_source_and_medium_choice(self):
        self.assertEqual(channel_source_medium("other", custom_source=" LinkedIn ", medium="social"), ("linkedin", "social"))
        self.assertEqual(
            channel_source_medium("other", custom_source="forum", medium="other", custom_medium="Partner Site"),
            ("forum", "partner_site"),
        )
        self.assertEqual(channel_source_medium("other", medium="social"), ("", "social"))
        with self.assertRaises(ValueError):
            channel_source_medium("myspace")
        with self.assertRaises(ValueError):
            build_campaign_url(destination="home", channel="other", medium="social", campaign="launch")

    def test_reddit_channel_shape_is_canonical(self):
        self.assertEqual(
            build_campaign_url(destination="home", channel="reddit", campaign="early_beta"),
            "https://terento.app/?utm_source=reddit&utm_medium=community&utm_campaign=early_beta",
        )
        self.assertEqual(
            build_campaign_url(destination="download", channel="garmin_forum", campaign="Winter Update!", content="fenix 8 thread"),
            "https://terento.app/download/?utm_source=garmin_forum&utm_medium=community&utm_campaign=winter_update&utm_content=fenix_8_thread",
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
        for destination in ("https://example.com/", "http://terento.app/", "https://terento.app:8443/", "https://user@terento.app/"):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                build_campaign_url(destination="other", custom_destination=destination, channel="reddit", campaign="launch")

    def test_values_longer_than_the_site_accepts_are_rejected(self):
        # site/privacy-consent.js forwards at most 80 characters per UTM value to Umami.
        self.assertEqual(MAX_VALUE_LENGTH, 80)
        build_campaign_url(destination="home", channel="reddit", campaign="a" * 80)
        with self.assertRaises(ValueError):
            build_campaign_url(destination="home", channel="reddit", campaign="a" * 81)
        with self.assertRaises(ValueError):
            build_campaign_url(destination="home", channel="reddit", campaign="launch", content="b" * 81)


class _Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def find(self, **wanted):
        return [attrs for tag, attrs in self.elements if all(attrs.get(key) == value for key, value in wanted.items())]


class CampaignLinkPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = campaign_links_page({"username": "operator"}, "csrf").decode()
        cls.main = cls.body.split("</head>", 1)[1]
        cls.markup = _Markup()
        cls.markup.feed(cls.main)

    def test_page_is_one_card_with_short_hints_and_no_popovers(self):
        main = self.main
        for text in (
            "<h1>Campaign links</h1>",
            "Campaign link builder",
            "Built in this browser. Nothing is saved.",
            "When to use campaign links",
            "Use one whenever you post a terento.app link outside the site.",
            "Pick the channel where you post it",
            "Use the same campaign name for every post in one effort.",
            "Where will you share this link?",
            "Where exactly <span class='campaign-optional'>(optional)</span>",
            "Subreddit or thread, e.g. r_garmin",
            "More options",
            "Rarely needed: only for paid search keywords.",
            "Copy link",
            "Umami will show:",
            "window.TerentoCampaignLinkBuilder",
        ):
            self.assertIn(text, main)
        self.assertEqual(main.count("class='admin-card campaign-card'"), 1)
        for removed in (
            "info-control", "info-popover", "Umami attribution preview", "preview-grid",
            "required-label", "Preset", "campaign-preset", "Generated URL", ">Generate<",
        ):
            self.assertNotIn(removed, main)
        self.assertGreaterEqual(main.count("class='campaign-hint'"), 8)

    def test_choices_are_quick_filter_buttons_from_the_contract(self):
        groups = {
            "campaign-channel": ([channel.key for channel in CHANNELS], "reddit"),
            "campaign-destination": (["home", "download", "compatibility", "other"], "home"),
            "campaign-name-choice": ([*CAMPAIGN_SUGGESTIONS, "custom"], "early_beta"),
            "campaign-medium": ([value for value, _ in MEDIUM_OPTIONS], "referral"),
        }
        elements = self.markup.elements
        for select_id, (values, selected) in groups.items():
            with self.subTest(group=select_id):
                start = next(i for i, (tag, attrs) in enumerate(elements) if attrs.get("data-quick-select") == select_id)
                self.assertEqual(elements[start][1].get("role"), "group")
                self.assertIn(elements[start - 1][1].get("class"), {"filter-bar admin-filter-bar campaign-choice"})
                buttons = [attrs for tag, attrs in elements[start + 1:start + 1 + len(values)] if tag == "button"]
                self.assertEqual([button["data-quick-value"] for button in buttons], values)
                self.assertTrue(all(button["type"] == "button" for button in buttons))
                self.assertEqual([button["aria-pressed"] for button in buttons], ["true" if value == selected else "false" for value in values])
        for label in ("Reddit post", "Garmin forum", "Facebook group", "X post", "Other page…", "Custom…", "Early beta", "Other…"):
            self.assertIn(f">{label}</button>", self.main)

    def test_free_text_fields_are_revealed_only_for_their_choice(self):
        for wrapper in ("campaign-other-fields", "campaign-medium-custom-wrap", "campaign-destination-fields", "campaign-name-fields"):
            with self.subTest(wrapper=wrapper):
                (attrs,) = self.markup.find(id=wrapper)
                self.assertIn("hidden", attrs)
        for input_id in ("campaign-source", "campaign-medium-custom", "campaign-name-custom", "campaign-content", "campaign-term"):
            with self.subTest(input=input_id):
                (attrs,) = self.markup.find(id=input_id)
                self.assertEqual(attrs["maxlength"], str(MAX_VALUE_LENGTH))
                self.assertTrue(attrs["aria-describedby"])
                self.assertTrue(self.markup.find(**{"for": input_id}), "input has a visible label")
        (term_disclosure,) = self.markup.find(id="campaign-more")
        self.assertNotIn("open", term_disclosure)

    def test_result_is_a_read_only_link_with_copy_and_inline_summary(self):
        (output,) = self.markup.find(id="generated-url")
        self.assertIn("readonly", output)
        self.assertTrue(self.markup.find(**{"for": "generated-url"}))
        self.assertIn(
            ">https://terento.app/?utm_source=reddit&amp;utm_medium=community&amp;utm_campaign=early_beta</textarea>",
            self.main,
        )
        (copy,) = self.markup.find(id="copy-link")
        self.assertEqual(copy["class"], "copy-button")
        self.assertIn(
            "source <strong>reddit</strong> · medium <strong>community</strong> · campaign <strong>early_beta</strong>",
            self.main,
        )
        (message,) = self.markup.find(id="campaign-message")
        self.assertEqual(message["role"], "status")
        for state, icon in (("incomplete", "circle-exclamation"), ("copied", "circle-check"), ("failed", "x-circle")):
            self.assertIn(f"data-icon='{state}'><svg class='admin-icon admin-icon-{icon}'", self.main)

    def test_styles_use_admin_controls_and_mono_only_for_the_url(self):
        body = ADMIN_STYLES
        self.assertIn(".campaign-form input[type='text'],.campaign-url{width:100%;max-width:480px;height:var(--admin-control-height)", body)
        self.assertIn("font-family:var(--font-mono);font-size:13px", body)
        self.assertIn(".campaign-url-row .campaign-url::placeholder{font-family:var(--font-ui)}", body)
        self.assertIn(".campaign-card .campaign-choice .quick-filter-group{flex-wrap:wrap;overflow:visible}", body)
        campaign_rules = "\n".join(line for line in body.split("\n") if line.lstrip().startswith((".campaign-", ".copy-button")))
        self.assertEqual(campaign_rules.count("--font-mono"), 1)
        self.assertNotIn("#", campaign_rules.replace("#top", ""), "no raw colours")
        self.assertIn(".copy-button,.model-administration", body)  # Interactive Primary button family

    def test_script_embeds_the_contract_constants(self):
        script = _campaign_links_script()
        marker = "const config = "
        config = json.loads(script[script.index(marker) + len(marker):script.index(";\n", script.index(marker))])
        self.assertEqual(config["destinations"], DESTINATIONS)
        self.assertEqual(
            config["channels"],
            {channel.key: {"source": channel.source, "medium": channel.medium, "contentHint": channel.content_hint} for channel in CHANNELS},
        )
        self.assertEqual(config["maxLength"], MAX_VALUE_LENGTH)
        for key in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"):
            self.assertIn(f"'{key}'", script)

    def test_browser_normalization_and_url_match_the_python_contract(self):
        node = os.environ.get("TERENTO_NODE_BIN", "").strip() or shutil.which("node") or shutil.which("nodejs")
        if not node or not Path(node).exists():
            self.skipTest("Node.js is not available")
        samples = [" Garmin Forum-DE! ", "Paid__social", "Ēarly  Beta", "r/garmin", "--a--b__", "ﬁnal", "x"]
        script = _campaign_links_script()
        start = script.index("const normalizeValue")
        end = script.index("const destinationUrl")
        program = script[start:end] + f"console.log(JSON.stringify({json.dumps(samples)}.map(normalizeValue)));"
        result = subprocess.run([node, "-e", program], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), [normalize_value(sample) for sample in samples])


if __name__ == "__main__":
    unittest.main()
