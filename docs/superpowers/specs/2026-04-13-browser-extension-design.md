# WhisperTranscribe v3.0 — Browser Extension Design

## Overview

Chrome extension that sends video URLs from any web page to the WhisperTranscribe macOS app for transcription. The app downloads the video via yt-dlp and processes it through the existing batch queue.

## Architecture

```
[Chrome Extension] --POST /transcribe--> [App HTTP Server :50061] --yt-dlp--> [local file] --batch queue--> [WhisperKit :50060]
```

Three new components:
1. **Chrome Extension** (Manifest V3) — UI in the browser
2. **App HTTP Server** (port 50061) — receives URLs, manages downloads
3. **yt-dlp integration** — downloads video/audio from URLs

## Component 1: Chrome Extension

### Manifest
- Manifest V3
- Permissions: `activeTab`, `contextMenus`
- Host permission: `http://localhost:50061/*`

### UI — Popup (popup.html + popup.js)
- Status indicator: green dot = app online, red = offline (polls `GET /status`)
- Text field showing detected video URL from current tab
- "Transcrever" button sends URL to app
- Feedback: "Enviado!", "App offline", "Erro"

### Context Menu (background.js)
- Right-click on any page → "Transcrever com WhisperTranscribe"
- Sends current tab URL to `POST /transcribe`
- Shows Chrome notification with result ("Enviado!" or "App offline")

### URL Detection (content.js)
- On YouTube: extracts video URL from `location.href`
- On other sites: extracts `<video src>` or `<source src>` from the page
- Sends detected URL to popup via `chrome.runtime.sendMessage`

### Files
```
extension/
  manifest.json
  background.js      — context menu + message handling
  popup.html          — extension popup UI
  popup.js            — popup logic
  content.js          — page URL detection
  icons/
    icon16.png
    icon48.png
    icon128.png
```

## Component 2: App HTTP Server

### Overview
Lightweight HTTP server running on `localhost:50061` inside the app process. Uses Python stdlib `http.server` in a daemon thread. Separate from the WhisperKit server on port 50060.

### Endpoints

#### `GET /status`
Returns app readiness state.
```json
{"status": "ready", "server_ready": true, "queue_active": false}
```

#### `POST /transcribe`
Accepts a URL for download and transcription.

Request:
```json
{"url": "https://www.youtube.com/watch?v=..."}
```

Response (accepted):
```json
{"ok": true, "message": "Download iniciado", "filename": "Video Title.wav"}
```

Response (error):
```json
{"ok": false, "error": "yt-dlp não encontrado"}
```

### CORS
- `Access-Control-Allow-Origin: *` (localhost only, acceptable security)
- Handles preflight `OPTIONS` requests

### Integration with App
- `AppHttpServer` class, started in `WhisperApp.__init__` after server ready
- Download runs in a background thread
- On download complete, calls `self._add_to_queue([filepath])` on the main thread via `self.after(0, ...)`
- Download progress shown in the UI progress bar: "Baixando: Video Title..."

## Component 3: yt-dlp Integration

### Download Flow
1. Receive URL from HTTP endpoint
2. Validate URL is not empty
3. Run: `yt-dlp -x --audio-format wav --audio-quality 0 -o <output_template> <url>`
4. Output to: `~/.whisper_transcribe/downloads/<title>.wav`
5. On success, add file to batch queue
6. On failure, report error to UI

### Download Directory
`~/.whisper_transcribe/downloads/` — created on first use, files persist until user deletes.

### yt-dlp Path
Same pattern as whisperkit-cli: check `/opt/homebrew/bin/yt-dlp` first, fall back to `shutil.which`.

### Error Handling
- yt-dlp not installed → show dependency error (same pattern as whisperkit-cli check)
- Invalid URL → return error to extension
- Download fails → mark as error in queue, advance to next
- Network timeout → yt-dlp handles its own retries

## Changes to Existing Code

### shared.py
- Add `YTDLP` path constant (same pattern as `WHISPERKIT`)
- Add `DOWNLOADS_DIR` constant

### app.py
- Import and start `AppHttpServer` after WhisperKit server is ready
- Add yt-dlp to `_check_dependencies()`
- Stop HTTP server in `_on_close()`
- Version bump to 3.0.0

### install.sh
- Add `brew install yt-dlp` step
- Add instructions for Chrome extension installation

### setup.py
- Version bump to 3.0.0
- Add `app_http_server` to includes

## New Files
- `extension/` — Chrome extension (manifest.json, background.js, popup.html, popup.js, content.js, icons/)
- `app_http_server.py` — HTTP server class for receiving URLs from extension
- `url_downloader.py` — yt-dlp wrapper for downloading videos

## Dependency Check on Startup
yt-dlp is added to the existing dependency check dialog. If missing, shows install instructions alongside whisperkit-cli. The app still works for local files without yt-dlp — the extension features just won't work.

## Security Considerations
- Server only binds to `localhost` — not accessible from network
- No authentication needed (local-only)
- URL validation before passing to yt-dlp (must start with http/https)
- yt-dlp output directory is fixed (no path traversal)
