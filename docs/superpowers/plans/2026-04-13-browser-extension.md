# WhisperTranscribe v3.0 — Browser Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chrome extension that sends video URLs to WhisperTranscribe for download and transcription via a local HTTP API.

**Architecture:** Extension sends URL via HTTP POST to a lightweight server (port 50061) inside the app. The app downloads audio with yt-dlp and feeds it into the existing batch transcription queue. All communication is localhost-only.

**Tech Stack:** Chrome Manifest V3, Python http.server, yt-dlp, existing customtkinter app

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `url_downloader.py` | yt-dlp wrapper — downloads audio from URLs |
| `app_http_server.py` | HTTP server on :50061 — receives URLs from extension |
| `extension/manifest.json` | Chrome extension manifest (MV3) |
| `extension/background.js` | Service worker — context menu + message routing |
| `extension/popup.html` | Extension popup UI |
| `extension/popup.js` | Popup logic — status check + send URL |
| `extension/content.js` | Detects video URLs on pages |
| `extension/icons/icon16.png` | Extension icon 16px |
| `extension/icons/icon48.png` | Extension icon 48px |
| `extension/icons/icon128.png` | Extension icon 128px |

### Modified Files
| File | Changes |
|------|---------|
| `shared.py` | Add `YTDLP` path, `DOWNLOADS_DIR` constant |
| `app.py` | Import + start HTTP server, add yt-dlp to dependency check, version bump |
| `setup.py` | Version bump to 3.0.0, add new modules to includes |
| `install.sh` | Add `brew install yt-dlp`, extension install instructions |

---

### Task 1: Add yt-dlp constant to shared.py

**Files:**
- Modify: `shared.py:1-14`

- [ ] **Step 1: Add YTDLP path and DOWNLOADS_DIR to shared.py**

Add after the `WHISPERKIT` fallback block (after line 12):

```python
YTDLP = "/opt/homebrew/bin/yt-dlp"

if not os.path.exists(YTDLP):
    import shutil
    found = shutil.which("yt-dlp")
    if found:
        YTDLP = found

DOWNLOADS_DIR = os.path.join(os.path.expanduser("~"), ".whisper_transcribe", "downloads")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "from shared import YTDLP, DOWNLOADS_DIR; print(YTDLP); print(DOWNLOADS_DIR)"`
Expected: paths printed without error

- [ ] **Step 3: Commit**

```bash
git add shared.py
git commit -m "feat: add YTDLP path and DOWNLOADS_DIR to shared constants"
```

---

### Task 2: Create url_downloader.py

**Files:**
- Create: `url_downloader.py`

- [ ] **Step 1: Create url_downloader.py**

```python
"""url_downloader.py — Downloads audio from URLs using yt-dlp."""

import subprocess
import os
import logging
import re

from shared import YTDLP, DOWNLOADS_DIR

log = logging.getLogger("WhisperTranscribe")


def download_audio(url, on_progress=None):
    """
    Download audio from a URL using yt-dlp.

    Parameters
    ----------
    url : str
        The video/audio URL to download.
    on_progress : callable(str) | None
        Called with status messages during download.

    Returns
    -------
    dict with 'filepath' and 'filename' on success.
    Raises RuntimeError on failure.
    """
    if not url or not url.startswith(("http://", "https://")):
        raise RuntimeError(f"URL inválida: {url}")

    if not os.path.exists(YTDLP):
        raise RuntimeError(
            "yt-dlp não encontrado. Instale com: brew install yt-dlp"
        )

    # Get the title first for progress reporting
    output_template = os.path.join(DOWNLOADS_DIR, "%(title)s.%(ext)s")

    cmd = [
        YTDLP,
        "-x",                       # extract audio only
        "--audio-format", "wav",    # convert to wav for WhisperKit
        "--audio-quality", "0",     # best quality
        "--no-playlist",            # single video only
        "-o", output_template,
        "--print", "after_move:filepath",  # print final path to stdout
        url,
    ]

    log.info(f"Downloading: {url}")
    if on_progress:
        on_progress("Baixando áudio...")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            encoding="utf-8",
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Download excedeu o tempo limite (10 min)")

    if proc.returncode != 0:
        # Extract meaningful error from stderr
        err = proc.stderr.strip().split("\n")[-1] if proc.stderr else "Erro desconhecido"
        log.error(f"yt-dlp failed: {proc.stderr}")
        raise RuntimeError(f"Falha no download: {err}")

    # The last non-empty line of stdout is the final filepath
    lines = [l.strip() for l in proc.stdout.strip().split("\n") if l.strip()]
    if not lines:
        raise RuntimeError("yt-dlp não retornou o caminho do arquivo")

    filepath = lines[-1]

    if not os.path.exists(filepath):
        raise RuntimeError(f"Arquivo não encontrado após download: {filepath}")

    filename = os.path.basename(filepath)
    log.info(f"Downloaded: {filename} -> {filepath}")

    return {"filepath": filepath, "filename": filename}
```

