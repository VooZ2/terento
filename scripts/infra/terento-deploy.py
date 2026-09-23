#!/usr/bin/python3 -I
"""CANONICAL TRACKED SOURCE for the root-owned Terento deployment helper.

The owner-run bootstrap must install this reviewed file as
/usr/local/sbin/terento-deploy. Do not maintain a second helper copy.
"""
from contextlib import contextmanager
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import traceback

PROJECTS = {
 'site': {'image': 'ghcr.io/vooz2/terento-site', 'name': 'terento-site', 'services': ['site'], 'roles': {'site': 'site'}},
 'api': {'image': 'ghcr.io/vooz2/terento-catalog', 'name': 'terento-catalog', 'services': ['catalog-api', 'catalog-scheduler'], 'roles': {'api': 'catalog-api', 'scheduler': 'catalog-scheduler'}},
}
BASE = Path('/etc/terento/deployment')
STATE = Path('/var/lib/terento/deployment')
REGISTRY = Path('/etc/terento/ops-containers.json')
OPERATIONS_LOCK_NAME = 'operations.lock'

class DeploymentError(Exception):
    pass

def validate(args):
    if len(args) != 3 or args[0] not in PROJECTS:
        raise DeploymentError('Expected project, image digest and commit.')
    project, digest, commit = args
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        raise DeploymentError('Invalid image digest.')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise DeploymentError('Invalid commit.')
    return project, digest, commit

def atomic_json(path, value):
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def run(args, image=None, timeout=240):
    env = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': '/root'}
    if image:
        env['TERENTO_IMAGE'] = image
    return subprocess.run(args, cwd='/', env=env, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, timeout=timeout, check=True).stdout

def docker(*args, image=None, timeout=240):
    return run(['/usr/bin/docker', '--host=unix:///var/run/docker.sock', *args], image, timeout)

def compose(project, image, *args):
    spec = PROJECTS[project]
    return docker('compose', '--project-name', spec['name'], '--project-directory', str(BASE/project),
                  '--env-file', str(BASE/project/'release.env'), '-f', str(BASE/project/'compose.json'),
                  *args, image=image)

def healthy_ids(project, image):
    records = {}
    spec = PROJECTS[project]
    for role, service in spec['roles'].items():
        ids = compose(project, image, 'ps', '-q', service).split()
        if len(ids) != 1:
            raise DeploymentError('Expected one running service: '+service)
        data = json.loads(docker('inspect', '--type=container', ids[0]))[0]
        labels = data['Config'].get('Labels') or {}
        if labels.get('com.docker.compose.project') != spec['name'] or labels.get('com.docker.compose.service') != service:
            raise DeploymentError('Unexpected service identity.')
        if data['Config']['Image'] != image or not data['State']['Running']:
            raise DeploymentError('Unexpected running image.')
        if service != 'catalog-scheduler' and data['State'].get('Health', {}).get('Status') != 'healthy':
            raise DeploymentError('Service failed its health check.')
        records[role] = {'id': data['Id'], 'project': spec['name'], 'service': service}
    if project == 'api':
        ids = compose(project, image, 'ps', '-q', 'catalog-db').split()
        if len(ids) != 1 or json.loads(docker('inspect', ids[0]))[0]['State'].get('Health', {}).get('Status') != 'healthy':
            raise DeploymentError('Database is not healthy.')
    return records

def register(records, remove=()):
    with (STATE/'registry.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = json.loads(REGISTRY.read_text())
        for role in remove:
            state.pop(role, None)
        state.update(records)
        atomic_json(REGISTRY, state)

@contextmanager
def operations_lock():
    """Acquire the shared, non-blocking host operations lock for mutating operations."""
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE/OPERATIONS_LOCK_NAME).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield

STATUS_SQL = """
BEGIN TRANSACTION READ ONLY;
SELECT json_build_object(
  'database', current_database(),
  'schema', current_schema(),
  'postgresql_version', current_setting('server_version'),
  'highest_migration', (SELECT max(version)::text FROM schema_migrations),
  'migration_062_applied', EXISTS (SELECT 1 FROM schema_migrations WHERE version = '062'),
  'server_time', clock_timestamp()::text,
  'timezone', current_setting('TimeZone')
)::text;
ROLLBACK;
"""

