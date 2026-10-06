"""Map style preview pipeline: areas, package choice, acquisition, releases."""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import zipfile
from datetime import datetime, time as day_time, timedelta, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

from jsonschema import Draft202012Validator

from terento_catalog.asset_storage import AssetStorage
from terento_catalog.http_api import CatalogService, make_handler
from terento_catalog.map_preview import acquire, areas as areas_module, job as job_module
from terento_catalog.map_preview.acquire import AcquisitionError, Limits
from terento_catalog.map_preview.areas import PreviewArea, load_areas, parse_areas, tile_count, tile_range
from terento_catalog.map_preview.job import (
    PreviewRun, PreviewSettings, next_window, parse_window, plan_work,
)
from terento_catalog.map_preview.manifest import build_manifest
from terento_catalog.map_preview.publish import PreviewStore
from terento_catalog.map_preview.render import MapInfo, RenderError, RenderResult, Renderer
from terento_catalog.map_preview.styles import STYLE_BY_ID, candidates_for, package_country_codes, packages_from_snapshot

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "contracts"
FIXTURE_IMG = ROOT / "backend/catalog-api/renderer/tests/fixture/synthetic-gmapsupp.img"
WEBP = b"RIFF\x1a\x00\x00\x00WEBPVP8L\x0d\x00\x00\x00/\x00\x00\x00\x10\x07\x10\x11\x11\x88\x88\xfe\x07\x00"
NOW = datetime(2026, 10, 6, 1, 0, tzinfo=timezone.utc)
LIMITS = Limits(max_source_bytes=10 * 1024 * 1024, min_free_bytes=0)


def area(identifier="dolomites-tre-cime", *, countries=("IT",), hints=(), center=(12.30, 46.62), featured=False, kind="place"):
    document = {
        "schemaVersion": 1,
        "areaSizesKm": {"place": [16, 16], "route": [25, 10], "city": [8, 8]},
        "zoom": {"place": [12, 16], "route": [12, 16], "city": [12, 17]},
        "areas": [{
            "id": identifier, "kind": kind, "name": {"en": identifier}, "countryCodes": list(countries),
            "continent": "europe", "center": list(center), "tags": ["mountains"],
            **({"regionHints": list(hints)} if hints else {}),
            **({"featured": True} if featured else {}),
            **({"routeName": "Trail"} if kind == "route" else {}),
        }],
    }
    return parse_areas(document)[0]


def snapshot_row(package_id, provider="bbbike", *, region="EUROPE-ITALY", codes=("IT",), size=100,
                 map_type="bbbike-latin1", kind="main", url=None, release="2026-09-01", **extra):
    return {
        "provider_id": provider, "package_id": package_id, "provider_region_id": region,
        "package_region": region, "package_name": region, "map_type": map_type,
        "country_codes": list(codes), "availability": "AVAILABLE", "downloads_disabled": False,
        "release": release, "release_id": None, "artifact_kind": kind,
        "artifact_source_url": url or f"https://data.bbbike.org/osm/garmin/region/europe/{package_id}/{package_id}.osm.garmin-bbbike-latin1.zip",
        "artifact_size_bytes": size, "artifact_validation_status": "VALIDATED", **extra,
    }


class AreaListTests(unittest.TestCase):
    def test_packaged_copy_matches_contract(self):
        self.assertEqual(
            (CONTRACTS / "map-preview-areas.json").read_bytes(),
            areas_module.PACKAGED_AREAS.read_bytes(),
        )

    def test_extent_and_tiles(self):
        areas = load_areas()
        self.assertGreaterEqual(len(areas), 100)
        dolomites = next(item for item in areas if item.id == "dolomites-tre-cime")
        west, south, east, north = dolomites.bbox
        self.assertAlmostEqual((north - south) * 111.32, 16, places=3)
        self.assertTrue(dolomites.contains(*dolomites.center))
        x0, y0, x1, y1 = tile_range(dolomites.bbox, 12)
        self.assertLessEqual(x0, x1)
        self.assertLessEqual(y0, y1)
        self.assertGreater(tile_count(dolomites), 1000)
        city = next(item for item in areas if item.kind == "city")
        self.assertEqual(city.max_zoom, 17)

    def test_duplicate_area_is_rejected(self):
        document = json.loads((CONTRACTS / "map-preview-areas.json").read_text())
        document["areas"].append(dict(document["areas"][0]))
        with self.assertRaises(ValueError):
            parse_areas(document)