- [ ] **Step 2: Test with a short video (requires yt-dlp installed)**

Run: `brew install yt-dlp` (if not already installed)
Then: `python3 -c "from url_downloader import download_audio; r = download_audio('https://www.youtube.com/watch?v=jNQXAC9IVRw'); print(r)"`
Expected: downloads "Me at the zoo" audio, prints filepath

- [ ] **Step 3: Test error cases**

Run: `python3 -c "from url_downloader import download_audio; download_audio('not-a-url')"`
Expected: RuntimeError "URL inválida"

Run: `python3 -c "from url_downloader import download_audio; download_audio('https://example.com/nonexistent')"`
Expected: RuntimeError with yt-dlp error message

- [ ] **Step 4: Commit**

```bash
git add url_downloader.py
git commit -m "feat: add url_downloader — yt-dlp wrapper for downloading audio from URLs"
```

---

### Task 3: Create app_http_server.py

**Files:**
- Create: `app_http_server.py`

- [ ] **Step 1: Create app_http_server.py**

```python
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
```

- [ ] **Step 2: Test the server standalone**

```bash
python3 -c "
from app_http_server import AppHttpServer
import time

class FakeApp:
    _server_ready = True
    class batch:
        is_active = False
    def after(self, ms, fn): fn()
    def _download_and_queue(self, url): print(f'Would download: {url}')

s = AppHttpServer(FakeApp(), port=50061)
s.start()
print('Server running on :50061')
time.sleep(2)

# Test /status
from urllib.request import urlopen, Request
resp = urlopen('http://localhost:50061/status')
print('GET /status:', resp.read().decode())

# Test POST /transcribe
import json
req = Request('http://localhost:50061/transcribe',
    data=json.dumps({'url': 'https://youtube.com/watch?v=test'}).encode(),
    headers={'Content-Type': 'application/json'},
    method='POST')
resp = urlopen(req)
print('POST /transcribe:', resp.read().decode())

s.stop()
print('DONE')
"
```

Expected: status returns JSON, POST returns ok:true, "Would download" printed

- [ ] **Step 3: Commit**

```bash
git add app_http_server.py
git commit -m "feat: add app HTTP server for browser extension communication"
```

---

### Task 4: Integrate HTTP server and download into app.py

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add imports at top of app.py**

After line 18 (`from whisper_server import WhisperServer`), add:

```python
from app_http_server import AppHttpServer
from url_downloader import download_audio
```

- [ ] **Step 2: Update version string**

Change line 2:
```python
"""WhisperTranscribe v3.0 — App premium de transcrição de áudio/vídeo."""
```

- [ ] **Step 3: Start HTTP server in __init__**

In `WhisperApp.__init__`, after `self.server = WhisperServer()` and `self._server_ready = False`, add:

```python
self.http_server = AppHttpServer(self)
```

- [ ] **Step 4: Start HTTP server after WhisperKit is ready**

