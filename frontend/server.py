#!/usr/bin/env python3
"""Zero-dependency HTTP server and reverse-proxy for the Citely frontend.

- Serves static frontend files on port 3000 (or custom port via --port).
- Proxies all /api/v1/* requests to the FastAPI backend (default http://localhost:8000).
- Injects permissive CORS headers so browser fetch works without any backend modification.

Usage:
    python frontend/server.py
    python frontend/server.py --port 3000 --backend http://localhost:8000
"""

import argparse
import http.server
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
FRONTEND_DIR = os.path.dirname(os.path.abspath(__file__))


class FrontendProxyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def end_headers(self):
        # Enable CORS for all local requests
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/v1"):
            self._proxy_request("GET")
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/v1"):
            self._proxy_request("POST")
        else:
            self.send_error(405, "Method Not Allowed")

    def do_DELETE(self):
        if self.path.startswith("/api/v1"):
            self._proxy_request("DELETE")
        else:
            self.send_error(405, "Method Not Allowed")

    def _proxy_request(self, method: str):
        target_url = urllib.parse.urljoin(BACKEND_URL, self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        # Copy non-host headers
        headers = {}
        for header, value in self.headers.items():
            if header.lower() not in ("host", "content-length"):
                headers[header] = value

        req = urllib.request.Request(target_url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                self.send_response(resp.status)
                for key, val in resp.headers.items():
                    if key.lower() not in ("transfer-encoding", "content-encoding", "access-control-allow-origin"):
                        self.send_header(key, val)
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for key, val in e.headers.items():
                if key.lower() not in ("transfer-encoding", "content-encoding", "access-control-allow-origin"):
                    self.send_header(key, val)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            error_json = (
                f'{{"detail": "Frontend proxy cannot reach backend at {BACKEND_URL}. '
                f'Ensure backend is running: {str(e)}"}}'
            )
            self.wfile.write(error_json.encode("utf-8"))


def run(port: int = 3000, backend: str = "http://localhost:8000"):
    global BACKEND_URL
    BACKEND_URL = backend.rstrip("/")
    mimetypes.init()
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")

    server_address = ("", port)
    httpd = http.server.ThreadingHTTPServer(server_address, FrontendProxyHandler)
    print("=" * 65)
    print(f"🚀 Citely Frontend running at: http://localhost:{port}")
    print(f"🔗 Forwarding API calls (/api/v1/*) to:   {BACKEND_URL}/api/v1")
    print(f"📂 Serving static files from:             {FRONTEND_DIR}")
    print("=" * 65)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down frontend server.")
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Serve the Citely frontend")
    parser.add_argument("--port", type=int, default=3000, help="Port to serve on (default: 3000)")
    parser.add_argument("--backend", type=str, default="http://localhost:8000", help="FastAPI backend URL")
    args = parser.parse_args()
    run(port=args.port, backend=args.backend)

