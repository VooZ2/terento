"""Serve generated Admin presentation fixtures with read-only Admin routes."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from urllib.parse import urlsplit


def serve(directory: Path, port: int = 8765) -> None:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def do_GET(self):
            route = urlsplit(self.path).path
            fixture_routes = {
                "/admin": "/overview.html",
                "/admin/devices": "/devices.html",
                "/admin/installations": "/installations.html",
                "/admin/map-statistics": "/statistics.html",
                "/admin/providers": "/providers.html",
                "/admin/system-health": "/health.html",
                "/admin/diagnostics": "/diagnostics.html",
            }
            if route in fixture_routes:
                self.path = fixture_routes[route]
            elif route.startswith("/admin/devices/"):
                self.path = "/device.html"
            elif route.startswith("/admin/providers/"):
                self.path = "/provider.html"
            elif route.startswith("/admin/") and not route.startswith("/admin/map-assets/"):
                self.path = route.removeprefix("/admin")
            super().do_GET()

    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    serve(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 8765)