In `_on_server_ready()`, after `self._restore_upload_btn()`, add:

```python
self.http_server.start()
```

- [ ] **Step 5: Stop HTTP server on close**

In `_on_close()`, before `self.destroy()`, add:

```python
self.http_server.stop()
```

- [ ] **Step 6: Add _download_and_queue method**

Add this method to `WhisperApp` class (before `_add_to_queue`):

```python
def _download_and_queue(self, url):
    """Download audio from URL and add to transcription queue."""
    log.info(f"_download_and_queue: {url}")
    self.progress.start_pulse(f"Baixando: {url[:60]}...")

    def _do_download():
        try:
            def on_progress(msg):
                self.after(0, lambda m=msg: self.progress.set_status(m))

            result = download_audio(url, on_progress=on_progress)
            filepath = result["filepath"]
            log.info(f"Download complete: {filepath}")
            self.after(0, lambda fp=filepath: self._add_to_queue([fp]))
        except Exception as e:
            log.error(f"Download failed: {e}")
            self.after(0, lambda: self.progress.set_status(f"✕ Erro no download: {e}"))
            self.after(0, lambda: self.progress.stop())
            self.after(5000, lambda: self.progress.hide())

    thread = threading.Thread(target=_do_download, daemon=True)
    thread.start()
```

- [ ] **Step 7: Add yt-dlp to dependency check**

In `_check_dependencies()`, after the `has_whisperkit` check, add:

```python
ytdlp_paths = ["/opt/homebrew/bin/yt-dlp", "/usr/local/bin/yt-dlp"]
has_ytdlp = any(os.path.exists(p) for p in ytdlp_paths)

if not has_ytdlp:
    missing.append(
        "yt-dlp (download de vídeos — opcional):\n"
        "  brew install yt-dlp"
    )
```

Note: yt-dlp is optional — change the early return to only block on brew+whisperkit:

Replace:
```python
if not missing:
    return True
```

With:
```python
# yt-dlp is optional — only block startup for core deps
critical_missing = not has_brew or not has_whisperkit
if not missing:
    return True
if not critical_missing:
    # Just warn about optional deps, don't block
    return True
```

- [ ] **Step 8: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('app.py').read()); print('OK')"`
Expected: OK

- [ ] **Step 9: Commit**

```bash
git add app.py
git commit -m "feat: integrate HTTP server and URL download into app"
```

---

### Task 5: Create Chrome extension

**Files:**
- Create: `extension/manifest.json`
- Create: `extension/background.js`
- Create: `extension/popup.html`
- Create: `extension/popup.js`
- Create: `extension/content.js`

- [ ] **Step 1: Create extension/manifest.json**

```json
{
  "manifest_version": 3,
  "name": "WhisperTranscribe",
  "version": "1.0.0",
  "description": "Envie vídeos da web para o WhisperTranscribe transcrever",
  "permissions": ["activeTab", "contextMenus"],
  "host_permissions": ["http://localhost:50061/*"],
  "background": {
    "service_worker": "background.js"
  },
  "action": {
    "default_popup": "popup.html",
    "default_icon": {
      "16": "icons/icon16.png",
      "48": "icons/icon48.png",
      "128": "icons/icon128.png"
    }
  },
  "content_scripts": [
    {
      "matches": ["<all_urls>"],
      "js": ["content.js"],
      "run_at": "document_idle"
    }
  ],
  "icons": {
    "16": "icons/icon16.png",
    "48": "icons/icon48.png",
    "128": "icons/icon128.png"
  }
}
```

- [ ] **Step 2: Create extension/background.js**

