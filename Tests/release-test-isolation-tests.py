import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('isolation', ROOT / 'Packaging/verify-release-test-isolation.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class ReleaseIsolationTests(unittest.TestCase):
    def test_effective_flags_and_response_inputs(self):
        guard.check_build_text('clang -DNDEBUG=1 -DTERENTO_BUNDLED_MTP=1 /repo/Sources/Core.swift')
        for text in ('swiftc -D DEBUG', 'clang -DTERENTO_NATIVE_TEST_OPEN=fake_open',
                     'SWIFT_ACTIVE_COMPILATION_CONDITIONS = TERENTO_TESTING',
                     'clang -D TERENTO_FAULT_INJECTION=1',
                     '/repo/app/TerentoCore/Tests/NativePrefixSessionTests.c',
                     '/repo/Sources/TerentoWriteTest/main.swift', 'swiftc Tests/Fixture.swift',
                     'clang -include Tests/fault.h Sources/Core.c', '@Tests/test-resp'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                guard.check_build_text(text)

    def test_bundle_catalog_and_fixture_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / 'Terento.app'
            resources = app / 'Contents/Resources'
            resources.mkdir(parents=True)
            source = root / 'app/TerentoCore/Sources/TerentoPoC/Resources/Maps/catalog.json'
            source.parent.mkdir(parents=True)
            source.write_text('{"provider":"canonical"}')
            catalog = resources / 'catalog.json'
            catalog.write_bytes(source.read_bytes())
            guard.check_bundle(app, root)
            for name in ('terento-write-test.txt', 'manifest.json', 'synthetic-provider.json', 'Fixtures/map.img'):
                fixture = resources / name
                fixture.parent.mkdir(parents=True, exist_ok=True)
                fixture.write_text('local test evidence')
                with self.subTest(name=name), self.assertRaises(ValueError):
                    guard.check_bundle(app, root)
                fixture.unlink()
            catalog.write_text('{"provider":"synthetic"}')
            with self.assertRaises(ValueError):
                guard.check_bundle(app, root)
            catalog.write_bytes(source.read_bytes())
            duplicate = resources / 'nested/catalog.json'
            duplicate.parent.mkdir()
            duplicate.write_bytes(source.read_bytes())
            with self.assertRaises(ValueError):
                guard.check_bundle(app, root)

    def test_private_build_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / 'Terento.app'
            app.mkdir()
            binary = app / 'Terento'
            binary.write_bytes(b'normal executable content')
            guard.check_private_paths(app, [Path('/private/tmp/private-build')])
            binary.write_bytes(b'prefix /tmp/private-build/Objects/Core.o')
            with self.assertRaises(ValueError):
                guard.check_private_paths(app, [Path('/private/tmp/private-build')])

    def test_linked_hooks(self):
        guard.check_symbols('_terento_mtp_install_map_file_authorized\n_NativeMutationOperation')
        for symbol in guard.FORBIDDEN_SYMBOLS:
            with self.subTest(symbol=symbol), self.assertRaises(ValueError):
                guard.check_symbols('_' + symbol)

    def test_packaging_gate_is_before_signing(self):
        script = (ROOT / 'Packaging/release.sh').read_text()
        self.assertLess(script.index('verify-release-test-isolation.py'), script.index('Signing libusb'))
        project = (ROOT / 'Terento.xcodeproj/project.pbxproj').read_text()
        self.assertNotIn('terento-write-test.txt in Resources', project)


if __name__ == '__main__':
    unittest.main()
