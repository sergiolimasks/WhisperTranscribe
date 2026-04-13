"""
whisper_server.py — Manages a persistent WhisperKit server process.

Starts whisperkit-cli serve once when the app opens, keeping the model
loaded in memory. Transcriptions use the HTTP API instead of spawning
a new process each time, making batch processing much faster.
"""

import subprocess
import threading
import time
import json
import os
from urllib.request import Request, urlopen
from urllib.error import URLError

from shared import WHISPERKIT, MAX_FILE_SIZE

DEFAULT_PORT = 50060
DEFAULT_HOST = "localhost"


class WhisperServer:
    """Manages the whisperkit-cli serve lifecycle."""

    def __init__(self, port=DEFAULT_PORT, host=DEFAULT_HOST):
        self.port = port
        self.host = host
        self.base_url = f"http://{host}:{port}"
        self._process = None
        self._ready = False
        self._error = None

    @property
    def is_ready(self):
        return self._ready and self._process and self._process.poll() is None

    @property
    def error(self):
        return self._error

    def start(self, language=None, on_ready=None, on_error=None):
        """Start the server in a background thread. Calls on_ready or on_error."""
        def _run():
            try:
                cmd = [
                    WHISPERKIT, "serve",
                    "--port", str(self.port),
                    "--host", self.host,
                ]
                if language:
                    cmd += ["--language", language]

                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

                # Wait for server to be ready by polling /health
                deadline = time.time() + 120  # 2 min timeout for model download
                while time.time() < deadline:
                    if self._process.poll() is not None:
                        self._error = "Servidor encerrou inesperadamente"
                        if on_error:
                            on_error(self._error)
                        return

                    try:
                        req = Request(f"{self.base_url}/health")
                        resp = urlopen(req, timeout=2)
                        if resp.status == 200:
                            self._ready = True
                            if on_ready:
                                on_ready()
                            return
                    except (URLError, OSError):
                        pass

                    time.sleep(0.5)

                self._error = "Timeout esperando servidor iniciar"
                if on_error:
                    on_error(self._error)

            except FileNotFoundError:
                self._error = f"whisperkit-cli não encontrado em {WHISPERKIT}"
                if on_error:
                    on_error(self._error)
            except Exception as e:
                self._error = str(e)
                if on_error:
                    on_error(self._error)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def health_check(self):
        """Ping /health to verify the server is actually responding."""
        if not self._process or self._process.poll() is not None:
            return False
        try:
            req = Request(f"{self.base_url}/health")
            resp = urlopen(req, timeout=3)
            return resp.status == 200
        except (URLError, OSError):
            return False

    def restart(self, language=None, on_ready=None, on_error=None):
        """Stop and restart the server."""
        self.stop()
        self._error = None
        self.start(language=language, on_ready=on_ready, on_error=on_error)

    def stop(self):
        """Stop the server."""
        self._ready = False
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None

    def transcribe(self, filepath, language=None):
        """
        Transcribe an audio file using the server API.
        Returns dict with 'text', 'duration', 'segments' on success.
        Raises Exception on failure.
        """
        if not self.is_ready:
            raise RuntimeError("Servidor WhisperKit não está pronto")

        # Check file size before loading into memory
        file_size = os.path.getsize(filepath)
        if file_size > MAX_FILE_SIZE:
            raise RuntimeError(
                f"Arquivo muito grande ({file_size / (1024**3):.1f} GB). "
                f"Limite: {MAX_FILE_SIZE / (1024**3):.1f} GB."
            )

        import mimetypes
        content_type = mimetypes.guess_type(filepath)[0] or "application/octet-stream"
        filename = os.path.basename(filepath)

        # Build multipart form data
        boundary = "----WhisperTranscribeBoundary"
        body = b""

        # file field
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
        body += f"Content-Type: {content_type}\r\n\r\n".encode()
        with open(filepath, "rb") as f:
            body += f.read()
        body += b"\r\n"

        # model field (required by the API)
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="model"\r\n\r\n'
        body += b"whisper-large-v3\r\n"

        # language field
        if language:
            body += f"--{boundary}\r\n".encode()
            body += b'Content-Disposition: form-data; name="language"\r\n\r\n'
            body += f"{language}\r\n".encode()

        # response format
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="response_format"\r\n\r\n'
        body += b"verbose_json\r\n"

        body += f"--{boundary}--\r\n".encode()

        req = Request(
            f"{self.base_url}/v1/audio/transcriptions",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )

        # Use a thread to monitor server health while waiting for response
        response_data = {}
        error_holder = {}

        def _do_request():
            try:
                resp = urlopen(req, timeout=600)
                response_data["result"] = resp.read().decode()
            except Exception as e:
                error_holder["error"] = e

        req_thread = threading.Thread(target=_do_request, daemon=True)
        req_thread.start()

        # Poll: wait for response while checking server health every 10s
        while req_thread.is_alive():
            req_thread.join(timeout=10)
            if req_thread.is_alive() and not self.health_check():
                raise RuntimeError(
                    "Servidor WhisperKit parou de responder durante a transcrição"
                )

        if "error" in error_holder:
            raise error_holder["error"]

        data = json.loads(response_data["result"])

        if "error" in data and data.get("error"):
            raise RuntimeError(data.get("reason", "Erro desconhecido"))

        return {
            "text": data.get("text", "").strip(),
            "duration": data.get("duration", 0),
            "segments": data.get("segments", []),
            "language": data.get("language", ""),
        }
