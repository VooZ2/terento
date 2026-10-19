"""Migration 086 reviews only undecided model source links and drops duplicates."""
import unittest

from pglite_support import PGliteTestCase

from terento_catalog.db import migration_directory
from terento_catalog.migrate import _statements

MIGRATION = migration_directory() / "086_model_source_review.sql"
SOURCE = "https://example.org/source"


class ModelSourceReviewTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        for device_id, model in (("garmin-fenix-8-47-solar", "fēnix 8"), ("garmin-fenix-8-47-amoled", "fēnix 8"),
                                 ("garmin-fenix-8-51-amoled", "fēnix 8"), ("garmin-forerunner-965", "Forerunner 965"),
                                 ("garmin-fenix-7-47", "fēnix 7"), ("garmin-enduro-4", "Enduro 4")):
            self.sql(
                """INSERT INTO device_model (id, family_id, manufacturer, model, canonical_model, variant,
                       product_url, source_url) VALUES (%s, 'garmin-fenix', 'Garmin', %s, %s, '', %s, %s)
                   ON CONFLICT (id) DO NOTHING""",
                (device_id, model, model.lower(), SOURCE, SOURCE),
            )
        self.sql("DELETE FROM device_identity_mapping_audit")
        self.sql("DELETE FROM device_identity_mapping")

    def link(self, kind, value, device_id, status="PENDING", version="1"):
        return self.sql(
            """INSERT INTO device_identity_mapping (kind, value, device_model_id, source_url, source_version, status)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (kind, value, device_id, SOURCE, version, status),
        )[0]["id"]

    def migrate(self):
        for statement in _statements(MIGRATION.read_text(encoding="utf-8")):
            self.sql(statement)

    def links(self, value):
        return {(row["device_model_id"], row["status"]) for row in self.sql(
            "SELECT device_model_id, status FROM device_identity_mapping WHERE value = %s", (value,))}

    def test_undecided_links_are_reviewed_with_an_audit_and_decisions_stay(self):
        wrong = self.link("XML_PART_NUMBER", "006-B4536-00", "garmin-fenix-8-47-solar")
        self.link("XML_PART_NUMBER", "006-B4533-00", "garmin-fenix-8-51-amoled", status="APPROVED")
        self.link("XML_PART_NUMBER", "006-B4315-00", "garmin-forerunner-965")
        self.link("USB", "091e:4f43", "garmin-fenix-7-47")
        self.migrate()
        self.assertIn(("garmin-fenix-8-47-solar", "REJECTED"), self.links("006-B4536-00"))
        # An administrator's decision is never overwritten.
        self.assertIn(("garmin-fenix-8-51-amoled", "APPROVED"), self.links("006-B4533-00"))
        self.assertEqual(self.links("006-B4315-00"), {("garmin-forerunner-965", "APPROVED")})
        self.assertIn(("garmin-fenix-7-47", "REJECTED"), self.links("091e:4f43"))
        audit = self.sql("SELECT previous_status, new_status, reviewed_by, reason FROM device_identity_mapping_audit"
                         " WHERE mapping_id = %s", (wrong,))
        self.assertEqual([(a["previous_status"], a["new_status"], a["reviewed_by"]) for a in audit],
                         [("PENDING", "REJECTED", None)])
        self.assertTrue(audit[0]["reason"].startswith("Migration 086:"))

    def test_missing_named_links_are_added_approved_only_for_existing_models(self):
        self.migrate()
        self.assertEqual(self.links("006-B5169-00"), {("garmin-enduro-4", "APPROVED")})
        # Seed rows for catalog models this database lacks (Enduro 3) add nothing.
        self.assertEqual(self.links("006-B4575-00"), set())

    def test_undecided_duplicates_of_a_link_are_removed(self):
        kept = self.link("RETAIL_SKU", "010-99999-00", "garmin-fenix-7-47", status="APPROVED", version="1")
        self.link("RETAIL_SKU", "010-99999-00", "garmin-fenix-7-47", version="2")
        oldest = self.link("RETAIL_SKU", "010-88888-00", "garmin-fenix-7-47", version="1")
        self.link("RETAIL_SKU", "010-88888-00", "garmin-fenix-7-47", version="2")
        single = self.link("RETAIL_SKU", "010-77777-00", "garmin-fenix-7-47", version="1")
        self.migrate()
        remaining = {row["id"] for row in self.sql(
            "SELECT id FROM device_identity_mapping WHERE kind = 'RETAIL_SKU'")}
        self.assertEqual(remaining, {kept, oldest, single})

    def test_a_changed_product_page_adds_no_second_retail_link(self):
        with self.db.connection() as connection:
            for version in ("1", "2"):
                self.db.enrich_device_specifications(connection, "garmin-fenix-7-47", {}, SOURCE, version,
                                                     skus=["010-99999-00"])
        self.assertEqual(len(self.sql("SELECT id FROM device_identity_mapping WHERE value = '010-99999-00'")), 1)


if __name__ == "__main__":
    unittest.main()
