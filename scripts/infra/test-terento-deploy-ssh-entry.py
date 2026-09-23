"""Offline tests for the fixed-role Terento production SSH command boundary."""

import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).parent
TEMPLATE = (ROOT / 'terento-deploy-ssh-entry.py.in').read_text(encoding='utf-8')
DIGEST = 'sha256:' + 'a' * 64
REVISION = 'b' * 40
SQL_SHA = 'c' * 64
RUNNER_SHA = 'd' * 64


def invoke(project, command):
    with tempfile.TemporaryDirectory() as directory:
        entry = Path(directory) / 'entry.py'
        entry.write_text(TEMPLATE.replace('@PROJECT@', project), encoding='utf-8')
        with patch.dict(os.environ, {'SSH_ORIGINAL_COMMAND': command}, clear=True), \
                patch('subprocess.call', return_value=0) as call:
            with unittest.TestCase().assertRaises(SystemExit) as stopped:
                runpy.run_path(str(entry), run_name='__main__')
        return stopped.exception.code, call


class SSHEntryTests(unittest.TestCase):
    def test_api_deploy_preserves_the_existing_scoped_route(self):
        result, call = invoke('api', f'deploy {DIGEST} {REVISION}')
        self.assertEqual(result, 0)
        self.assertEqual(call.call_args.args[0], [
            '/usr/bin/sudo', '-n', '/usr/local/sbin/terento-deploy',
            'api', DIGEST, REVISION,
        ])
        self.assertEqual(call.call_args.kwargs['stdin'], subprocess.DEVNULL)

    def test_site_principal_remains_deploy_only(self):
        for command in ('status', 'migrate --target 062', f'deploy {DIGEST} {REVISION}; id'):
            with self.subTest(command=command):
                result, call = invoke('site', command)
                self.assertEqual(result, 64)
                call.assert_not_called()

    def test_api_status_is_read_only_and_maps_to_the_fixed_root_helper(self):
        result, call = invoke('api', 'status')
        self.assertEqual(result, 0)
        self.assertEqual(call.call_args.args[0], [
            '/usr/bin/sudo', '-n', '/usr/local/sbin/terento-deploy', 'api', 'status',
        ])

    def test_api_status_can_pin_a_candidate_receipt(self):
        command = (
            f'status --candidate-digest {DIGEST} --candidate-revision {REVISION}'
            f' --expected-migration-062-sha256 {SQL_SHA}'
        )
        result, call = invoke('api', command)
        self.assertEqual(result, 0)
        self.assertEqual(call.call_args.args[0], [
            '/usr/bin/sudo', '-n', '/usr/local/sbin/terento-deploy', 'api', 'status',
            '--candidate-digest', DIGEST,
            '--candidate-revision', REVISION,
            '--expected-migration-062-sha256', SQL_SHA,
        ])

    def test_api_migration_forwards_only_explicit_receipt_bound_062(self):
        command = (
            f'migrate --target 062 --image {DIGEST} --revision {REVISION}'
            f' --expected-migration-062-sha256 {SQL_SHA}'
            f' --expected-migrate-py-sha256 {RUNNER_SHA}'
        )
        result, call = invoke('api', command)
        self.assertEqual(result, 0)
        self.assertEqual(call.call_args.args[0], [
            '/usr/bin/sudo', '-n', '/usr/local/sbin/terento-deploy', 'api', 'migrate',
            '--target', '062', '--image', DIGEST, '--revision', REVISION,
            '--expected-migration-062-sha256', SQL_SHA,
            '--expected-migrate-py-sha256', RUNNER_SHA,
        ])
        self.assertEqual(call.call_args.kwargs['stdin'], subprocess.DEVNULL)
        self.assertEqual(call.call_args.kwargs['env'], {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin'})

    def test_malformed_status_or_migration_commands_are_rejected_without_sudo(self):
        commands = (
            'status --candidate-digest ' + DIGEST,
            'status; id',
            f'migrate --target 061 --image {DIGEST} --revision {REVISION}'
            f' --expected-migration-062-sha256 {SQL_SHA}'
            f' --expected-migrate-py-sha256 {RUNNER_SHA}',
            f'migrate --target 062 --image latest --revision {REVISION}'
            f' --expected-migration-062-sha256 {SQL_SHA}'
            f' --expected-migrate-py-sha256 {RUNNER_SHA}',
            f'migrate --target 062 --image {DIGEST} --revision {REVISION}'
            f' --expected-migration-062-sha256 {SQL_SHA} --expected-migrate-py-sha256 {RUNNER_SHA}; id',
        )
        for command in commands:
            with self.subTest(command=command):
                result, call = invoke('api', command)
                self.assertEqual(result, 64)
                call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
