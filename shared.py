"""Shared constants and utilities for WhisperTranscribe."""

import os

WHISPERKIT = "/opt/homebrew/bin/whisperkit-cli"

# Fall back to PATH lookup on Intel Macs or custom installs
if not os.path.exists(WHISPERKIT):
    import shutil
    found = shutil.which("whisperkit-cli")
    if found:
        WHISPERKIT = found

AUDIO_VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".m4a", ".mp3", ".wav", ".webm",
    ".ogg", ".flac", ".aac", ".mkv", ".avi", ".wma",
    ".m4v", ".3gp", ".opus", ".caf"
}

COLORS = {
    "bg_dark": "#0a0a16",
    "bg_main": "#0d0d1a",
    "bg_card": "#161630",
    "bg_card_hover": "#1e1e42",
    "bg_card_selected": "#252550",
    "bg_input": "#12122a",
    "accent": "#7c6cf0",
    "accent_hover": "#8f82f5",
    "accent_dim": "#5a4ec4",
    "accent_glow": "#7c6cf020",
    "success": "#00d4aa",
    "success_dim": "#00a080",
    "warning": "#f0a030",
    "danger": "#f06060",
    "danger_hover": "#ff4444",
    "text": "#eeeeff",
    "text_secondary": "#b0b0d0",
    "text_dim": "#6a6a90",
    "text_muted": "#44445a",
    "border": "#252545",
    "border_accent": "#3a3a6a",
    "divider": "#1a1a35",
    "progress_bg": "#151530",
    "progress_fill": "#7c6cf0",
    "gradient_start": "#7c6cf0",
    "gradient_end": "#00d4aa",
    "tag_bg": "#1a1a40",
    "drop_zone": "#1a1a3a",
    "drop_zone_active": "#252560",
}


def format_duration(secs):
    """Format seconds into human readable duration."""
    if secs < 60:
        return f"{int(secs)}s"
    mins = int(secs // 60)
    s = int(secs % 60)
    if mins < 60:
        return f"{mins}m {s}s"
    hours = mins // 60
    mins = mins % 60
    return f"{hours}h {mins}m"


def format_file_size(path):
    """Format file size in human readable format."""
    try:
        size = os.path.getsize(path)
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f} GB"
    except Exception:
        return ""


# Max file size for server API upload (1.5 GB)
MAX_FILE_SIZE = 1.5 * 1024 * 1024 * 1024