```javascript
const API_BASE = "http://localhost:50061";

// Context menu
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "whisper-transcribe",
    title: "Transcrever com WhisperTranscribe",
    contexts: ["page", "video", "audio", "link"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "whisper-transcribe") return;

  // Use link URL if right-clicked on a link, otherwise use page URL
  const url = info.linkUrl || info.pageUrl || tab.url;

  try {
    const resp = await fetch(`${API_BASE}/transcribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await resp.json();

    if (data.ok) {
      chrome.notifications.create({
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: "WhisperTranscribe",
        message: `Enviado para transcrição!`,
      });
    } else {
      chrome.notifications.create({
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: "WhisperTranscribe — Erro",
        message: data.error || "Erro desconhecido",
      });
    }
  } catch (e) {
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "WhisperTranscribe",
      message: "App não está aberto. Abra o WhisperTranscribe primeiro.",
    });
  }
});

// Handle messages from popup
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "get-video-url") {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]) {
        chrome.tabs.sendMessage(tabs[0].id, { type: "detect-video" }, (response) => {
          sendResponse(response || { url: tabs[0].url });
        });
      }
    });
    return true; // async response
  }
});
```

- [ ] **Step 3: Create extension/content.js**

```javascript
// Detect video URLs on the current page
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type !== "detect-video") return;

  const url = window.location.href;

  // YouTube
  if (url.includes("youtube.com/watch") || url.includes("youtu.be/")) {
    sendResponse({ url, source: "youtube" });
    return;
  }

  // Vimeo
  if (url.includes("vimeo.com/")) {
    sendResponse({ url, source: "vimeo" });
    return;
  }

  // Try to find a <video> or <source> element
  const video = document.querySelector("video");
  if (video) {
    const src = video.src || video.querySelector("source")?.src;
    if (src && src.startsWith("http")) {
      sendResponse({ url: src, source: "video-element" });
      return;
    }
  }

  // Fallback: page URL (yt-dlp supports many sites)
  sendResponse({ url, source: "page" });
});
```

- [ ] **Step 4: Create extension/popup.html**

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      width: 320px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0d0d1a;
      color: #eeeeff;
      padding: 16px;
    }
    .header {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 16px;
    }
    .logo {
      width: 32px; height: 32px;
      background: #7c6cf0;
      border-radius: 8px;
      display: flex; align-items: center; justify-content: center;
      font-weight: bold; font-size: 18px; color: #fff;
    }
    .title { font-size: 15px; font-weight: 600; }
    .status {
      display: flex; align-items: center; gap: 6px;
      font-size: 12px; color: #6a6a90;
      margin-bottom: 14px;
    }
    .dot {
      width: 8px; height: 8px; border-radius: 50%;
      background: #f06060;
    }
    .dot.online { background: #00d4aa; }
    .url-box {
      width: 100%;
      background: #12122a;
      border: 1px solid #252545;
      border-radius: 8px;
      padding: 10px;
      color: #b0b0d0;
      font-size: 12px;
      word-break: break-all;
      margin-bottom: 12px;
      min-height: 40px;
    }
    .btn {
      width: 100%;
      padding: 10px;
      background: #7c6cf0;
      color: #fff;
      border: none;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.2s;
    }
    .btn:hover { background: #8f82f5; }
    .btn:disabled { background: #3a3a6a; cursor: not-allowed; }
    .feedback {
      text-align: center;
      font-size: 12px;
      margin-top: 10px;
      color: #00d4aa;
      min-height: 16px;
    }
    .feedback.error { color: #f06060; }
  </style>
</head>
<body>
  <div class="header">
    <div class="logo">W</div>
    <span class="title">WhisperTranscribe</span>
  </div>
  <div class="status">
    <div class="dot" id="status-dot"></div>
    <span id="status-text">Verificando...</span>
  </div>
  <div class="url-box" id="url-display">Detectando URL...</div>
  <button class="btn" id="send-btn" disabled>Transcrever</button>
  <div class="feedback" id="feedback"></div>
  <script src="popup.js"></script>
</body>
</html>
```

- [ ] **Step 5: Create extension/popup.js**

