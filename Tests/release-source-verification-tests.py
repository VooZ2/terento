import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('source_gate', Path(__file__).resolve().parents[1] / 'Packaging/verify-github-release-source.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
SHA = 'a' * 40

class SourceVerificationTests(unittest.TestCase):
    def responses(self, verified=True, reason='valid', status='ahead', sha=SHA):
        return ['', SHA, json.dumps({'sha': sha, 'commit': {'verification': {'verified': verified, 'reason': reason}}}), json.dumps({'status': status})]

    def test_verified_merged_source(self):
        for status in ('ahead', 'identical'):
            with patch.object(gate, 'run', side_effect=self.responses(status=status)):
                self.assertEqual(gate.verify(), SHA)

    def test_unsigned_invalid_or_wrong_source_rejected(self):
        for args in ({'verified': False, 'reason': 'unsigned'}, {'reason': 'unknown_key'}, {'sha': 'b'*40}):
            with patch.object(gate, 'run', side_effect=self.responses(**args)), self.assertRaises(ValueError):
                gate.verify()

    def test_unmerged_source_rejected(self):
        for status in ('behind', 'diverged', None):
            with patch.object(gate, 'run', side_effect=self.responses(status=status)), self.assertRaises(ValueError):
                gate.verify()

    def test_dirty_checkout_stops_before_network(self):
        with patch.object(gate, 'run', return_value='?? untracked.swift') as run, self.assertRaises(ValueError):
            gate.verify()
        self.assertEqual(run.call_count, 1)

    def test_api_failure_is_not_accepted(self):
        with patch.object(gate, 'run', side_effect=gate.subprocess.TimeoutExpired('gh', 60)), self.assertRaises(gate.subprocess.SubprocessError):
            gate.verify()

if __name__ == '__main__':
    unittest.main()