class PackageChoiceTests(unittest.TestCase):
    def test_hints_country_bounds_and_map_type(self):
        rows = [
            snapshot_row("italy", size=900),
            snapshot_row("nord-est", region="EUROPE-ITALY-NORD-EST", size=200),
            snapshot_row("sud", region="EUROPE-ITALY-SUD", size=50),
            snapshot_row("ontrail", map_type="ontrail-latin1", size=10),
            snapshot_row("france", region="EUROPE-FRANCE", codes=("FR",), size=1),
        ]
        packages = packages_from_snapshot(rows)
        target = area(hints=("nord-est",))
        chosen = candidates_for(target, STYLE_BY_ID["bbbike"], packages)
        self.assertEqual([c.package_id for c in chosen], ["nord-est", "sud", "italy"])
        self.assertTrue(chosen[0].hinted)
        # Recorded bounds that miss the centre remove a package.
        chosen = candidates_for(target, STYLE_BY_ID["bbbike"], packages,
                                known_bounds={("sud", "2026-09-01"): (14.0, 37.0, 18.0, 41.0)})
        self.assertNotIn("sud", [c.package_id for c in chosen])
        ontrail = candidates_for(target, STYLE_BY_ID["bbbike-ontrail"], packages)
        self.assertEqual([c.package_id for c in ontrail], ["ontrail"])

    def test_disabled_withheld_and_russian_packages_are_skipped(self):
        rows = [
            snapshot_row("off", downloads_disabled=True),
            {**snapshot_row("withheld"), "availability": "WITHHELD"},
            snapshot_row("ru", codes=("RU", "IT")),
            {**snapshot_row("broken"), "artifact_validation_status": "FAILED"},
        ]
        self.assertEqual(candidates_for(area(), STYLE_BY_ID["bbbike"], packages_from_snapshot(rows)), [])

    def test_freizeitkarte_alpha3_regions_and_contour_overlay(self):
        self.assertEqual(package_country_codes({"provider_id": "freizeitkarte", "provider_region_id": "BEL-NLD-LUX"}),
                         {"BE", "NL", "LU"})
        self.assertIn("ME", package_country_codes({"provider_id": "freizeitkarte", "provider_region_id": "BALKAN"}))
        rows = [
            snapshot_row("otm-it", provider="opentopomap", map_type=None,
                         url="https://garmin.opentopomap.org/europe/italy/otm-italy.zip"),
            snapshot_row("otm-it", provider="opentopomap", map_type=None, kind="contours", size=40,
                         url="https://garmin.opentopomap.org/europe/italy/otm-italy-contours.zip"),
        ]
        chosen = candidates_for(area(), STYLE_BY_ID["opentopomap"], packages_from_snapshot(rows))
        self.assertEqual(chosen[0].overlay_urls, ("https://garmin.opentopomap.org/europe/italy/otm-italy-contours.zip",))
        self.assertEqual(chosen[0].size_bytes, 140)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class FakeOpener:
    def __init__(self, payload=b"", error=None):
        self.payload, self.error, self.requests = payload, error, []

    def open(self, request, timeout):
        self.requests.append(request)
        if self.error:
            raise self.error
        return FakeResponse(self.payload)