```javascript
const API_BASE = "http://localhost:50061";

const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const urlDisplay = document.getElementById("url-display");
const sendBtn = document.getElementById("send-btn");
const feedback = document.getElementById("feedback");

let detectedUrl = null;
let appOnline = false;

// Check app status
async function checkStatus() {
  try {
    const resp = await fetch(`${API_BASE}/status`, { signal: AbortSignal.timeout(2000) });
    const data = await resp.json();
    appOnline = true;
    statusDot.classList.add("online");
    statusText.textContent = "App conectado";
    updateButton();
  } catch {
    appOnline = false;
    statusDot.classList.remove("online");
    statusText.textContent = "App offline — abra o WhisperTranscribe";
    updateButton();
  }
}

// Detect video URL on current tab
function detectUrl() {
  chrome.runtime.sendMessage({ type: "get-video-url" }, (response) => {
    if (response && response.url) {
      detectedUrl = response.url;
      const display = detectedUrl.length > 80
        ? detectedUrl.substring(0, 77) + "..."
        : detectedUrl;
      urlDisplay.textContent = display;
      updateButton();
    } else {
      urlDisplay.textContent = "Nenhuma URL detectada";
    }
  });
}

function updateButton() {
  sendBtn.disabled = !appOnline || !detectedUrl;
}

// Send URL to app
sendBtn.addEventListener("click", async () => {
  if (!detectedUrl || !appOnline) return;

  sendBtn.disabled = true;
  sendBtn.textContent = "Enviando...";
  feedback.textContent = "";
  feedback.className = "feedback";

  try {
    const resp = await fetch(`${API_BASE}/transcribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: detectedUrl }),
    });
    const data = await resp.json();

    if (data.ok) {
      feedback.textContent = "✓ Enviado para transcrição!";
      sendBtn.textContent = "✓ Enviado";
    } else {
      feedback.textContent = data.error || "Erro desconhecido";
      feedback.className = "feedback error";
      sendBtn.textContent = "Transcrever";
      sendBtn.disabled = false;
    }
  } catch {
    feedback.textContent = "Não foi possível conectar ao app";
    feedback.className = "feedback error";
    sendBtn.textContent = "Transcrever";
    sendBtn.disabled = false;
  }
});

// Init
checkStatus();
detectUrl();
```

- [ ] **Step 6: Generate extension icons**

Create simple placeholder icons using Python:

```bash
python3 -c "
import struct, zlib, os

def create_png(size, filepath):
    \"\"\"Create a simple purple square PNG icon.\"\"\"
    # Purple (#7c6cf0) with W letter approximation
    r, g, b = 124, 108, 240
    width = height = size

    raw = b''
    for y in range(height):
        raw += b'\x00'  # filter byte
        for x in range(width):
            # Simple rounded square with margin
            margin = size // 6
            corner = size // 4
            in_x = margin <= x < width - margin
            in_y = margin <= y < height - margin
            if in_x and in_y:
                raw += struct.pack('BBBB', r, g, b, 255)
            else:
                raw += struct.pack('BBBB', 0, 0, 0, 0)

    def chunk(chunk_type, data):
        c = chunk_type + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', ihdr)
    png += chunk(b'IDAT', zlib.compress(raw))
    png += chunk(b'IEND', b'')

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'wb') as f:
        f.write(png)
    print(f'Created {filepath}')

create_png(16, 'extension/icons/icon16.png')
create_png(48, 'extension/icons/icon48.png')
create_png(128, 'extension/icons/icon128.png')
"
```

- [ ] **Step 7: Commit**

```bash
git add extension/
git commit -m "feat: add Chrome extension for sending video URLs to WhisperTranscribe"
```

---

### Task 6: Update install.sh and setup.py

**Files:**
- Modify: `install.sh`
- Modify: `setup.py`

- [ ] **Step 1: Add yt-dlp to install.sh**

After the whisperkit-cli install block (after line 42), add:

```bash
# --- Instalar yt-dlp ---
echo "[2/5] Instalando yt-dlp..."
if command -v yt-dlp &>/dev/null; then
    echo "  -> yt-dlp ja instalado"
else
    brew install yt-dlp
    echo "  -> yt-dlp instalado com sucesso!"
