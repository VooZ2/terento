#!/usr/bin/env python3
"""Fail packaging if test-only code, flags or fixtures enter the Release app."""
import argparse
from pathlib import Path
import re
import subprocess

FORBIDDEN_FLAGS = r'(?:DEBUG|TERENTO_TESTING|TERENTO_NATIVE_TEST_OPEN|TERENTO_PREFIX_SWIFT_DRIVER|TERENTO_PRODUCTION_CLEANUP_TEST|TERENTO_FAULT_INJECTION)'
FORBIDDEN_SYMBOLS = ('fake_open', 'fake_send', 'fake_delete', 'terento_prefix_test_',
                     'terento_cleanup_forbidden_calls', 'setDiagnosticTestIdentity', 'NativeMutationAuthorizationTests',
                     'LocalManagedUpdateSimulationTests')


def check_build_text(text):
    if re.search(r'(?:-D\s*|\b)' + FORBIDDEN_FLAGS + r'(?:\b|=)', text):
        raise ValueError('Release build enables a test/debug compilation condition')
    if re.search(r'(?:^|[\s\"\'@=/])(?:Tests|Fixtures|TerentoWriteTest|TerentoInterruptionTest)/' , text):
        raise ValueError('Release compile/link inputs contain a test source or fixture')


def check_bundle(app, root):
    resources = app / 'Contents/Resources'
    for path in app.rglob('*'):
        if not path.is_file():
            continue
        name = path.name.lower()
        if (name.startswith(('terento-write-test', 'test-manifest', 'synthetic-', 'fixture-'))
                or name == 'manifest.json' or path.suffix.lower() == '.img'
                or any(part.lower() in ('tests', 'fixtures', 'test-results') for part in path.relative_to(app).parts)):
            raise ValueError('Release bundle contains test/device-state data: ' + str(path.relative_to(app)))
    catalogs = list(resources.rglob('catalog.json'))
    expected = root / 'app/TerentoCore/Sources/TerentoPoC/Resources/Maps/catalog.json'
    if len(catalogs) != 1 or catalogs[0].read_bytes() != expected.read_bytes():
        raise ValueError('Release catalog must equal the single canonical production catalog')


def check_symbols(symbols):
    if any(symbol in symbols for symbol in FORBIDDEN_SYMBOLS):
        raise ValueError('Release executable contains a test-only hook')


def check_private_paths(app, roots):
    markers = set()
    for root in roots:
        value = str(root.resolve())
        markers.add(value.encode())
        if value.startswith('/private/tmp/'):
            markers.add(value.removeprefix('/private').encode())
    for path in app.rglob('*'):
        if path.is_file() and any(marker in path.read_bytes() for marker in markers):
            raise ValueError('Release bundle retains a private source/build path: ' + str(path.relative_to(app)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', required=True, type=Path)
    parser.add_argument('--build-log', required=True, type=Path)
    parser.add_argument('--derived-data', required=True, type=Path)
    parser.add_argument('--stripped', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    check_build_text(args.build_log.read_text())
    response_files = [p for p in args.derived_data.rglob('*.resp') if '/Release/' in str(p)]
    if not response_files:
        raise ValueError('Fresh Release compiler response files are required')
    for path in response_files + list(args.derived_data.rglob('*.SwiftFileList')) + list(args.derived_data.rglob('*.LinkFileList')):
        if '/Release/' in str(path):
            check_build_text(path.read_text())
    check_bundle(args.app, root)
    symbols = subprocess.check_output(['nm', '-a', str(args.app / 'Contents/MacOS/Terento')], text=True)
    check_symbols(symbols)
    if args.stripped:
        check_private_paths(args.app, [root, args.derived_data])
    print('PASS: Release compile inputs, flags, catalog, resources and test-hook isolation')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit('Release test-isolation gate failed: ' + str(error))