class AcquisitionTests(unittest.TestCase):
    def test_only_reviewed_provider_paths(self):
        good = [
            ("freizeitkarte", "https://download.freizeitkarte-osm.de/garmin/latest/AND_en_gmapsupp.img.zip"),
            ("opentopomap", "https://garmin.opentopomap.org/europe/andorra/otm-andorra-contours.zip"),
            ("maprando", "https://ravenfeld.fr/MapRando/Saint-Barth%C3%A9lemy/MapRando_Saint-Barth%C3%A9lemy_2026_09_02.img"),
            ("bbbike", "https://data.bbbike.org/osm/garmin/region/europe/andorra/andorra.osm.garmin-ontrail-latin1.zip"),
        ]
        for provider, url in good:
            self.assertEqual(acquire.reviewed_url(provider, url), url)
        bad = [
            ("bbbike", "http://data.bbbike.org/osm/garmin/region/europe/andorra/andorra.osm.garmin-ontrail-latin1.zip"),
            ("bbbike", "https://evil.example/osm/garmin/region/europe/andorra/andorra.osm.garmin-ontrail-latin1.zip"),
            ("bbbike", "https://data.bbbike.org/osm/garmin/region/../x.osm.garmin-bbbike-latin1.zip"),
            ("opentopomap", "https://garmin.opentopomap.org/europe/andorra/otm-andorra.zip?x=1"),
            ("maprando", "https://ravenfeld.fr/other/file.img"),
            ("custom", "https://example.com/map.img"),
        ]
        for provider, url in bad:
            with self.assertRaises(AcquisitionError, msg=url):
                acquire.reviewed_url(provider, url)

    def test_download_caps_size_and_reports_rate_limits(self):
        url = "https://ravenfeld.fr/MapRando/Malte/MapRando_Malte_2026_09_02.img"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "map.img"
            opener = FakeOpener(b"x" * 64)
            acquire.download("maprando", url, target, expected_bytes=64, limits=LIMITS, opener=opener)
            self.assertEqual(target.read_bytes(), b"x" * 64)
            self.assertIn("TerentoCatalog", opener.requests[0].get_header("User-agent"))
            with self.assertRaises(AcquisitionError) as caught:
                acquire.download("maprando", url, target, expected_bytes=10,
                                 limits=Limits(max_source_bytes=100, min_free_bytes=0), opener=FakeOpener(b"x" * 500))
            self.assertEqual(caught.exception.code, "too_large")
            self.assertFalse(target.exists())
            error = HTTPError(url, 429, "Too Many", {"Retry-After": "3600"}, None)
            with self.assertRaises(AcquisitionError) as caught:
                acquire.download("maprando", url, target, expected_bytes=10, limits=LIMITS, opener=FakeOpener(error=error))
            self.assertEqual(caught.exception.code, "rate_limited")
            self.assertGreater(caught.exception.retry_not_before, datetime.now(timezone.utc) + timedelta(minutes=50))

    def test_disk_reserve_is_enforced(self):
        url = "https://ravenfeld.fr/MapRando/Malte/MapRando_Malte_2026_09_02.img"
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("terento_catalog.map_preview.acquire.shutil.disk_usage", return_value=mock.Mock(free=100)):
                with self.assertRaises(AcquisitionError) as caught:
                    acquire.download("maprando", url, Path(directory) / "m.img", expected_bytes=10,
                                     limits=Limits(max_source_bytes=1000, min_free_bytes=95), opener=FakeOpener(b"x"))
            self.assertEqual(caught.exception.code, "disk_space")

    def test_extract_prefers_gmapsupp_and_deletes_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "otm.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr("readme.txt", "x")
                bundle.writestr("extra.img", b"e" * 100)
                bundle.writestr("otm/gmapsupp.img", b"g" * 10)
            img = acquire.extract_img(archive, Path(directory), LIMITS)
            self.assertEqual(img.read_bytes(), b"g" * 10)
            self.assertFalse(archive.exists())
            broken = Path(directory) / "broken.zip"
            broken.write_bytes(b"not a zip")
            with self.assertRaises(AcquisitionError):
                acquire.extract_img(broken, Path(directory), LIMITS)
            self.assertFalse(broken.exists())