fi
```

Update the step numbers: whisperkit becomes [1/5], yt-dlp is [2/5], Python is [3/5], tkinter is [4/5], venv is [5/5].

Also add at the end, before the final "Pronto!" message:

```bash
echo ""
echo "Para instalar a extensão do Chrome:"
echo "  1. Abra chrome://extensions no Chrome"
echo "  2. Ative o 'Modo do desenvolvedor' (canto superior direito)"
echo "  3. Clique em 'Carregar sem compactação'"
echo "  4. Selecione a pasta: $(pwd)/extension"
echo ""
```

- [ ] **Step 2: Update setup.py**

Change version to 3.0.0 and add new modules to includes:

```python
'CFBundleVersion': '3.0.0',
'CFBundleShortVersionString': '3.0.0',
```

Add to `includes` list:
```python
'app_http_server', 'url_downloader',
```

- [ ] **Step 3: Verify syntax**

Run: `bash -n install.sh && echo 'install.sh OK'`
Run: `python3 -c "import ast; ast.parse(open('setup.py').read()); print('setup.py OK')"`

- [ ] **Step 4: Commit**

```bash
git add install.sh setup.py
git commit -m "feat: update install.sh with yt-dlp step and setup.py for v3.0.0"
```

---

### Task 7: Integration test — full flow

**Files:** None (test only)

- [ ] **Step 1: Install yt-dlp if not present**

Run: `brew install yt-dlp`

- [ ] **Step 2: Test url_downloader with a real video**

```bash
python3 -c "
from url_downloader import download_audio
result = download_audio('https://www.youtube.com/watch?v=jNQXAC9IVRw')
print(f'Downloaded: {result[\"filepath\"]}')
import os
print(f'File exists: {os.path.exists(result[\"filepath\"])}')
print(f'Size: {os.path.getsize(result[\"filepath\"]) / 1024:.0f} KB')
"
```

Expected: file downloaded to `~/.whisper_transcribe/downloads/`, exists, non-zero size

- [ ] **Step 3: Test HTTP server + download integration**

```bash
python3 -c "
from app_http_server import AppHttpServer
from url_downloader import download_audio
import threading, time, json
from urllib.request import Request, urlopen

downloaded_files = []

class FakeApp:
    _server_ready = True
    class batch:
        is_active = False
    def after(self, ms, fn): fn()
    def _download_and_queue(self, url):
        result = download_audio(url)
        downloaded_files.append(result['filepath'])
        print(f'Queued: {result[\"filename\"]}')

app = FakeApp()
srv = AppHttpServer(app, port=50061)
srv.start()
time.sleep(1)

# Send a URL
req = Request('http://localhost:50061/transcribe',
    data=json.dumps({'url': 'https://www.youtube.com/watch?v=jNQXAC9IVRw'}).encode(),
    headers={'Content-Type': 'application/json'},
    method='POST')
resp = urlopen(req)
data = json.loads(resp.read().decode())
print(f'Response: {data}')

# Wait for download
time.sleep(30)
print(f'Downloaded files: {downloaded_files}')
srv.stop()
print('DONE')
" 2>&1
```

Expected: POST returns ok:true, file gets downloaded and queued

- [ ] **Step 4: Build and install updated .app**

```bash
rm -rf build dist
source .venv/bin/activate
python3 setup.py py2app 2>&1 | tail -3
rm -rf /Applications/WhisperTranscribe.app
cp -R dist/WhisperTranscribe.app /Applications/
echo "v3.0 installed"
```

- [ ] **Step 5: Test the .app with extension**

1. Open WhisperTranscribe from /Applications
2. Load extension in Chrome: chrome://extensions → Load unpacked → select `extension/` folder
3. Go to a YouTube video
4. Click the extension icon → verify app status shows "conectado"
5. Click "Transcrever" → verify video downloads and transcription starts

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "WhisperTranscribe v3.0.0 — Chrome extension for web video transcription"
```
