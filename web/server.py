import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


class Handler(BaseHTTPRequestHandler):
    provider = None

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            view = parse_qs(parsed.query).get("view", ["single"])[0]
            body = json.dumps(self.provider(view), ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        item = FILES.get(parsed.path)
        if item is None:
            self.send_error(404)
            return
        name, content_type = item
        body = (ROOT / name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def serve(port, provider):
    Handler.provider = staticmethod(provider)
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


def start(port, provider):
    Handler.provider = staticmethod(provider)
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    thread = threading.Thread(target=server.serve_forever, name="webui", daemon=True)
    thread.start()
    return server