class ReleaseTests(unittest.TestCase):
    def stage(self, root: Path, area_id: str, style_id: str) -> Path:
        path = root / area_id / style_id / "14" / "8800"
        path.mkdir(parents=True)
        (path / "5800.webp").write_bytes(WEBP)
        return root / area_id / style_id

    def test_publish_links_unchanged_layers_serves_tiles_and_prunes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PreviewStore(Path(directory))
            staging = store.staging_dir("job1")
            store.publish(release="20261001T010000Z", staged={("a", "otm"): self.stage(staging, "a", "otm"),
                                                             ("b", "otm"): self.stage(staging, "b", "otm")}, keep=[])
            self.assertEqual(store.current_release(), "20261001T010000Z")
            staging = store.staging_dir("job2")
            store.publish(release="20261002T010000Z", staged={("a", "otm"): self.stage(staging, "a", "otm")},
                          keep=[("a", "otm"), ("b", "otm")])
            store.publish(release="20261003T010000Z", staged={}, keep=[("a", "otm")])
            self.assertEqual(store.current_release(), "20261003T010000Z")
            self.assertEqual(store.layers("20261003T010000Z"), {("a", "otm")})
            remaining = sorted(path.name for path in store.releases.iterdir())
            self.assertEqual(remaining, ["20261002T010000Z", "20261003T010000Z"])
            # Hard links: the kept layer shares its bytes with the previous release,
            # so only the two distinct tile files and the pointer count.
            current_tile = store.releases / "20261003T010000Z/a/otm/14/8800/5800.webp"
            previous_tile = store.releases / "20261002T010000Z/a/otm/14/8800/5800.webp"
            self.assertEqual(current_tile.stat().st_ino, previous_tile.stat().st_ino)
            self.assertEqual(store.disk_usage(), 2 * len(WEBP) + len(b'{"release": "20261003T010000Z"}'))
            body, etag = store.tile("/assets/previews/20261003T010000Z/a/otm/14/8800/5800.webp")
            self.assertEqual(body, WEBP)
            self.assertTrue(etag.startswith('"20261003T010000Z-'))
            for path in (
                "/assets/previews/20261003T010000Z/a/otm/14/8800/../5800.webp",
                "/assets/previews/20261003T010000Z/A/otm/14/8800/5800.webp",
                "/assets/previews/20261003T010000Z/a/otm/14/8800/5800.png",
                "/assets/previews/current.json",
            ):
                self.assertIsNone(store.tile(path), path)

    def test_non_webp_file_is_not_served(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PreviewStore(Path(directory))
            staging = store.staging_dir("job")
            layer = self.stage(staging, "a", "otm")
            (layer / "14" / "8800" / "5800.webp").write_bytes(b"<html>")
            store.publish(release="20261001T010000Z", staged={("a", "otm"): layer}, keep=[])
            self.assertIsNone(store.tile("/assets/previews/20261001T010000Z/a/otm/14/8800/5800.webp"))


class ManifestTests(unittest.TestCase):
    def test_manifest_matches_public_contract(self):
        validator = Draft202012Validator(json.loads((CONTRACTS / "map-preview-manifest.schema.json").read_text()))
        areas = load_areas()
        layers = {
            ("dolomites-tre-cime", "opentopomap"): {"status": "AVAILABLE", "release": "20261006T010000Z",
                                                    "package_version": "2026-09", "rendered_at": NOW},
            ("dolomites-tre-cime", "bbbike"): {"status": "AVAILABLE", "release": "20261001T010000Z",
                                               "package_version": "2026-09", "rendered_at": NOW},
            ("mount-fuji", "freizeitkarte"): {"status": "NOT_COVERED", "release": None},
        }
        document = build_manifest(
            areas=areas, layers=layers, published={("dolomites-tre-cime", "opentopomap")},
            scores={"dolomites-tre-cime": 0.4}, release="20261006T010000Z",
            public_base_url="https://api.terento.app", now=NOW,
        )
        self.assertEqual(list(validator.iter_errors(document)), [])
        dolomites = next(item for item in document["areas"] if item["id"] == "dolomites-tre-cime")
        statuses = {layer["style"]: layer["status"] for layer in dolomites["layers"]}
        self.assertEqual(statuses["opentopomap"], "AVAILABLE")
        # A layer from an older release is not advertised as published.
        self.assertEqual(statuses["bbbike"], "PENDING")
        self.assertEqual(dolomites["diffScore"], 0.4)
        fuji = next(item for item in document["areas"] if item["id"] == "mount-fuji")
        self.assertEqual(fuji["layers"][0]["status"], "NOT_COVERED")
        empty = build_manifest(areas=areas, layers={}, published=set(), scores={}, release=None,
                               public_base_url="https://api.terento.app", now=NOW)
        self.assertEqual(list(validator.iter_errors(empty)), [])
        self.assertIsNone(empty["tileUrlTemplate"])


class FakePreviewDatabase:
    def __init__(self, enabled=("bbbike",)):
        self.enabled, self.rows, self.bounds, self.scores_saved, self.released = set(enabled), {}, {}, {}, []
        self.lease = None

    def acquire_lease(self, owner, seconds):
        self.lease_calls = getattr(self, "lease_calls", []) + [seconds]
        if self.lease and self.lease != owner:
            return False
        self.lease = owner
        return True

    def release_lease(self, owner):
        self.lease = None

    def enabled_providers(self):
        return self.enabled

    def layers(self):
        return {key: dict(value) for key, value in self.rows.items()}

    def package_bounds(self):
        return dict(self.bounds)

    def save_bounds(self, package_id, version, bounds):
        self.bounds[(package_id, version)] = bounds

    def save_layer(self, area_id, style_id, provider_id, status, *, keep_rendered=False, **values):
        row = self.rows.setdefault((area_id, style_id), {})
        if keep_rendered:
            row.update(error_code=values.get("error_code"), retry_not_before=values.get("retry_not_before"))
            return
        row.update(status=status, provider_id=provider_id, package_id=values.get("package_id"),
                   package_version=values.get("package_version"), rendered_at=values.get("rendered_at"),
                   retry_not_before=values.get("retry_not_before"), error_code=values.get("error_code"))

    def mark_released(self, release, layers, count, total):
        self.released.append((release, list(layers)))
        for key in layers:
            if key in self.rows:
                self.rows[key]["release"] = release

    def save_score(self, area_id, score):
        self.scores_saved[area_id] = score


class FakeRenderer:
    def __init__(self, bounds=(11.0, 45.0, 13.0, 47.0), fail=False):
        self.bounds, self.fail, self.rendered = bounds, fail, []

    def info(self, img):
        return MapInfo(self.bounds, False, True)

    def render(self, area, imgs, output):
        if self.fail:
            raise RenderError("render_failed", "boom")
        self.rendered.append((area.id, [path.name for path in imgs]))
        target = output / "14" / "8800"
        target.mkdir(parents=True)
        (target / "5800.webp").write_bytes(WEBP)
        return RenderResult(1, len(WEBP), 0.1)

    def compare(self, first, second, zoom):
        return 0.25


class CatalogDatabase:
    def __init__(self, rows):
        self.rows = rows

    def catalog_snapshot(self):
        return self.rows, NOW


def settings(root: Path, **overrides) -> PreviewSettings:
    values = dict(
        enabled=True, asset_root=root / "assets", work_dir=root / "work",
        window_utc=(day_time(0, 0), day_time(6, 0)), refresh_days=90,
        max_total_bytes=10**9, max_source_bytes=10**7, min_free_bytes=0,
        renderer=root / "renderer", public_base_url="https://api.terento.app",
    )
    values.update(overrides)
    return PreviewSettings(**values)


class WindowTests(unittest.TestCase):
    def test_window_parsing(self):
        self.assertEqual(parse_window("00:00-06:00"), (day_time(0), day_time(6)))
        with self.assertRaises(RuntimeError):
            parse_window("06:00")
        start, end = next_window(datetime(2026, 10, 6, 7, tzinfo=timezone.utc), (day_time(0), day_time(6)))
        self.assertEqual(start, datetime(2026, 10, 7, tzinfo=timezone.utc))
        start, end = next_window(datetime(2026, 10, 6, 23, 30, tzinfo=timezone.utc), (day_time(23), day_time(2)))
        self.assertEqual((start.hour, end.day), (23, 7))
        around_the_clock = parse_window("00:00-00:00")
        start, end = next_window(datetime(2026, 10, 6, 15, 40, tzinfo=timezone.utc), around_the_clock)
        self.assertEqual((start, end - start), (datetime(2026, 10, 6, tzinfo=timezone.utc), timedelta(days=1)))

    def test_plan_skips_fresh_layers_and_backoff(self):
        target = area()
        packages = packages_from_snapshot([snapshot_row("italy")])
        fresh = {(target.id, "bbbike"): {"status": "AVAILABLE", "package_id": "italy",
                                          "package_version": "2026-09-01", "rendered_at": NOW - timedelta(days=5)}}
        work, uncovered = plan_work([target], packages, fresh, {}, {"bbbike"}, now=NOW, refresh_days=90)
        self.assertEqual(work, [])
        # The Ontrail style of the same provider has no package here.
        self.assertEqual([style.id for _area, style in uncovered], ["bbbike-ontrail"])
        stale = {(target.id, "bbbike"): {**fresh[(target.id, "bbbike")], "rendered_at": NOW - timedelta(days=120)}}
        work, _ = plan_work([target], packages, stale, {}, {"bbbike"}, now=NOW, refresh_days=90)
        self.assertEqual(len(work), 1)
        waiting = {(target.id, "bbbike"): {"status": "FAILED", "retry_not_before": NOW + timedelta(days=1)}}
        work, _ = plan_work([target], packages, waiting, {}, {"bbbike"}, now=NOW, refresh_days=90)
        self.assertEqual(work, [])
        work, uncovered = plan_work([target], [], {}, {}, {"bbbike"}, now=NOW, refresh_days=90)
        self.assertEqual(len(uncovered), 2)


class PreviewRunTests(unittest.TestCase):
    def run_window(self, root, rows, *, renderer=None, db=None, downloader=None, **setting_values):
        db = db or FakePreviewDatabase()
        renderer = renderer or FakeRenderer()
        downloads = []

        def fake_download(provider_id, url, destination, *, expected_bytes, limits):
            downloads.append(url)
            destination.write_bytes(b"IMG")
            return destination

        run = PreviewRun(
            CatalogDatabase(rows), settings(root, **setting_values), renderer=renderer, db=db,
            areas=[area("a", hints=("nord-est",)), area("b", center=(12.4, 46.5))],
            downloader=downloader or fake_download, clock=lambda: NOW,
        )
        result = run.run(NOW + timedelta(hours=5))
        return result, db, renderer, downloads, run

    def test_one_download_per_package_publishes_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [snapshot_row("nord-est", region="EUROPE-ITALY-NORD-EST",
                                 url="https://data.bbbike.org/osm/garmin/region/europe/italy/nord-est.osm.garmin-bbbike-latin1.img")]
            result, db, renderer, downloads, run = self.run_window(root, rows)
            self.assertEqual(result.rendered, 2)
            self.assertEqual(len(downloads), 1)
            self.assertEqual(db.rows[("a", "bbbike")]["status"], "AVAILABLE")
            self.assertIsNotNone(result.release)
            self.assertEqual(run.store.layers(result.release), {("a", "bbbike"), ("b", "bbbike")})
            self.assertEqual(list((root / "work").iterdir()), [])
            self.assertFalse(run.store.staging.exists())
            self.assertIsNone(db.lease)
            self.assertIn(("nord-est", "2026-09-01"), db.bounds)

    def test_long_windows_publish_finished_layers_progressively(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = [
                snapshot_row("nord-est", region="EUROPE-ITALY-NORD-EST",
                             url="https://data.bbbike.org/osm/garmin/region/europe/italy/nord-est.osm.garmin-bbbike-latin1.img"),
                snapshot_row("sud", region="EUROPE-ITALY-SUD", size=50,
                             url="https://data.bbbike.org/osm/garmin/region/europe/italy/sud.osm.garmin-bbbike-latin1.img"),
            ]
            result, db, _, downloads, run = self.run_window(Path(directory), rows, publish_interval=timedelta(0))
            self.assertEqual((result.rendered, len(downloads)), (2, 2))
            self.assertEqual(len(db.released), 2)
            self.assertEqual(db.released[0][1], [("a", "bbbike")])
            self.assertEqual(run.store.layers(result.release), {("a", "bbbike"), ("b", "bbbike")})
            self.assertFalse(run.store.staging.exists())

    def test_short_renewed_lease_and_leftovers_from_a_killed_renderer_are_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "work" / "old-run").mkdir(parents=True)
            (root / "work" / "old-run" / "gmapsupp.img").write_bytes(b"IMG")
            (root / "work" / "stray.zip").write_bytes(b"ZIP")
            rows = [snapshot_row("nord-est", region="EUROPE-ITALY-NORD-EST",
                                 url="https://data.bbbike.org/osm/garmin/region/europe/italy/nord-est.osm.garmin-bbbike-latin1.img")]

            def slow_download(provider_id, url, destination, *, expected_bytes, limits):
                time.sleep(0.2)
                destination.write_bytes(b"IMG")
                return destination

            db = FakePreviewDatabase()
            with mock.patch.object(job_module, "LEASE_RENEW_SECONDS", 0.02):
                result, db, _, _, _ = self.run_window(root, rows, db=db, downloader=slow_download)
            self.assertEqual(result.rendered, 2)
            self.assertEqual(db.lease_calls[0], job_module.LEASE_SECONDS)
            self.assertGreater(len(db.lease_calls), 2)
            self.assertTrue(all(seconds == job_module.LEASE_SECONDS for seconds in db.lease_calls))
            self.assertEqual(list((root / "work").iterdir()), [])
            self.assertIsNone(db.lease)

    def test_package_not_covering_area_moves_to_next_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = [
                snapshot_row("small", region="EUROPE-ITALY-SUD", size=10,
                             url="https://data.bbbike.org/osm/garmin/region/europe/italy/small.osm.garmin-bbbike-latin1.img"),
                snapshot_row("large", region="EUROPE-ITALY", size=900,
                             url="https://data.bbbike.org/osm/garmin/region/europe/italy/large.osm.garmin-bbbike-latin1.img"),
            ]

            class SequencedRenderer(FakeRenderer):
                def info(self, img):
                    covering = "large" in str(img)
                    return MapInfo((11.0, 45.0, 13.0, 47.0) if covering else (14.0, 37.0, 18.0, 41.0), False, True)

            def fake_download(provider_id, url, destination, *, expected_bytes, limits):
                destination = destination.with_name(url.rsplit("/", 1)[-1])
                destination.write_bytes(b"IMG")
                return destination

            result, db, renderer, downloads, _ = self.run_window(
                Path(directory), rows, renderer=SequencedRenderer(), downloader=fake_download,
            )
            self.assertEqual(result.rendered, 2)
            self.assertEqual(db.rows[("a", "bbbike")]["package_id"], "large")
            self.assertIn(("small", "2026-09-01"), db.bounds)

    def test_failures_are_recorded_and_sources_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [snapshot_row("nord-est", url="https://data.bbbike.org/osm/garmin/region/europe/italy/ne.osm.garmin-bbbike-latin1.img")]
            result, db, _, _, run = self.run_window(root, rows, renderer=FakeRenderer(fail=True))
            self.assertEqual(result.failed, 2)
            self.assertIsNone(result.release)
            self.assertEqual(db.rows[("a", "bbbike")]["status"], "FAILED")
            self.assertGreater(db.rows[("a", "bbbike")]["retry_not_before"], NOW)
            self.assertEqual(list((root / "work").iterdir()), [])

            def rate_limited(*args, **kwargs):
                raise AcquisitionError("rate_limited", "slow down", retry_not_before=NOW + timedelta(hours=2))

            result, db, _, _, _ = self.run_window(root, rows, downloader=rate_limited)
            self.assertEqual(db.rows[("a", "bbbike")]["error_code"], "rate_limited")
            self.assertEqual(db.rows[("a", "bbbike")]["retry_not_before"], NOW + timedelta(hours=2))

    def test_disk_budget_stops_the_window(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = [snapshot_row("nord-est", url="https://data.bbbike.org/osm/garmin/region/europe/italy/ne.osm.garmin-bbbike-latin1.img")]
            result, db, renderer, downloads, _ = self.run_window(Path(directory), rows, max_total_bytes=1000)
            self.assertTrue(result.skipped_budget)
            self.assertEqual(downloads, [])
            self.assertEqual(renderer.rendered, [])

    def test_disabled_provider_is_not_rendered(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = [snapshot_row("nord-est")]
            result, _, renderer, downloads, _ = self.run_window(Path(directory), rows, db=FakePreviewDatabase(enabled=()))
            self.assertEqual((result.rendered, downloads), (0, []))

    def test_lease_held_elsewhere_skips_the_window(self):
        with tempfile.TemporaryDirectory() as directory:
            db = FakePreviewDatabase()
            db.lease = "other-host"
            result, _, _, downloads, _ = self.run_window(Path(directory), [snapshot_row("nord-est")], db=db)
            self.assertEqual((result.rendered, downloads), (0, []))


@unittest.skipUnless(
    os.environ.get("TERENTO_PREVIEW_RENDERER") and Path(os.environ["TERENTO_PREVIEW_RENDERER"]).is_file(),
    "set TERENTO_PREVIEW_RENDERER to a built terento-preview-render to run",
)
class RendererBinaryTests(unittest.TestCase):
    def test_renders_synthetic_fixture(self):
        renderer = Renderer(Path(os.environ["TERENTO_PREVIEW_RENDERER"]))
        info = renderer.info(FIXTURE_IMG)
        self.assertTrue(info.covers(1.53, 42.51))
        fixture_area = area("fixture", countries=("AD",), center=(1.532, 42.512), kind="city")
        fixture_area = PreviewArea(**{**fixture_area.__dict__, "min_zoom": 14, "max_zoom": 15})
        with tempfile.TemporaryDirectory() as directory:
            result = renderer.render(fixture_area, [FIXTURE_IMG], Path(directory) / "a")
            self.assertGreater(result.tiles, 4)
            tiles = list(Path(directory, "a").rglob("*.webp"))
            self.assertEqual(len(tiles), result.tiles)
            self.assertTrue(all(tile.read_bytes()[8:12] == b"WEBP" for tile in tiles))
            renderer.render(fixture_area, [FIXTURE_IMG, FIXTURE_IMG], Path(directory) / "b")
            self.assertEqual(renderer.compare(Path(directory) / "a", Path(directory) / "a", 14), 0.0)
            self.assertLess(renderer.compare(Path(directory) / "a", Path(directory) / "b", 14), 0.05)

    def test_parallel_rendering_matches_serial_output(self):
        executable = Path(os.environ["TERENTO_PREVIEW_RENDERER"])
        fixture_area = area("fixture", countries=("AD",), center=(1.532, 42.512), kind="city")
        fixture_area = PreviewArea(**{**fixture_area.__dict__, "min_zoom": 13, "max_zoom": 15})
        with tempfile.TemporaryDirectory() as directory:
            serial = Renderer(executable, jobs=1).render(fixture_area, [FIXTURE_IMG], Path(directory) / "serial")
            parallel = Renderer(executable, jobs=4).render(fixture_area, [FIXTURE_IMG], Path(directory) / "parallel")
            self.assertEqual((serial.tiles, serial.bytes), (parallel.tiles, parallel.bytes))
            for tile in Path(directory, "serial").rglob("*.webp"):
                twin = Path(directory, "parallel", tile.relative_to(Path(directory, "serial")))
                self.assertEqual(tile.read_bytes(), twin.read_bytes())


class RendererSettingsTests(unittest.TestCase):
    def test_jobs_scale_the_memory_limit_and_are_bounded(self):
        self.assertEqual(Renderer(jobs=1).memory_limit_bytes, 1536 * 1024 * 1024)
        self.assertEqual(Renderer(jobs=3).memory_limit_bytes, 2560 * 1024 * 1024)
        self.assertEqual((Renderer(jobs=0).jobs, Renderer(jobs=99).jobs), (1, 16))
        self.assertEqual(settings(Path("/tmp")).render_jobs, 1)


class PreviewHTTPTests(unittest.TestCase):
    def test_manifest_and_tile_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = AssetStorage(Path(directory))
            store = PreviewStore(Path(directory))
            staging = store.staging_dir("job")
            tile_dir = staging / "dolomites-tre-cime" / "bbbike" / "14" / "8800"
            tile_dir.mkdir(parents=True)
            (tile_dir / "5800.webp").write_bytes(WEBP)
            store.publish(release="20261006T010000Z",
                          staged={("dolomites-tre-cime", "bbbike"): staging / "dolomites-tre-cime" / "bbbike"}, keep=[])

            class FakeStoreDatabase:
                def __init__(self, database):
                    pass

                def enabled_providers(self):
                    return {"bbbike"}

                def layers(self):
                    return {("dolomites-tre-cime", "bbbike"): {"status": "AVAILABLE", "provider_id": "bbbike",
                                                               "release": "20261006T010000Z", "package_version": "x",
                                                               "rendered_at": NOW},
                            ("dolomites-tre-cime", "maprando"): {"status": "AVAILABLE", "provider_id": "maprando",
                                                                 "release": "20261006T010000Z", "package_version": "x",
                                                                 "rendered_at": NOW}}

                def scores(self):
                    return {}

            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(CatalogService(object(), asset_storage=storage)))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with mock.patch("terento_catalog.map_preview.store.PreviewDatabase", FakeStoreDatabase):
                    connection = HTTPConnection(*server.server_address)
                    connection.request("GET", "/maps/previews/manifest.json")
                    response = connection.getresponse()
                    manifest = json.loads(response.read())
                    connection.close()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Cache-Control"], "public, max-age=300")
                dolomites = next(item for item in manifest["areas"] if item["id"] == "dolomites-tre-cime")
                statuses = {layer["style"]: layer["status"] for layer in dolomites["layers"]}
                self.assertEqual(statuses["bbbike"], "AVAILABLE")
                # Disabled providers are never advertised, even with rows.
                self.assertEqual(statuses["maprando"], "PENDING")
                path = manifest["tileUrlTemplate"].replace("https://api.terento.app", "").format(
                    area="dolomites-tre-cime", style="bbbike", z=14, x=8800, y=5800)
                connection = HTTPConnection(*server.server_address)
                connection.request("GET", path)
                response = connection.getresponse()
                body = response.read()
                connection.close()
                self.assertEqual(response.status, 200)
                self.assertEqual(body, WEBP)
                self.assertEqual(response.headers["Content-Type"], "image/webp")
                self.assertIn("immutable", response.headers["Cache-Control"])
                connection = HTTPConnection(*server.server_address)
                connection.request("GET", path, headers={"If-None-Match": response.headers["ETag"]})
                cached = connection.getresponse()
                cached.read()
                connection.close()
                self.assertEqual(cached.status, 304)
                connection = HTTPConnection(*server.server_address)
                connection.request("GET", "/assets/previews/20261006T010000Z/../../current.json")
                missing = connection.getresponse()
                missing.read()
                connection.close()
                self.assertEqual(missing.status, 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
