"""New catalog models get Maps only from official Garmin specifications (owner rule 2026-10-06)."""
import json
import unittest
from datetime import datetime, timezone

from pglite_support import PGliteTestCase
from terento_catalog.admin import overview_page
from terento_catalog.collectors.garmin.specifications import map_capability_from_rows, parse_specifications
from terento_catalog.device_catalog import build_device_catalog
from terento_catalog.installation_policy import build_installation_policy
from terento_catalog.models import CollectedDevice


def page(*skus):
    return "var GarminAppBootstrap = " + json.dumps({"skus": {str(i): sku for i, sku in enumerate(skus)}}) + ";"


def sku(rows, product="123", part="010-12345-00"):
    """A product SKU whose specsTab mirrors Garmin's table markup (yes/no cells carry a class)."""
    cells = []
    for label, value in rows:
        if value in {"yes", "no"}:
            cells.append(f"<tr><th>{label}</th><td class='{value}'></td></tr>")
        else:
            cells.append(f"<tr><th>{label}</th><td>{value}</td></tr>")
    content = ("<h3>MAPS &amp; MEMORY</h3><table><tr><th>Maps &amp; memory</th></tr>" + "".join(cells) + "</table>")
    return {"productId": product, "partNumber": part, "tabs": {"specsTab": {"content": content}}}


class SpecificationParserTests(unittest.TestCase):
    def test_maps_yes_from_preloaded_or_add_maps_rows(self):
        result = parse_specifications(page(sku([("Display type", "AMOLED"), ("Preloaded maps", "yes"),
                                                ("Ability to add maps", "yes"), ("Storage", "32 GB")])), "123")
        self.assertIs(result["map_capable"], True)
        self.assertEqual(result["map_evidence_row"], "ability to add maps")
        topo = parse_specifications(page(sku([("TopoActive maps", "yes (Europe)")])), "123")
        self.assertIs(topo["map_capable"], True)
        self.assertEqual(topo["map_evidence_row"], "topoactive maps")

    def test_live_garmin_row_labels(self):
        """Row labels as they appear on live Garmin pages (checked 2026-10-06)."""
        map_watch = parse_specifications(page(sku([
            ("Display type", "AMOLED"), ("Built-in mapping", "yes"), ("Full vector map", "yes"),
            ("Preloaded road and trail maps", "yes (Sapphire Editions only)"),
            ("On-screen workout muscle maps", "yes"), ("Course guidance", "yes")])), "123")
        self.assertIs(map_watch["map_capable"], True)
        self.assertEqual(map_watch["map_evidence_row"], "built-in mapping")
        # Watches without maps omit the mapping rows; muscle maps and courses are not map support.
        no_rows = parse_specifications(page(sku([
            ("Display type", "AMOLED"), ("On-screen workout muscle maps", "yes"),
            ("Course guidance", "yes"), ("Point-to-point navigation", "yes")])), "123")
        self.assertIsNone(no_rows["map_capable"])
        self.assertIsNone(no_rows["map_evidence_row"])
        self.assertEqual(map_capability_from_rows({"built-in mapping": "no"}), (False, "built-in mapping"))

    def test_explicit_no_only_from_a_whole_map_support_row(self):
        result = parse_specifications(page(sku([("Display type", "AMOLED"), ("Ability to add maps", "no"),
                                                ("Preloaded maps", "no")])), "123")
        self.assertIs(result["map_capable"], False)
        self.assertEqual(result["map_evidence_row"], "ability to add maps")
        # No preloaded maps alone does not prove the watch cannot take added maps.
        self.assertIsNone(parse_specifications(page(sku([("Preloaded maps", "no")])), "123")["map_capable"])

    def test_missing_or_conflicting_map_information_is_unknown(self):
        missing = parse_specifications(page(sku([("Display type", "AMOLED"), ("Solar charging", "yes")])), "123")
        self.assertIsNone(missing["map_capable"])
        self.assertIsNone(missing["map_evidence_row"])
        self.assertIs(missing["solar"], True)
        conflicting = parse_specifications(page(sku([("Ability to add maps", "no"), ("Preloaded maps", "yes")])), "123")
        self.assertIsNone(conflicting["map_capable"])
        variants = parse_specifications(page(sku([("Ability to add maps", "yes")]),
                                             sku([("Ability to add maps", "no")], part="010-12345-01")), "123")
        self.assertIsNone(variants["map_capable"])
        self.assertEqual(map_capability_from_rows({}), (None, None))
        self.assertEqual(map_capability_from_rows({"maps": "none listed"}), (None, None))

    def test_other_product_on_the_page_is_not_evidence(self):
        result = parse_specifications(page(sku([("Ability to add maps", "yes")], product="456")), "123")
        self.assertIsNone(result["map_capable"])


def record(device_id, model, map_capable=None, field=None):
    return CollectedDevice(
        id=device_id, family_id="garmin-venu", family_name="Venu", manufacturer="Garmin",
        model=model, canonical_model=model, variant="", case_size_mm=None, display_type=None,
        part_number=None, product_url=f"https://www.garmin.com/en-US/p/{abs(hash(device_id)) % 10**6}/",
        source_url="https://www.garmin.com/en-US/c/wearables-smartwatches/",
        map_capable=map_capable, map_evidence_row=field,
    )


