"""url_downloader.py — Downloads audio from URLs using yt-dlp."""

import subprocess
import os
import logging

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
