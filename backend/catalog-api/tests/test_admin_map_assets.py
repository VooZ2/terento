import hashlib
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from terento_catalog.admin import (
    ADMIN_STYLES, ADMIN_STYLESHEET_PATH, WORLD_MAP_SCRIPT, WORLD_MAP_SCRIPT_PATH, _layout, login_page,
    map_statistics_page,
)
from terento_catalog.admin_world_map import WORLD_MAP_SVG
from terento_catalog.http_api import make_handler


class AdminMapAssetsTests(unittest.TestCase):
    def test_assets_require_session_and_have_explicit_allowlist(self):
        service = SimpleNamespace(admin_is_configured=lambda: True,
            admin_review_summary=lambda: {},
            admin_session=lambda token: {'id': 1} if token == 'valid' else None,
            csrf_valid=lambda session, token: token == 'valid')
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection(*server.server_address)
            connection.request('GET', '/admin/map-assets/leaflet-1.9.4.js')
            response = connection.getresponse()
            self.assertEqual(response.status, 303)
            response.read()
            headers = {'Cookie': 'terento_admin_session=valid; terento_admin_csrf=valid'}
            connection.request('GET', '/admin/map-assets/leaflet-1.9.4.js', headers=headers)
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIn('private', response.getheader('Cache-Control'))
            self.assertIn(b'1.9.4', response.read())
            connection.request('GET', '/admin/map-assets/../../config.py', headers=headers)
            response = connection.getresponse()
            self.assertNotEqual(response.status, 200)
            response.read()
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_admin_css_is_one_content_versioned_cached_stylesheet(self):
        digest = hashlib.sha256(ADMIN_STYLES.encode("utf-8")).hexdigest()[:16]
        self.assertEqual(ADMIN_STYLESHEET_PATH, f"/admin/map-assets/admin.{digest}.css")
        page = _layout("Test", "<main id='main-content'></main>").decode()
        self.assertIn(f'<link rel="stylesheet" href="{ADMIN_STYLESHEET_PATH}">', page)
        self.assertNotIn("<style>", page)
        self.assertLess(len(page), len(ADMIN_STYLES))
        # Before sign-in the asset route redirects, so the sign-in page keeps its CSS inline.
        self.assertIn(f"<style>{ADMIN_STYLES}</style>", login_page().decode())
        # Maps loads the static world map as a versioned script, not inline data.
        digest = hashlib.sha256(WORLD_MAP_SCRIPT.encode("utf-8")).hexdigest()[:16]
        self.assertEqual(WORLD_MAP_SCRIPT_PATH, f"/admin/map-assets/world-map.{digest}.js")
        maps = map_statistics_page({"rows": []}, [], {"username": "a"}, "csrf").decode()
        self.assertIn(f'src="{WORLD_MAP_SCRIPT_PATH}"></script>', maps)
        self.assertNotIn(WORLD_MAP_SVG[:80], maps)
        self.assertNotIn("window.terentoWorldMapSvg = ", maps)
        service = SimpleNamespace(admin_is_configured=lambda: True,
            admin_session=lambda token: {'id': 1} if token == 'valid' else None,
            csrf_valid=lambda session, token: token == 'valid')
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection(*server.server_address)
            connection.request('GET', ADMIN_STYLESHEET_PATH)
            response = connection.getresponse()
            self.assertEqual(response.status, 303)
            response.read()
            headers = {'Cookie': 'terento_admin_session=valid; terento_admin_csrf=valid'}
            connection.request('GET', ADMIN_STYLESHEET_PATH, headers=headers)
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader('Content-Type'), 'text/css; charset=utf-8')
            self.assertEqual(response.getheader('Cache-Control'), 'private, max-age=31536000, immutable')
            self.assertEqual(response.read(), ADMIN_STYLES.encode("utf-8"))
            connection.request('GET', WORLD_MAP_SCRIPT_PATH, headers=headers)
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader('Content-Type'), 'text/javascript; charset=utf-8')
            self.assertEqual(response.getheader('Cache-Control'), 'private, max-age=31536000, immutable')
            self.assertEqual(response.read(), WORLD_MAP_SCRIPT.encode("utf-8"))
            connection.request('GET', '/admin/map-assets/admin.0000000000000000.css', headers=headers)
            response = connection.getresponse()
            self.assertNotEqual(response.status, 200)
            response.read()
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