def require_062_already_applied(image, digest, revision, labels):
    """Prove the pinned API image and DB schema match; never migrate in deploy."""
    migration_sha = labels.get('io.terento.migration.062.sha256')
    runner_sha = labels.get('io.terento.migrate.py.sha256')
    if not isinstance(migration_sha, str) or not re.fullmatch(r'[0-9a-f]{64}', migration_sha):
        raise DeploymentError('API candidate must carry a valid migration 062 identity; deployment is refused.')
    if not isinstance(runner_sha, str) or not re.fullmatch(r'[0-9a-f]{64}', runner_sha):
        raise DeploymentError('API candidate must carry a valid migration runner identity; deployment is refused.')
    tool = migration_tool()
    arguments = [
        '--target', '062', '--image', digest, '--revision', revision,
        '--expected-migration-062-sha256', migration_sha,
        '--expected-migrate-py-sha256', runner_sha,
    ]
    try:
        return tool.verify_deploy_schema(arguments, docker=docker, compose=compose)
    except tool.MigrationError as error:
        raise DeploymentError(str(error)) from None

def validate_status(args):
    """Parse the strictly optional candidate receipt fields for status."""
    values = {}
    patterns = {
        '--candidate-digest': r'sha256:[0-9a-f]{64}',
        '--candidate-revision': r'[0-9a-f]{40}',
        '--expected-migration-062-sha256': r'[0-9a-f]{64}',
    }
    index = 0
    while index < len(args):
        option = args[index]
        if option not in patterns or option in values or index + 1 >= len(args):
            raise DeploymentError('Invalid status arguments.')
        value = args[index + 1]
        if not re.fullmatch(patterns[option], value):
            raise DeploymentError('Invalid status arguments.')
        values[option] = value
        index += 2
    if ('--candidate-digest' in values) != ('--candidate-revision' in values):
        raise DeploymentError('Candidate digest and revision must be supplied together.')
    if '--expected-migration-062-sha256' in values and '--candidate-digest' not in values:
        raise DeploymentError('Migration checksum requires a candidate digest and revision.')
    if not values:
        return None
    return {
        'digest': values.get('--candidate-digest'),
        'revision': values.get('--candidate-revision'),
        'expected_migration_062_sha256': values.get('--expected-migration-062-sha256'),
    }

def inspect_candidate(candidate):
    """Validate a locally cached immutable API image without pulling or running it."""
    digest = candidate.get('digest', '')
    revision = candidate.get('revision', '')
    expected_sha = candidate.get('expected_migration_062_sha256')
    if (not re.fullmatch(r'sha256:[0-9a-f]{64}', digest)
            or not re.fullmatch(r'[0-9a-f]{40}', revision)
            or (expected_sha is not None and not re.fullmatch(r'[0-9a-f]{64}', expected_sha))):
        raise DeploymentError('Invalid candidate image identity.')
    image = PROJECTS['api']['image'] + '@' + digest
    request = {'digest': digest, 'expected_revision': revision}
    if expected_sha is not None:
        request['expected_migration_062_sha256'] = expected_sha
    try:
        raw = docker('image', 'inspect', image, timeout=30)
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or '').lower()
        missing = 'no such image' in detail or 'no such object' in detail
        return {'status': 'not_cached' if missing else 'inspection_unavailable', 'request': request}
    except Exception:
        return {'status': 'inspection_unavailable', 'request': request}
    try:
        inspected = json.loads(raw)
        if not isinstance(inspected, list) or len(inspected) != 1 or not isinstance(inspected[0], dict):
            return {'status': 'invalid_inspect_result', 'request': request}
        image_data = inspected[0]
        if image not in (image_data.get('RepoDigests') or []):
            return {'status': 'digest_mismatch', 'request': request}
        labels = image_data.get('Config', {}).get('Labels') or {}
        source = labels.get('org.opencontainers.image.source')
        if source != 'https://github.com/VooZ2/terento':
            return {'status': 'source_mismatch', 'request': request}
        image_revision = labels.get('org.opencontainers.image.revision')
        if not isinstance(image_revision, str) or image_revision != revision:
            return {'status': 'revision_mismatch', 'request': request}
        image_sha = labels.get('io.terento.migration.062.sha256')
        if not isinstance(image_sha, str) or not re.fullmatch(r'[0-9a-f]{64}', image_sha):
            return {'status': 'missing_migration_062_label', 'request': request}
        if expected_sha is not None and image_sha != expected_sha:
            return {
                'status': 'expected_sha_mismatch',
                'request': request,
                'observed_migration_062_sha256': image_sha,
            }
        return {
            'status': 'verified',
            'request': request,
            'verified_artifact': {
                'image': image,
                'source': source,
                'revision': image_revision,
                'migration_062_sha256': image_sha,
            },
        }
    except Exception:
        return {'status': 'invalid_inspect_result', 'request': request}

