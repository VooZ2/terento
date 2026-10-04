"""Provider health aggregation must not hide a failed sample or block healthy downloads."""
import unittest
from types import SimpleNamespace
from urllib.error import HTTPError
from terento_catalog.provider_catalog import OPENTOPO_MAP
from terento_catalog.provider_health import HTTPProbeResult, check_provider, _retry_after_seconds

ROOT = "https://garmin.opentopomap.org/"


class Probe:
    def __init__(self, outcomes=None, bad_zip=(), limited_magic=False):
        self.outcomes = outcomes or {}
        self.bad_zip = bad_zip
        self.limited_magic = limited_magic
        self.calls = []

    def inspect(self, url, *, read_body=False):
        self.calls.append(url)
        outcome = self.outcomes.get(url, 200)
        if isinstance(outcome, Exception):
            raise outcome
        return HTTPProbeResult(outcome, url, "application/zip", body=b"catalog", retry_after="7200")

    def inspect_magic(self, url):
        self.calls.append("magic:" + url)
        if self.limited_magic:
            raise HTTPError(url, 429, "limited", {"Retry-After": "7200"}, None)
        return b"PK\x03\x04"

    def inspect_zip(self, url):
        self.calls.append("zip:" + url)
        if url in self.bad_zip:
            raise ValueError("invalid package")
        return SimpleNamespace(install_size_bytes=123)


class ProviderHealthTests(unittest.TestCase):
    def test_order_independent_mixed_failures(self):
        for failure in (OSError("offline"), 503, 404):
            for urls in ([ROOT + "bad.zip", ROOT + "ok.zip"], [ROOT + "ok.zip", ROOT + "bad.zip"]):
                result = check_provider(OPENTOPO_MAP, download_urls=urls, probe=Probe({ROOT + "bad.zip": failure}))
                self.assertEqual(result.download_status, "DEGRADED")
                self.assertNotEqual(result.status, "DOWN")

    def test_all_transport_failures_down_but_missing_map_degraded(self):
        for failure, expected in ((OSError("offline"), "DOWN"), (503, "DOWN"), (404, "DEGRADED")):
            probe = Probe({ROOT + "bad.zip": failure})
            result = check_provider(OPENTOPO_MAP, download_urls=[ROOT + "bad.zip"], probe=probe)
            self.assertEqual(result.download_status, expected)
            self.assertEqual(result.zip_status, "UNKNOWN")
            self.assertFalse(any(call.startswith("zip:") for call in probe.calls))

    def test_unavailable_website_does_not_change_download_availability(self):
        result = check_provider(OPENTOPO_MAP, download_urls=[ROOT + "ok.zip"], probe=Probe({OPENTOPO_MAP.website: OSError("offline")}))
        self.assertEqual(result.website_status, "DOWN")
        self.assertEqual(result.download_status, "HEALTHY")

    def test_validation_failure_not_overwritten(self):
        for urls in ([ROOT + "bad.zip", ROOT + "ok.zip"], [ROOT + "ok.zip", ROOT + "bad.zip"]):
            result = check_provider(OPENTOPO_MAP, download_urls=urls, probe=Probe(bad_zip={ROOT + "bad.zip"}))
            self.assertEqual(result.download_status, "DEGRADED")
            self.assertEqual(result.img_status, "DEGRADED")
            self.assertEqual(result.zip_status, "DEGRADED")

    def test_no_samples_and_bounded_iterator(self):
        result = check_provider(OPENTOPO_MAP, probe=Probe())
        self.assertEqual(result.download_status, "UNKNOWN")
        self.assertIn("no_samples", result.error_detail)
        def urls():
            for i in range(8):
                yield ROOT + str(i) + ".zip"
            raise AssertionError("must not consume beyond the sample cap")
        result = check_provider(OPENTOPO_MAP, download_urls=urls(), probe=Probe())
        self.assertEqual(result.artifact_count, 8)

    def test_rate_limit_stops_all_following_requests(self):
        for url in (OPENTOPO_MAP.website, OPENTOPO_MAP.catalog_url, ROOT + "limited.zip"):
            probe = Probe({url: 429})
            result = check_provider(OPENTOPO_MAP, download_urls=[ROOT + "limited.zip", ROOT + "next.zip"], probe=probe)
            self.assertEqual(result.retry_after_seconds, 7200)
            self.assertEqual(result.download_status, "DEGRADED")
            self.assertEqual(probe.calls[-1], url)
            self.assertIn("not_evaluated", result.error_detail)

    def test_range_rate_limit_stops_before_zip_and_other_samples(self):
        probe = Probe(limited_magic=True)
        result = check_provider(OPENTOPO_MAP, download_urls=[ROOT + "one.zip", ROOT + "two.zip"], probe=probe)
        self.assertEqual(result.retry_after_seconds, 7200)
        self.assertEqual(result.download_status, "DEGRADED")
        self.assertEqual(probe.calls[-1], "magic:" + ROOT + "one.zip")

    def test_retry_after_default_date_and_bounds(self):
        self.assertEqual(_retry_after_seconds(None), 3600)
        self.assertEqual(_retry_after_seconds("invalid"), 3600)
        self.assertEqual(_retry_after_seconds("0"), 60)
        self.assertEqual(_retry_after_seconds("999999999"), 604800)
        self.assertGreaterEqual(_retry_after_seconds("Wed, 01 Jan 2031 00:00:00 GMT"), 60)

if __name__ == "__main__":
    unittest.main()
