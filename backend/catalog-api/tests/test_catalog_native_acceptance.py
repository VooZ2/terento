"""Release gate: every published catalog package must pass released-client acceptance.

Released native clients reject the whole catalog when one package fails
``MapCatalogLoader.isCompatible``. These tests build catalog v4 from the real
database read model and run the Python mirror in ``native_catalog_acceptance``.
"""
import json
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from native_catalog_acceptance import catalog_rejections
from pglite_support import PGliteTestCase
from terento_catalog import provider_rechecks
from terento_catalog.http_api import CatalogService

FIXTURE = json.loads((Path(__file__).parent / "fixtures/bbbike/representative-catalog.json").read_text())
BBBIKE_MAPS = FIXTURE["providers"][0]["maps"]


class MirrorSanityTests(unittest.TestCase):
    def test_representative_bbbike_catalog_is_accepted(self):
        self.assertEqual(catalog_rejections(FIXTURE), [])

    def test_unavailable_bbbike_with_retained_proof_is_rejected(self):
        catalog = deepcopy(FIXTURE)
        artifact = catalog["providers"][0]["maps"][0]["artifacts"][0]
        artifact.update(validationStatus="UNAVAILABLE", validationState="unavailable")
        self.assertTrue(any("must not carry sourceProof" in reason for reason in catalog_rejections(catalog)))
        artifact.pop("sourceProof")
        self.assertEqual(catalog_rejections(catalog), [])


class PublishedCatalogGateTests(PGliteTestCase):
    def setUp(self):
        super().setUp()
        self.sql("UPDATE map_provider SET status='ACTIVE' WHERE id IN ('bbbike','freizeitkarte')")
        for package in BBBIKE_MAPS[:2]:
            self.insert_bbbike(package)
        self.sql("""INSERT INTO map_package (id, provider_id, provider_region_id, canonical_region_id, name, region,
                        release, country, source_updated_at)
                    VALUES ('freizeitkarte-deu', 'freizeitkarte', 'DEU', 'DEU', 'Germany', 'DEU', '2026-09', 'DE',
                            '2026-09-01T00:00:00Z')""")
        self.sql("""INSERT INTO map_artifact (id, package_id, kind, source_url, size_bytes, install_size_bytes,
                        validation_status)
                    VALUES ('freizeitkarte-deu-main', 'freizeitkarte-deu', 'main',
                            'https://download.freizeitkarte-osm.de/garmin/latest/Freizeitkarte_DEU.Android.zip',
                            1000, 2000, 'VALIDATED')""")

    def insert_bbbike(self, package):
        artifact = package["artifacts"][0]
        self.sql(
            """INSERT INTO map_package (id, provider_id, provider_region_id, canonical_region_id, name, region,
                   release, country, map_type, geographic_region_id, country_codes, region_kind,
                   release_id, version_label, generated_at, source_updated_at)
               VALUES (%s, 'bbbike', %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)""",
            (package["id"], package["providerRegionId"], package["canonicalRegionId"], package["name"],
             package["region"], package["release"], package["country"], package["mapType"],
             package["geographicRegionId"], json.dumps(package["countryCodes"]), package["regionKind"],
             package["releaseMetadata"]["releaseId"], package["releaseMetadata"]["versionLabel"],
             package["releaseMetadata"]["generatedAt"], package["releaseMetadata"]["sourceUpdatedAt"]),
        )
        proof = artifact["sourceProof"]
        self.sql(
            """INSERT INTO map_artifact (id, package_id, kind, source_url, size_bytes, install_size_bytes,
                   validation_status, install_payload_path, source_updated_at, source_proof, content_type)
               VALUES (%s, %s, 'main', %s, %s, %s, 'VALIDATED', %s, %s, %s::jsonb, 'application/zip')""",
            (artifact["id"], package["id"], artifact["sourceURL"], artifact["downloadSizeBytes"],
             artifact["installSizeBytes"], proof["payloadPath"], proof["generatedAt"], json.dumps(proof)),
        )

    def catalog(self):
        return json.loads(CatalogService(self.db).catalog_v4_response()[0])

    def bbbike_package(self, catalog, package_id):
        provider = next(item for item in catalog["providers"] if item["id"] == "bbbike")
        return next(item for item in provider["maps"] if item["id"] == package_id)

    def test_validated_catalog_passes_every_package(self):
        catalog = self.catalog()
        self.assertEqual(sum(len(p["maps"]) for p in catalog["providers"]), 3)
        self.assertEqual(catalog_rejections(catalog), [])

    def test_failed_bbbike_recheck_is_published_without_proof(self):
        failed_id = BBBIKE_MAPS[0]["id"]
        provider_rechecks.enqueue(self.db, "bbbike", failed_id, None)
        error = HTTPError(BBBIKE_MAPS[0]["sourceURL"], 503, "unavailable", {}, None)
        with patch.object(provider_rechecks, "inspect_artifact", side_effect=error):
            provider_rechecks.process_one(self.db)
        stored = self.sql("SELECT validation_status, source_proof FROM map_artifact WHERE package_id=%s", (failed_id,))[0]
        self.assertEqual(stored["validation_status"], "UNAVAILABLE")
        self.assertIsNotNone(stored["source_proof"], "stored evidence must not be deleted")

        catalog = self.catalog()
        package = self.bbbike_package(catalog, failed_id)
        # App rule: an unavailable BBBike main artifact is exactly one artifact without proof.
        self.assertEqual(len(package["artifacts"]), 1)
        main = package["artifacts"][0]
        self.assertEqual(main["validationState"], "unavailable")
        for key in ("sourceProof", "sourceUpdatedAt", "installPayloadPath"):
            self.assertNotIn(key, main)
        self.assertEqual(catalog_rejections(catalog), [])
        healthy = self.bbbike_package(catalog, BBBIKE_MAPS[1]["id"])
        self.assertIn("sourceProof", healthy["artifacts"][0])


if __name__ == "__main__":
    unittest.main()