def status_exit_code(snapshot):
    """Reject present-but-unverified candidates while treating an uncached image as informational."""
    artifact = snapshot.get('candidate_artifact')
    if not artifact:
        return 0
    return 1 if artifact.get('status') not in ('verified', 'not_cached') else 0

def _image_identity(reference, project, service):
    """Return only a validated repository/digest pair; never echo arbitrary references."""
    if project == 'api' and service in PROJECTS['api']['roles'].values():
        repository = PROJECTS['api']['image']
        prefix = repository + '@sha256:'
        if not reference.startswith(prefix):
            return None
        digest = reference[len(prefix):]
        return (repository, 'sha256:'+digest) if re.fullmatch(r'[0-9a-f]{64}', digest) else None
    match = re.fullmatch(
        r'([a-z0-9][a-z0-9.-]*(?::[0-9]+)?(?:/[a-z0-9][a-z0-9._-]*)*)@sha256:([0-9a-f]{64})',
        reference,
    )
    return (match.group(1), 'sha256:'+match.group(2)) if match else None

def _container_status(service):
    """Read one compose container without calling health endpoints or mutating it."""
    empty = {
        'project': PROJECTS['api']['name'],
        'service': service,
        'container_id': None,
        'image_repository': None,
        'image_digest': None,
        'image_immutable': False,
        'revision': None,
        'started_at': None,
        'state': 'unavailable',
    }
    try:
        ids = docker(
            'ps', '-a', '-q',
            '--filter', 'label=com.docker.compose.project='+PROJECTS['api']['name'],
            '--filter', 'label=com.docker.compose.service='+service,
        ).split()
        if not ids:
            return {**empty, 'state': 'missing'}
        if len(ids) != 1 or not re.fullmatch(r'[0-9a-f]{12,64}', ids[0]):
            return {**empty, 'state': 'ambiguous'}
        data = json.loads(docker('inspect', '--type=container', ids[0]))[0]
        labels = data.get('Config', {}).get('Labels') or {}
        if (labels.get('com.docker.compose.project') != PROJECTS['api']['name']
                or labels.get('com.docker.compose.service') != service):
            return {**empty, 'state': 'identity_mismatch'}
        container_id = data.get('Id', '')
        state = data.get('State') or {}
        status = state.get('Status')
        allowed_states = {'created', 'restarting', 'running', 'removing', 'paused', 'exited', 'dead'}
        status = status if status in allowed_states else 'unknown'
        started_at = state.get('StartedAt')
        if not isinstance(started_at, str) or not re.fullmatch(
                r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z', started_at):
            started_at = None
        revision = labels.get('org.opencontainers.image.revision')
        if not isinstance(revision, str) or not re.fullmatch(r'[0-9a-f]{40}', revision):
            revision = None
        image_identity = _image_identity(data.get('Config', {}).get('Image', ''), 'api', service)
        return {
            'project': PROJECTS['api']['name'],
            'service': service,
            'container_id': container_id if re.fullmatch(r'[0-9a-f]{64}', container_id) else None,
            'image_repository': image_identity[0] if image_identity else None,
            'image_digest': image_identity[1] if image_identity else None,
            'image_immutable': image_identity is not None,
            'revision': revision if service in PROJECTS['api']['roles'].values() else None,
            'started_at': started_at,
            'state': status,
        }
    except Exception:
        # Do not surface Docker stderr, inspect data, or environment values in status output.
        return empty

def status(candidate=None):
    """Return a credential-minimised, read-only snapshot of the API deployment."""
    services = {
        service: _container_status(service)
        for service in ('catalog-api', 'catalog-scheduler', 'catalog-db')
    }
    db_container = services['catalog-db']
    database = {
        'status': 'not_queried',
        'database': None,
        'schema': None,
        'postgresql_version': None,
        'highest_migration': None,
        'migration_062_applied': None,
        'server_time': None,
        'timezone': None,
    }
    if db_container['state'] == 'running' and db_container['container_id']:
        try:
            # POSTGRES_USER and POSTGRES_DB are expanded inside the container and are never
            # returned or printed. The fixed SQL is enclosed in an explicit read-only tx.
            raw = docker(
                'exec', '--user', 'postgres', db_container['container_id'],
                'sh', '-c',
                'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$1"',
                'terento-status', STATUS_SQL,
                timeout=30,
            )
            result = json.loads(raw)
            required = set(database) - {'status'}
            if not isinstance(result, dict) or not required.issubset(result):
                raise ValueError('Unexpected database status result.')
            database.update({key: result[key] for key in required})
            database['status'] = 'available'
        except Exception:
            # Error strings can contain connection details; expose only the status enum.
            database['status'] = 'unavailable'
    snapshot = {
        'operation': 'status',
        'read_only': True,
        'services': services,
        'database': database,
        'candidate_artifact': inspect_candidate(candidate) if candidate else None,
    }
    return snapshot

def migration_tool():
    """Load the adjacent, root-owned migration-only implementation."""
    module_path = Path(__file__).resolve().with_name('terento-deploy-migration.py')
    spec = importlib.util.spec_from_file_location('_terento_deploy_migration', module_path)
    if spec is None or spec.loader is None:
        raise DeploymentError('Migration-only tooling is unavailable.')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def migrate_only(arguments, *, tool=None):
    """Run the separately targeted migration while sharing the deploy lock."""
    migration = tool or migration_tool()
    try:
        migration.parse_arguments(arguments)
    except migration.MigrationError as error:
        raise DeploymentError(str(error)) from None
    with operations_lock():
        try:
            return migration.run_migration(arguments, docker=docker, compose=compose)
        except migration.MigrationError as error:
            # MigrationError messages are constructed from fixed checks and
            # validated artifact filenames; they are safe to show to operators.
            raise DeploymentError(str(error)) from None

def status_command(arguments):
    candidate = validate_status(arguments)
    snapshot = status(candidate)
    print(json.dumps(snapshot, sort_keys=True))
    return status_exit_code(snapshot)

def dispatch(arguments):
    """Dispatch root CLI and the API SSH role without changing deploy semantics."""
    if arguments[:1] == ['status']:
        return status_command(arguments[1:])
    if arguments[:1] == ['migrate']:
        migrate_only(arguments[1:])
        return 0
    if arguments[:2] == ['api', 'status']:
        return status_command(arguments[2:])
    if arguments[:2] == ['api', 'migrate']:
        migrate_only(arguments[2:])
        return 0
    deploy(*validate(arguments))
    return 0

def operator_failure_message(error):
    """Return only fixed/sanitized operation detail suitable for the terminal."""
    if isinstance(error, DeploymentError):
        return 'Terento production operation refused: '+str(error)
    return 'Terento production operation failed; inspect root-owned server diagnostics. No service or volume rollback was requested.'

def deploy(project, digest, commit):
    spec = PROJECTS[project]
    image = spec['image']+'@'+digest
    # Owner activates only after root-owned config/secrets and rehearsal are ready.
    if not (BASE/project/'enabled').is_file():
        raise DeploymentError('This deployment target is not activated.')
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with operations_lock():
        state_path = STATE/(project+'.json')
        old = json.loads(state_path.read_text()) if state_path.exists() else None
        if old and not re.fullmatch(re.escape(spec['image'])+r'@sha256:[0-9a-f]{64}', old.get('image', '')):
            raise DeploymentError('Invalid previous deployment record.')
        compose(project, image, 'config', '--quiet')
        docker('pull', image, timeout=600)
        labels = json.loads(docker('image', 'inspect', image))[0]['Config'].get('Labels') or {}
        if labels.get('org.opencontainers.image.revision') != commit:
            raise DeploymentError('Image revision does not match requested commit.')
        if labels.get('org.opencontainers.image.source') != 'https://github.com/VooZ2/terento':
            raise DeploymentError('Image source label does not match Terento.')
        # Image labels are consistency checks, not cryptographic provenance.
        # Registry write access is a trusted release authority.
        if project == 'api':
            require_062_already_applied(image, digest, commit, labels)
        try:
            compose(project, image, 'up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout', '120', *spec['services'])
            records = healthy_ids(project, image)
            # Root-owned executable, never a script provided over SSH.
            run([str(BASE/project/'verify-release'), commit], image, timeout=120)
            register(records)
            atomic_json(state_path, {'image': image, 'commit': commit, 'previous': ({'image': old['image'], 'commit': old['commit']} if old else None)})
        except Exception:
            register({}, remove=spec['roles'])
            if old:
                compose(project, old['image'], 'up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout', '120', *spec['services'])
                register(healthy_ids(project, old['image']))
            else:
                compose(project, image, 'stop', *spec['services'])
            # Never delete volumes or attempt an automatic schema downgrade.
            raise
        print('DEPLOYMENT_PASS '+project+' '+commit)

if __name__ == '__main__':
    try:
        raise SystemExit(dispatch(sys.argv[1:]))
    except (DeploymentError, RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        try:
            fd = os.open('/var/log/terento-deploy.log', os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'a') as log:
                log.write(traceback.format_exc())
                if isinstance(error, subprocess.CalledProcessError):
                    log.write((error.stderr or '')[-65536:])
        except OSError:
            pass
        print(operator_failure_message(error), file=sys.stderr)
        raise SystemExit(1)
