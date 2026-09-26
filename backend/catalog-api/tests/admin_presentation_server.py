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
            if route == "/admin":
                self.path = "/overview.html"
            elif route == "/admin/map-statistics":
                self.path = "/statistics.html"
            elif route.startswith("/admin/") and not route.startswith("/admin/map-assets/"):
                self.path = route.removeprefix("/admin")
            super().do_GET()

    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    serve(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 8765)
