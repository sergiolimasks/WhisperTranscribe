"""url_downloader.py — Downloads audio from URLs using yt-dlp Python library."""

import os
import logging

from shared import DOWNLOADS_DIR

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

    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError(
            "yt-dlp não encontrado. Instale com: brew install yt-dlp"
        )

    output_template = os.path.join(DOWNLOADS_DIR, "%(title)s.%(ext)s")
    downloaded_file = {}

    def progress_hook(d):
        if d["status"] == "downloading" and on_progress:
            percent = d.get("_percent_str", "").strip()
            on_progress(f"Baixando: {percent}")
        elif d["status"] == "finished":
            downloaded_file["filepath"] = d.get("filename", "")

    opts = {
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
            "preferredquality": "0",
        }],
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [progress_hook],
    }

    log.info(f"Downloading: {url}")
    if on_progress:
        on_progress("Baixando áudio...")

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "download")

            # Find the output file — yt-dlp changes extension after postprocessing
            expected = os.path.join(DOWNLOADS_DIR, f"{title}.wav")
            if os.path.exists(expected):
                filepath = expected
            else:
                # Fallback: find most recent wav in downloads dir
                wavs = [
                    os.path.join(DOWNLOADS_DIR, f)
                    for f in os.listdir(DOWNLOADS_DIR)
                    if f.endswith(".wav")
                ]
                if wavs:
                    filepath = max(wavs, key=os.path.getmtime)
                else:
                    raise RuntimeError("Arquivo WAV não encontrado após download")

    except RuntimeError:
        raise
    except Exception as e:
        log.error(f"yt-dlp failed: {e}")
        raise RuntimeError(f"Falha no download: {e}")

    filename = os.path.basename(filepath)
    log.info(f"Downloaded: {filename} -> {filepath}")

    return {"filepath": filepath, "filename": filename}
