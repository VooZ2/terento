import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from terento_catalog.http_api import make_handler


class AdminMapAssetsTests(unittest.TestCase):
    def test_assets_require_session_and_have_explicit_allowlist(self):
        service = SimpleNamespace(admin_is_configured=lambda: True,
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
