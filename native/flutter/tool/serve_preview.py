"""Serve the compiled Flutter web app with a loopback-only Apex API proxy."""

import argparse
from functools import partial
from http.client import HTTPConnection, HTTPException
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class PreviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory, api_port, **kwargs):
        self.api_port = api_port
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        if urlsplit(self.path).path.startswith("/api/"):
            self.proxy_api()
        else:
            super().do_GET()

    def do_POST(self):
        self.proxy_api()

    def do_PUT(self):
        self.proxy_api()

    def do_PATCH(self):
        self.proxy_api()

    def do_DELETE(self):
        self.proxy_api()

    def proxy_api(self):
        # Only an explicitly supplied local API is reachable through this tool.
        path = urlsplit(self.path)
        if path.netloc or path.scheme or not path.path.startswith("/api/"):
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400)
            return
        if not 0 <= size <= 8 * 1024 * 1024:
            self.send_error(413)
            return
        conn = HTTPConnection("127.0.0.1", self.api_port, timeout=35)
        try:
            headers = {
                key: self.headers[key]
                for key in ("Authorization", "Accept", "Content-Type", "Idempotency-Key",
                            "X-Chunk-Sha256", "Range")
                if key in self.headers
            }
            conn.request(self.command, self.path, self.rfile.read(size) if size else None, headers)
            response = conn.getresponse()
            contents = response.read()
            self.send_response(response.status)
            for key in ("Content-Type", "Content-Disposition", "X-Apex-Error"):
                value = response.getheader(key)
                if value:
                    self.send_header(key, value)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(contents)))
            self.end_headers()
            self.wfile.write(contents)
        except (OSError, HTTPException):
            self.close_connection = True
        finally:
            conn.close()


def preview_server(directory, api_port, port=0):
    return ThreadingHTTPServer(
        ("127.0.0.1", port),
        partial(PreviewHandler, directory=str(directory), api_port=api_port),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--api-port", type=int, default=8012)
    cli.add_argument("--port", type=int, default=5174)
    cli.add_argument(
        "--directory",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "build" / "web",
    )
    args = cli.parse_args()
    if not (args.directory / "index.html").is_file():
        cli.error("Run flutter build web first or point --directory at the web bundle.")
    if not 0 < args.api_port <= 65535 or not 0 < args.port <= 65535:
        cli.error("Provide valid local TCP ports.")
    with preview_server(args.directory, args.api_port, args.port) as server:
        print(f"Apex Books preview: http://127.0.0.1:{args.port}", flush=True)
        server.serve_forever()
