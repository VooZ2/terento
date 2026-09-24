"""Focused tests for the tracked canonical Terento root deployment helper."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location('terento_deploy', ROOT/'terento-deploy.py')
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)
MIGRATION_SPEC = importlib.util.spec_from_file_location(
    'terento_deploy_migration', ROOT/'terento-deploy-migration.py'
)
migration = importlib.util.module_from_spec(MIGRATION_SPEC)
sys.modules[MIGRATION_SPEC.name] = migration
MIGRATION_SPEC.loader.exec_module(migration)
DIGEST = 'sha256:'+'a'*64
REVISION = 'b'*40


class DeploymentTests(unittest.TestCase):
    def test_deploy_protocol_is_exact(self):
        self.assertEqual(deploy.validate(['site', DIGEST, REVISION]), ('site', DIGEST, REVISION))
        for args in (
            [], ['db', DIGEST, REVISION], ['site', 'latest', REVISION],
            ['site', DIGEST+';id', REVISION], ['api', DIGEST, REVISION, 'sh'],
            ['site', DIGEST, '--help'],
        ):
            with self.subTest(args=args), self.assertRaises(deploy.DeploymentError):
                deploy.validate(args)

    def test_operations_lock_is_one_shared_nonblocking_path(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(deploy, 'STATE', Path(tmp)):
            lock_path = Path(tmp)/deploy.OPERATIONS_LOCK_NAME
            with deploy.operations_lock():
                self.assertTrue(lock_path.is_file())
                with self.assertRaises(BlockingIOError):
                    with deploy.operations_lock():
                        self.fail('A second host operation must not wait or acquire the lock.')
            self.assertEqual({path.name for path in Path(tmp).iterdir()}, {deploy.OPERATIONS_LOCK_NAME})

    def test_deploy_uses_the_shared_operations_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, state = Path(tmp)/'config', Path(tmp)/'state'
            (base/'site').mkdir(parents=True)
            (base/'site'/'enabled').touch()

            def docker_response(*args, **kwargs):
                if args[:2] == ('image', 'inspect'):
                    return json.dumps([{'Config': {'Labels': {
                        'org.opencontainers.image.revision': REVISION,
                        'org.opencontainers.image.source': 'https://github.com/VooZ2/terento',
                    }}}])
                return ''

            with patch.object(deploy, 'BASE', base), patch.object(deploy, 'STATE', state), \
                    patch.object(deploy, 'docker', side_effect=docker_response), \
                    patch.object(deploy, 'compose') as compose, \
                    patch.object(deploy, 'healthy_ids', return_value={'site': {'id': 'a'*64}}), \
                    patch.object(deploy, 'run', return_value=''), \
                    patch.object(deploy, 'register') as register:
                deploy.deploy('site', DIGEST, REVISION)

            register.assert_called_once()
            self.assertTrue((state/deploy.OPERATIONS_LOCK_NAME).is_file())
            self.assertFalse((state/'site.lock').exists())
            self.assertTrue((state/'site.json').is_file())
            self.assertTrue(any(call.args[2] == 'up' for call in compose.call_args_list))

    def test_migrate_cannot_enter_while_deploy_holds_the_shared_lock(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(deploy, 'STATE', Path(tmp)):
            args = [
                '--target', '062', '--image', DIGEST, '--revision', REVISION,
                '--expected-migration-062-sha256', 'c'*64,
                '--expected-migrate-py-sha256', 'e'*64,
            ]
            with deploy.operations_lock():
                with self.assertRaises(BlockingIOError):
                    deploy.migrate_only(args, tool=migration)

    def test_deploy_cannot_enter_while_migration_holds_the_shared_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, state = Path(tmp)/'config', Path(tmp)/'state'
            (base/'site').mkdir(parents=True)
            (base/'site'/'enabled').touch()
            with patch.object(deploy, 'BASE', base), patch.object(deploy, 'STATE', state), \
                    patch.object(deploy, 'docker') as docker:
                with deploy.operations_lock():
                    with self.assertRaises(BlockingIOError):
                        deploy.deploy('site', DIGEST, REVISION)
                docker.assert_not_called()

    def test_api_deploy_refuses_candidate_062_until_migration_only_operation_applies_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, state = Path(tmp)/'config', Path(tmp)/'state'
            (base/'api').mkdir(parents=True)
            (base/'api'/'enabled').touch()
            image = deploy.PROJECTS['api']['image']+'@'+DIGEST
            with patch.object(deploy, 'BASE', base), patch.object(deploy, 'STATE', state), \
                    patch.object(deploy, 'docker', return_value=json.dumps([{'Config': {'Labels': {
                        'org.opencontainers.image.revision': REVISION,
                        'org.opencontainers.image.source': 'https://github.com/VooZ2/terento',
                        'io.terento.migration.062.sha256': 'f'*64,
                        'io.terento.migrate.py.sha256': 'e'*64,
                    }}}])), \
                    patch.object(deploy, 'compose') as compose, \
                    patch.object(deploy, 'require_062_already_applied',
                                 side_effect=deploy.DeploymentError('DEPLOY refused: run a separately approved migration-only operation first.')) as schema_gate:
                with self.assertRaisesRegex(deploy.DeploymentError, 'separately approved migration-only'):
                    deploy.deploy('api', DIGEST, REVISION)

            self.assertTrue(any(call.args[2:] == ('config', '--quiet')
                                for call in compose.call_args_list))
            schema_gate.assert_called_once()
            self.assertFalse(any(call.args[2] == 'up' for call in compose.call_args_list))
            self.assertFalse(any('catalog-migrate' in call.args[2:] for call in compose.call_args_list))

    def test_api_deploy_never_runs_a_migration_after_schema_gate_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, state = Path(tmp)/'config', Path(tmp)/'state'
            (base/'api').mkdir(parents=True)
            (base/'api'/'enabled').touch()
            state.mkdir()
            with patch.object(deploy, 'BASE', base), patch.object(deploy, 'STATE', state), \
                    patch.object(deploy, 'docker', return_value=json.dumps([{'Config': {'Labels': {
                        'org.opencontainers.image.revision': REVISION,
                        'org.opencontainers.image.source': 'https://github.com/VooZ2/terento',
                        'io.terento.migration.062.sha256': 'f'*64,
                        'io.terento.migrate.py.sha256': 'e'*64,
                    }}}])), \
                    patch.object(deploy, 'compose') as compose, \
                    patch.object(deploy, 'require_062_already_applied') as schema_gate, \
                    patch.object(deploy, 'healthy_ids', return_value={
                        'api': {'id': 'a'*64}, 'scheduler': {'id': 'b'*64},
                    }), patch.object(deploy, 'run', return_value=''), \
                    patch.object(deploy, 'register'):
                deploy.deploy('api', DIGEST, REVISION)

            schema_gate.assert_called_once()
            compose.assert_any_call('api', deploy.PROJECTS['api']['image']+'@'+DIGEST,
                                    'up', '-d', '--no-deps', '--no-build', '--wait',
                                    '--wait-timeout', '120', 'catalog-api', 'catalog-scheduler')
            self.assertFalse(any('catalog-migrate' in call.args[2:] for call in compose.call_args_list))
            self.assertFalse(any('catalog-db' in call.args[2:] and 'up' in call.args[2:]
                                 for call in compose.call_args_list))

    def test_api_deploy_refuses_legacy_image_without_migration_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)/'config'
            (base/'api').mkdir(parents=True)
            (base/'api'/'enabled').touch()
            with patch.object(deploy, 'BASE', base), patch.object(deploy, 'STATE', Path(tmp)/'state'), \
                    patch.object(deploy, 'compose') as compose, \
                    patch.object(deploy, 'docker', return_value=json.dumps([{'Config': {'Labels': {
                        'org.opencontainers.image.revision': REVISION,
                        'org.opencontainers.image.source': 'https://github.com/VooZ2/terento',
                    }}}])):
                with self.assertRaisesRegex(deploy.DeploymentError, 'migration 062 identity'):
                    deploy.deploy('api', DIGEST, REVISION)
            self.assertEqual(compose.call_args.args[2:], ('config', '--quiet'))
            self.assertFalse(any(call.args[2] == 'up' for call in compose.call_args_list))

    def test_missing_migration_target_refuses_before_lock_or_host_io(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(deploy, 'STATE', Path(tmp)), patch.object(deploy, 'docker') as docker, \
                patch.object(deploy, 'compose') as compose:
            with self.assertRaisesRegex(deploy.DeploymentError, 'explicit --target 062'):
                deploy.dispatch(['migrate'])
            self.assertEqual(list(Path(tmp).iterdir()), [])
            docker.assert_not_called()
            compose.assert_not_called()

    def test_safe_migration_refusal_detail_is_preserved_for_operator(self):
        message = "Candidate image includes migration(s) after target 062: 063_extra.sql. No migration was run."

        class FakeMigrationTool:
            class MigrationError(RuntimeError):
                pass

            @staticmethod
            def parse_arguments(_arguments):
                return None

            @staticmethod
            def run_migration(*_args, **_kwargs):
                raise FakeMigrationTool.MigrationError(message)

        with tempfile.TemporaryDirectory() as tmp, patch.object(deploy, 'STATE', Path(tmp)):
            with self.assertRaisesRegex(deploy.DeploymentError, r"063_extra\.sql") as raised:
                deploy.migrate_only(['--valid'], tool=FakeMigrationTool)
        self.assertIn('063_extra.sql', deploy.operator_failure_message(raised.exception))

    def test_status_does_not_acquire_the_mutation_lock(self):
        missing = lambda service: {
            'project': 'terento-catalog', 'service': service, 'container_id': None,
            'image_repository': None, 'image_digest': None, 'image_immutable': False,
            'revision': None, 'started_at': None, 'state': 'missing',
        }
        with patch.object(deploy, '_container_status', side_effect=missing), \
                patch.object(deploy, 'operations_lock') as lock:
            snapshot = deploy.status()
        self.assertTrue(snapshot['read_only'])
        self.assertEqual(snapshot['database']['status'], 'not_queried')
        lock.assert_not_called()

    def test_missing_activation_runs_nothing(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(deploy, 'BASE', Path(tmp)), patch.object(deploy, 'docker') as docker:
            with self.assertRaises(deploy.DeploymentError):
                deploy.deploy('site', DIGEST, REVISION)
            docker.assert_not_called()

    def test_revision_mismatch_does_not_start_services(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)/'config'
            state = Path(tmp)/'state'
            (base/'site').mkdir(parents=True)
            (base/'site'/'enabled').touch()

            def docker_response(*args, **kwargs):
                if args[:2] == ('image', 'inspect'):
                    return json.dumps([{'Config': {'Labels': {}}}])
                return ''

            with patch.object(deploy, 'BASE', base), patch.object(deploy, 'STATE', state), \
                    patch.object(deploy, 'docker', side_effect=docker_response), \
                    patch.object(deploy, 'compose') as compose:
                with self.assertRaises(deploy.DeploymentError):
                    deploy.deploy('site', DIGEST, REVISION)
            self.assertEqual(compose.call_count, 1)
            self.assertEqual(compose.call_args.args[2:], ('config', '--quiet'))

    def test_health_failure_restores_previous_image_without_deleting_volumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)/'config'
            state = Path(tmp)/'state'
            (base/'site').mkdir(parents=True)
            (base/'site'/'enabled').touch()
            state.mkdir()
            old = {
                'image': deploy.PROJECTS['site']['image']+'@sha256:'+'c'*64,
                'commit': 'd'*40,
            }
            state_path = state/'site.json'
            state_path.write_text(json.dumps(old))

            def docker_response(*args, **kwargs):
                if args[:2] == ('image', 'inspect'):
                    return json.dumps([{'Config': {'Labels': {
                        'org.opencontainers.image.revision': REVISION,
                        'org.opencontainers.image.source': 'https://github.com/VooZ2/terento',
                    }}}])
                return ''

            with patch.object(deploy, 'BASE', base), patch.object(deploy, 'STATE', state), \
                    patch.object(deploy, 'docker', side_effect=docker_response), \
                    patch.object(deploy, 'compose') as compose, \
                    patch.object(deploy, 'healthy_ids', side_effect=[deploy.DeploymentError('unhealthy'), {}]), \
                    patch.object(deploy, 'register'):
                with self.assertRaises(deploy.DeploymentError):
                    deploy.deploy('site', DIGEST, REVISION)
            self.assertEqual(compose.call_args.args[1], old['image'])
            for call in compose.call_args_list:
                self.assertNotIn('down', call.args)
                self.assertNotIn('-v', call.args)
            self.assertEqual(json.loads(state_path.read_text()), old)


class StatusTests(unittest.TestCase):
    def test_status_is_read_only_and_redacts_credentials(self):
        api_id, scheduler_id, db_id = 'a'*64, 'b'*64, 'c'*64
        revision = 'd'*40
        secret = 'do-not-print-this-database-password'

        def container(container_id, service, image, image_revision=None):
            labels = {
                'com.docker.compose.project': 'terento-catalog',
                'com.docker.compose.service': service,
            }
            if image_revision:
                labels['org.opencontainers.image.revision'] = image_revision
            return json.dumps([{
                'Id': container_id,
                'Config': {
                    'Image': image,
                    'Labels': labels,
                    'Env': [
                        'POSTGRES_USER=terento_reader', 'POSTGRES_DB=terento',
                        'POSTGRES_PASSWORD='+secret,
                    ],
                },
                'State': {'Status': 'running', 'StartedAt': '2026-09-23T08:09:10.123456789Z'},
            }])

        inspected_containers = {
            api_id: container(api_id, 'catalog-api', deploy.PROJECTS['api']['image']+'@'+DIGEST, revision),
            scheduler_id: container(scheduler_id, 'catalog-scheduler', deploy.PROJECTS['api']['image']+'@'+DIGEST, revision),
            db_id: container(db_id, 'catalog-db', 'docker.io/library/postgres@sha256:'+'e'*64),
        }
        database_result = {
            'database': 'terento', 'schema': 'public', 'postgresql_version': '16.10',
            'highest_migration': '061', 'migration_062_applied': False,
            'server_time': '2026-09-23 11:09:10+03', 'timezone': 'Europe/Vilnius',
        }
        image_ref = deploy.PROJECTS['api']['image']+'@'+DIGEST
        image_result = [{
            'RepoDigests': [image_ref],
            'Config': {'Labels': {
                'org.opencontainers.image.source': 'https://github.com/VooZ2/terento',
                'org.opencontainers.image.revision': revision,
                'io.terento.migration.062.sha256': 'f'*64,
            }},
        }]
        docker_calls = []

        def docker_call(*args, **kwargs):
            docker_calls.append((args, kwargs))
            if args[:3] == ('ps', '-a', '-q'):
                self.assertEqual(args[3], '--filter')
                self.assertEqual(args[4], 'label=com.docker.compose.project=terento-catalog')
                self.assertEqual(args[5], '--filter')
                service = args[6].rsplit('=', 1)[1]
                return {
                    'catalog-api': api_id,
                    'catalog-scheduler': scheduler_id,
                    'catalog-db': db_id,
                }[service]+'\n'
            if args[:2] == ('inspect', '--type=container'):
                return inspected_containers[args[2]]
            if args[:2] == ('image', 'inspect'):
                return json.dumps(image_result)
            if args[:3] == ('exec', '--user', 'postgres'):
                return json.dumps(database_result)
            self.fail('Unexpected Docker operation from status: '+repr(args))

        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)/'state'
            state.mkdir()
            state_record = state/'api.json'
            state_record.write_text('{"image":"existing"}')
            registry = Path(tmp)/'ops-containers.json'
            registry.write_text('{"api":"existing"}')
            state_before, registry_before = state_record.read_bytes(), registry.read_bytes()
            state_entries_before = {path.name for path in state.iterdir()}
            candidate = {
                'digest': DIGEST, 'revision': revision,
                'expected_migration_062_sha256': 'f'*64,
            }
            with patch.object(deploy, 'STATE', state), patch.object(deploy, 'REGISTRY', registry), \
                    patch.object(deploy, 'compose') as compose, \
                    patch.object(deploy, 'docker', side_effect=docker_call), \
                    patch.object(deploy, 'register') as register, \
                    patch.object(deploy, 'atomic_json') as atomic_json, \
                    patch.object(deploy, 'deploy') as deploy_call, \
                    patch.object(deploy, 'healthy_ids') as healthy_ids:
                result = deploy.status(candidate)
                register.assert_not_called()
                atomic_json.assert_not_called()
                deploy_call.assert_not_called()
                healthy_ids.assert_not_called()
                compose.assert_not_called()

            self.assertEqual(state_record.read_bytes(), state_before)
            self.assertEqual(registry.read_bytes(), registry_before)
            self.assertEqual({path.name for path in state.iterdir()}, state_entries_before)
            for args, _kwargs in docker_calls:
                self.assertIn(args[0], ('ps', 'inspect', 'exec', 'image'))
                if args[0] == 'ps':
                    self.assertEqual(args[1:3], ('-a', '-q'))
                    self.assertIn('label=com.docker.compose.project=terento-catalog', args)
                    self.assertTrue(any(arg.startswith('label=com.docker.compose.service=') for arg in args))
                if args[0] == 'image':
                    self.assertEqual(args[:2], ('image', 'inspect'))
                    self.assertEqual(args[2], image_ref)
                if args[0] == 'exec':
                    self.assertEqual(args[-1], deploy.STATUS_SQL)
                    self.assertIn('BEGIN TRANSACTION READ ONLY', args[-1])
                    self.assertIn('ROLLBACK', args[-1])
                    self.assertNotIn('terento-catalog-migrate', args)
            self.assertEqual(result['operation'], 'status')
            self.assertTrue(result['read_only'])
            self.assertEqual(
                result['services']['catalog-api']['image_repository'],
                'ghcr.io/vooz2/terento-catalog',
            )
            self.assertEqual(result['services']['catalog-api']['image_digest'], DIGEST)
            self.assertEqual(result['services']['catalog-api']['revision'], revision)
            self.assertEqual(result['services']['catalog-scheduler']['state'], 'running')
            self.assertEqual(
                result['services']['catalog-db']['image_repository'],
                'docker.io/library/postgres',
            )
            self.assertEqual(result['services']['catalog-db']['image_digest'], 'sha256:'+'e'*64)
            self.assertEqual(result['database']['highest_migration'], '061')
            self.assertFalse(result['database']['migration_062_applied'])
            self.assertEqual(result['database']['server_time'], database_result['server_time'])
            self.assertEqual(result['database']['timezone'], 'Europe/Vilnius')
            self.assertEqual(result['candidate_artifact']['status'], 'verified')
            self.assertEqual(result['candidate_artifact']['verified_artifact'], {
                'image': image_ref,
                'source': 'https://github.com/VooZ2/terento',
                'revision': revision,
                'migration_062_sha256': 'f'*64,
            })
            self.assertNotIn(secret, json.dumps(result))

    def test_status_candidate_arguments_are_validated(self):
        expected = {
            'digest': DIGEST, 'revision': REVISION,
            'expected_migration_062_sha256': 'f'*64,
        }
        self.assertEqual(deploy.validate_status([
            '--candidate-digest', DIGEST, '--candidate-revision', REVISION,
            '--expected-migration-062-sha256', 'f'*64,
        ]), expected)
        self.assertIsNone(deploy.validate_status([]))
        for args in (
            ['--candidate-digest', DIGEST], ['--candidate-revision', REVISION],
            ['--candidate-digest', DIGEST, '--candidate-revision', REVISION,
             '--expected-migration-062-sha256', 'bad'],
            ['--expected-migration-062-sha256', 'f'*64],
            ['--candidate-digest', DIGEST, '--candidate-revision', REVISION,
             '--candidate-revision', REVISION],
        ):
            with self.subTest(args=args), self.assertRaises(deploy.DeploymentError):
                deploy.validate_status(args)

    def test_candidate_image_labels_are_inspected_without_pull_or_run(self):
        image = deploy.PROJECTS['api']['image']+'@'+DIGEST
        expected_sha = 'f'*64
        image_json = json.dumps([{
            'RepoDigests': [image],
            'Config': {'Labels': {
                'org.opencontainers.image.source': 'https://github.com/VooZ2/terento',
                'org.opencontainers.image.revision': REVISION,
                'io.terento.migration.062.sha256': expected_sha,
            }},
        }])
        with patch.object(deploy, 'docker', return_value=image_json) as docker:
            result = deploy.inspect_candidate({
                'digest': DIGEST, 'revision': REVISION,
                'expected_migration_062_sha256': expected_sha,
            })
        docker.assert_called_once_with('image', 'inspect', image, timeout=30)
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['verified_artifact']['migration_062_sha256'], expected_sha)
        for args, _kwargs in docker.call_args_list:
            self.assertEqual(args[:2], ('image', 'inspect'))
            self.assertNotIn('pull', args)
            self.assertNotIn('run', args)

    def test_expected_sha_mismatch_is_rejected(self):
        image = deploy.PROJECTS['api']['image']+'@'+DIGEST
        image_json = json.dumps([{
            'RepoDigests': [image],
            'Config': {'Labels': {
                'org.opencontainers.image.source': 'https://github.com/VooZ2/terento',
                'org.opencontainers.image.revision': REVISION,
                'io.terento.migration.062.sha256': 'e'*64,
            }},
        }])
        with patch.object(deploy, 'docker', return_value=image_json):
            result = deploy.inspect_candidate({
                'digest': DIGEST, 'revision': REVISION,
                'expected_migration_062_sha256': 'f'*64,
            })
        self.assertEqual(result['status'], 'expected_sha_mismatch')
        self.assertNotIn('verified_artifact', result)
        self.assertEqual(result['observed_migration_062_sha256'], 'e'*64)
        self.assertEqual(deploy.status_exit_code({'candidate_artifact': result}), 1)

    def test_source_and_revision_labels_must_match(self):
        image = deploy.PROJECTS['api']['image']+'@'+DIGEST
        for key, value, expected in (
            ('org.opencontainers.image.source', 'https://example.invalid/other', 'source_mismatch'),
            ('org.opencontainers.image.revision', 'e'*40, 'revision_mismatch'),
        ):
            labels = {
                'org.opencontainers.image.source': 'https://github.com/VooZ2/terento',
                'org.opencontainers.image.revision': REVISION,
                'io.terento.migration.062.sha256': 'f'*64,
            }
            labels[key] = value
            image_json = json.dumps([{'RepoDigests': [image], 'Config': {'Labels': labels}}])
            with self.subTest(key=key), patch.object(deploy, 'docker', return_value=image_json):
                result = deploy.inspect_candidate({'digest': DIGEST, 'revision': REVISION})
            self.assertEqual(result['status'], expected)
            self.assertNotIn('verified_artifact', result)
            self.assertEqual(deploy.status_exit_code({'candidate_artifact': result}), 1)

    def test_missing_migration_label_is_not_verified(self):
        image = deploy.PROJECTS['api']['image']+'@'+DIGEST
        image_json = json.dumps([{
            'RepoDigests': [image],
            'Config': {'Labels': {
                'org.opencontainers.image.source': 'https://github.com/VooZ2/terento',
                'org.opencontainers.image.revision': REVISION,
            }},
        }])
        with patch.object(deploy, 'docker', return_value=image_json):
            result = deploy.inspect_candidate({'digest': DIGEST, 'revision': REVISION})
        self.assertEqual(result['status'], 'missing_migration_062_label')
        self.assertNotIn('verified_artifact', result)
        self.assertEqual(deploy.status_exit_code({'candidate_artifact': result}), 1)

    def test_uncached_image_is_reported_without_pull_or_run(self):
        image = deploy.PROJECTS['api']['image']+'@'+DIGEST
        missing = subprocess.CalledProcessError(
            1, ['/usr/bin/docker', 'image', 'inspect', image],
            stderr='Error response from daemon: No such image: '+image,
        )
        with patch.object(deploy, 'docker', side_effect=missing) as docker:
            result = deploy.inspect_candidate({'digest': DIGEST, 'revision': REVISION})
        docker.assert_called_once_with('image', 'inspect', image, timeout=30)
        self.assertEqual(result['status'], 'not_cached')
        self.assertEqual(deploy.status_exit_code({'candidate_artifact': result}), 0)
        args = docker.call_args.args
        self.assertEqual(args[:2], ('image', 'inspect'))
        self.assertNotIn('pull', args)
        self.assertNotIn('run', args)


if __name__ == '__main__':
    unittest.main()
