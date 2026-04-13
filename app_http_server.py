"""app_http_server.py — Local HTTP server for receiving URLs from the browser extension."""

import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

log = logging.getLogger("WhisperTranscribe")

DEFAULT_PORT = 50061


class _Handler(BaseHTTPRequestHandler):
    """Handles requests from the Chrome extension."""

    def log_message(self, format, *args):
        log.debug(f"HTTP: {format % args}")

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == "/status":
            app = self.server.app_ref
            self._json_response(200, {
                "status": "ready",
                "server_ready": app._server_ready if app else False,
                "queue_active": app.batch.is_active if app else False,
            })
        else:
            self._json_response(404, {"error": "Not found"})

    def do_POST(self):
        if self.path == "/transcribe":
            try:
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                data = json.loads(raw.decode("utf-8"))
                url = data.get("url", "").strip()

                if not url:
                    self._json_response(400, {"ok": False, "error": "URL vazia"})
                    return

                if not url.startswith(("http://", "https://")):
                    self._json_response(400, {"ok": False, "error": "URL inválida"})
                    return

                log.info(f"Received URL from extension: {url}")

                # Trigger download in background
                app = self.server.app_ref
                if app:
                    app.after(0, lambda u=url: app._download_and_queue(u))

                self._json_response(200, {
                    "ok": True,
                    "message": "Download iniciado",
                })

            except json.JSONDecodeError:
                self._json_response(400, {"ok": False, "error": "JSON inválido"})
            except Exception as e:
                log.error(f"POST /transcribe error: {e}")
                self._json_response(500, {"ok": False, "error": str(e)})
        else:
            self._json_response(404, {"error": "Not found"})


class AppHttpServer:
    """Lightweight HTTP server for extension communication."""

    def __init__(self, app_ref, port=DEFAULT_PORT):
        self.port = port
        self.app_ref = app_ref
        self._server = None
        self._thread = None

    def start(self):
        """Start the HTTP server in a daemon thread."""
        try:
            self._server = HTTPServer(("127.0.0.1", self.port), _Handler)
            self._server.app_ref = self.app_ref
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            log.info(f"App HTTP server started on port {self.port}")
        except OSError as e:
            log.error(f"Failed to start HTTP server: {e}")

    def stop(self):
        """Stop the HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server = None
        log.info("App HTTP server stopped")