class CollectorInsertTests(PGliteTestCase):
    def maps(self, *ids):
        rows = self.sql("SELECT id, map_capable, specification_evidence FROM device_model WHERE id = ANY(%s)", (list(ids),))
        return {row["id"]: row for row in rows}

    def test_new_rows_take_maps_from_specs_and_never_from_the_name(self):
        self.db.upsert_collected_devices([
            # A future maps-capable watch in a "known non-map" family: no spec info → Unknown.
            record("garmin-venu-x2", "Venu X2"),
            record("garmin-venu-x2-spec", "Venu X2 Pro", True, "ability to add maps"),
            record("garmin-instinct-9", "Instinct 9", False, "ability to add maps"),
            # A name the old prefix list called supported is still Unknown without specs.
            record("garmin-fenix-10", "fēnix 10"),
        ], collection_complete=False)
        rows = self.maps("garmin-venu-x2", "garmin-venu-x2-spec", "garmin-instinct-9", "garmin-fenix-10")
        self.assertIsNone(rows["garmin-venu-x2"]["map_capable"])
        self.assertIs(rows["garmin-venu-x2-spec"]["map_capable"], True)
        self.assertIs(rows["garmin-instinct-9"]["map_capable"], False)
        self.assertIsNone(rows["garmin-fenix-10"]["map_capable"])
        evidence = rows["garmin-venu-x2-spec"]["specification_evidence"]
        self.assertEqual(evidence["map_capable"]["value"], True)
        self.assertEqual(evidence["map_capable"]["field"], "ability to add maps")
        self.assertEqual(evidence["map_capable"]["version"], "official-product-specifications")
        self.assertTrue(evidence["map_capable"]["source"].startswith("https://www.garmin.com/en-US/p/"))
        self.assertNotIn("map_capable", rows["garmin-venu-x2"]["specification_evidence"] or {})
        self.assertGreaterEqual(self.db.maps_unknown_model_count(), 2)

    def test_existing_stored_values_are_never_changed_and_unknown_can_be_filled(self):
        self.db.upsert_collected_devices([record("garmin-venu-x2", "Venu X2"), record("garmin-venu-4", "Venu 4")],
                                         collection_complete=False)
        self.sql("UPDATE device_model SET map_capable = false WHERE id = 'garmin-venu-4'")
        result = self.db.upsert_collected_devices([
            record("garmin-venu-x2", "Venu X2", True, "preloaded maps"),
            record("garmin-venu-4", "Venu 4", True, "ability to add maps"),
        ], collection_complete=False)
        rows = self.maps("garmin-venu-x2", "garmin-venu-4")
        self.assertIs(rows["garmin-venu-x2"]["map_capable"], True)  # Unknown filled from specs
        self.assertIs(rows["garmin-venu-4"]["map_capable"], False)  # reviewed value kept
        self.assertIn("garmin-venu-x2", result["updated_ids"])
        # A later run without spec information keeps every stored value.
        self.db.upsert_collected_devices([record("garmin-venu-x2", "Venu X2"), record("garmin-venu-4", "Venu 4")],
                                         collection_complete=False)
        rows = self.maps("garmin-venu-x2", "garmin-venu-4")
        self.assertEqual((rows["garmin-venu-x2"]["map_capable"], rows["garmin-venu-4"]["map_capable"]), (True, False))

    def test_unknown_row_is_null_in_public_catalog_and_pending_in_policy(self):
        self.db.upsert_collected_devices([record("garmin-venu-x2", "Venu X2")], collection_complete=False)
        rows, timestamp = self.db.device_catalog_snapshot()
        device = next(item for item in build_device_catalog(rows, timestamp)["devices"] if item["id"] == "garmin-venu-x2")
        self.assertIsNone(device["mapCapable"])
        policy_rows, policy_timestamp = self.db.installation_policy_snapshot()
        policy = build_installation_policy(policy_rows, policy_timestamp)
        entry = next(item for item in policy["devices"] if item["id"] == "garmin-venu-x2")
        self.assertIsNone(entry["mapCapable"])
        self.assertEqual(entry["installationAuthorization"], "PENDING")


class MapsUnknownAttentionTests(unittest.TestCase):
    def attention(self, **overview):
        body = overview_page({"period": "24h", "data": {}, "providers": [], **overview},
                             {"username": "operator", "admin_review_summary": {"available": True}}, "csrf").decode()
        return body.split("id='overview-attention-title'", 1)[1].split("</section>", 1)[0]

    def test_row_count_link_and_unavailable_state(self):
        attention = self.attention(mapsUnknown={"modelCount": 5})
        self.assertIn("aria-label='Maps unknown: 5'", attention)
        self.assertIn("href='/admin/devices?maps=unknown&amp;active=1'", attention)
        self.assertIn("aria-label='Maps unknown: unavailable'", self.attention(mapsUnknown={"available": False}))
        self.assertIn("aria-label='Maps unknown: unavailable'", self.attention())


if __name__ == "__main__":
    unittest.main()
