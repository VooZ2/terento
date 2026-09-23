import unittest

from terento_catalog.statistics_exclusions import (
    OUT_OF_SCOPE_PREWRITE,
    SECURITY_OUT_OF_SCOPE_WRITE,
    classify_compatibility_event,
)


class StatisticsExclusionTests(unittest.TestCase):
    def setUp(self):
        self.devices = [{
            "id": "garmin-edge-840",
            "support_status": "UNSUPPORTED",
            "active": True,
            "map_capable": False,
        }]
        self.assessment = {"canonicalDeviceId": "garmin-edge-840"}

    def test_three_edge_outcomes_are_classified_without_guessing_unknown_history(self):
        prewrite = classify_compatibility_event(
            {"model": "Edge 840", "writeStarted": False, "remoteObjectCreated": False},
            self.devices,
            self.assessment,
        )
        self.assertEqual(prewrite["statisticsExclusionCode"], OUT_OF_SCOPE_PREWRITE)
        self.assertNotIn("securityIssueCode", prewrite)

        write_reached = classify_compatibility_event(
            {"model": "Edge 840", "writeStarted": True, "remoteObjectCreated": False},
            self.devices,
            self.assessment,
        )
        self.assertEqual(write_reached["securityIssueCode"], SECURITY_OUT_OF_SCOPE_WRITE)
        self.assertNotIn("statisticsExclusionCode", write_reached)

        old_unknown = classify_compatibility_event(
            {"model": "Edge 840", "writeStarted": None, "remoteObjectCreated": None},
            self.devices,
            self.assessment,
        )
        self.assertIsNone(old_unknown)
        missing_remote_fact = classify_compatibility_event(
            {"model": "Edge 840", "writeStarted": False,
             "remoteObjectCreated": None},
            self.devices,
            self.assessment,
        )
        self.assertIsNone(missing_remote_fact)

    def test_unrelated_unknown_watch_is_preserved(self):
        result = classify_compatibility_event(
            {"model": "fēnix 8", "writeStarted": False, "remoteObjectCreated": False},
            self.devices,
            {"canonicalDeviceId": None},
        )
        self.assertIsNone(result)

    def test_future_edge_maps_yes_is_not_excluded_by_name_or_support_metadata(self):
        device = {"id": "garmin-edge-840", "active": True,
                  "map_capable": True, "support_status": "UNSUPPORTED"}
        result = classify_compatibility_event(
            {"model": "Edge 840", "writeStarted": False,
             "remoteObjectCreated": False},
            [device], self.assessment,
        )
        self.assertIsNone(result)

    def test_uncataloged_edge_and_unknown_maps_are_not_guessed_out_of_scope(self):
        event = {"model": "Edge 840", "writeStarted": False,
                 "remoteObjectCreated": False}
        self.assertIsNone(classify_compatibility_event(
            event, [], {"canonicalDeviceId": None}
        ))
        self.assertIsNone(classify_compatibility_event(
            event, [{"id": "garmin-edge-840", "active": True,
                     "map_capable": None, "support_status": "UNSUPPORTED"}],
            self.assessment,
        ))

if __name__ == "__main__":
    unittest.main()
