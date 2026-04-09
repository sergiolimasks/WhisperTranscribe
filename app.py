#!/usr/bin/env python3
"""WhisperTranscribe v2.0 — App premium de transcrição de áudio/vídeo."""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
import subprocess
import threading
import os
import json
import time
from datetime import datetime
from pathlib import Path
import re

# --- Config ---
HISTORY_DIR = Path.home() / ".whisper_transcribe"
HISTORY_FILE = HISTORY_DIR / "history.json"
SETTINGS_FILE = HISTORY_DIR / "settings.json"
WHISPERKIT = "/opt/homebrew/bin/whisperkit-cli"

HISTORY_DIR.mkdir(exist_ok=True)

# --- Supported formats ---
AUDIO_VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".m4a", ".mp3", ".wav", ".webm",
    ".ogg", ".flac", ".aac", ".mkv", ".avi", ".wma",
    ".m4v", ".3gp", ".opus", ".caf"
}

# --- Theme ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

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

LANGUAGES = {
    "Português": "pt",
    "English": "en",
    "Español": "es",
    "Français": "fr",
    "Deutsch": "de",
    "Italiano": "it",
    "日本語": "ja",
    "中文": "zh",
    "Auto-detectar": None,
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


class SettingsManager:
    """Manages app settings."""

    DEFAULTS = {
        "language": "pt",
        "language_name": "Português",
        "save_txt": True,
        "window_width": 1050,
        "window_height": 700,
    }

    def __init__(self):
        self.settings = self._load()

    def _load(self):
        if SETTINGS_FILE.exists():
            try:
                saved = json.loads(SETTINGS_FILE.read_text())
                merged = {**self.DEFAULTS, **saved}
                return merged
            except Exception:
                return dict(self.DEFAULTS)
        return dict(self.DEFAULTS)

    def save(self):
        SETTINGS_FILE.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2))

    def get(self, key, default=None):
        return self.settings.get(key, default or self.DEFAULTS.get(key))

    def set(self, key, value):
        self.settings[key] = value
        self.save()


class HistoryManager:
    """Manages transcription history."""

    def __init__(self):
        self.history = self._load()

    def _load(self):
        if HISTORY_FILE.exists():
            try:
                return json.loads(HISTORY_FILE.read_text())
            except Exception:
                return []
        return []

    def save(self):
        HISTORY_FILE.write_text(json.dumps(self.history, ensure_ascii=False, indent=2))

    def add(self, filename, filepath, text, duration_secs=0):
        word_count = len(text.split()) if text else 0
        entry = {
            "id": int(time.time() * 1000),
            "filename": filename,
            "original_path": filepath,
            "text": text,
            "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "duration_secs": round(duration_secs, 1),
            "chars": len(text),
            "words": word_count,
            "file_size": format_file_size(filepath),
        }
        self.history.insert(0, entry)
        self.save()
        return entry

    def delete(self, entry_id):
        self.history = [h for h in self.history if h["id"] != entry_id]
        self.save()

    def search(self, query):
        if not query.strip():
            return self.history
        q = query.lower()
        return [
            h for h in self.history
            if q in h["filename"].lower() or q in h["text"].lower()
        ]

    def clear_all(self):
        self.history = []
        self.save()


class AnimatedProgress(ctk.CTkFrame):
    """Sleek animated progress bar with gradient effect."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", height=36, **kwargs)
        self.animating = False
        self.pulse_pos = 0
        self._visible = False

        self.canvas = tk.Canvas(
            self, height=4, bg=COLORS["bg_main"],
            highlightthickness=0, bd=0
        )

        self.status_label = ctk.CTkLabel(
            self, text="", font=("SF Pro Display", 12),
            text_color=COLORS["text_dim"], height=20
        )

    def show(self):
        if not self._visible:
            self.canvas.pack(fill="x", padx=0, pady=(0, 2))
            self.status_label.pack(pady=(2, 0))
            self._visible = True

    def hide(self):
        if self._visible:
            self.canvas.pack_forget()
            self.status_label.pack_forget()
            self._visible = False

    def start_pulse(self, status="Transcrevendo..."):
        self.show()
        self.animating = True
        self.pulse_pos = -0.3
        self.status_label.configure(text=status)
        self._animate_pulse()

    def stop(self):
        self.animating = False
        self.canvas.delete("all")

    def set_status(self, text):
        self.status_label.configure(text=text)

    def set_complete(self, text):
        self.stop()
        self.status_label.configure(text=text, text_color=COLORS["success"])
        self.after(5000, lambda: self.hide())

    def _animate_pulse(self):
        if not self.animating:
            return
        self.canvas.delete("all")
        w = self.canvas.winfo_width() or 500
        h = 4

        self.canvas.create_rectangle(0, 0, w, h, fill=COLORS["progress_bg"], outline="")

        bar_w = int(w * 0.25)
        x = int(self.pulse_pos * (w + bar_w)) - bar_w

        # Gradient-like effect with multiple rectangles
        for i in range(3):
            alpha_offset = i * 8
            color = COLORS["accent"] if i == 1 else COLORS["accent_dim"]
            x_off = x + (i - 1) * 3
            self.canvas.create_rectangle(
                max(0, x_off), 0, min(w, x_off + bar_w), h,
                fill=color, outline=""
            )

        self.pulse_pos += 0.01
        if self.pulse_pos > 1.3:
            self.pulse_pos = -0.3

        self.after(16, self._animate_pulse)


class HistoryCard(ctk.CTkFrame):
    """A polished history entry card with hover effects."""

    def __init__(self, parent, entry, on_click, on_delete, is_selected=False, **kwargs):
        bg = COLORS["bg_card_selected"] if is_selected else COLORS["bg_card"]
        border = COLORS["accent"] if is_selected else COLORS["border"]

        super().__init__(
            parent, fg_color=bg,
            corner_radius=12, border_width=1,
            border_color=border, **kwargs
        )
        self.entry = entry
        self.on_click = on_click
        self._is_selected = is_selected

        self.configure(cursor="hand2")

        # --- Top row: icon + filename + date ---
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 2))

        # File type icon
        ext = os.path.splitext(entry["filename"])[1].lower()
        if ext in (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".opus", ".wma"):
            icon = "🎵"
        elif ext in (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"):
            icon = "🎬"
        else:
            icon = "📄"

        ctk.CTkLabel(
            top, text=icon, font=("SF Pro Display", 16),
            width=24
        ).pack(side="left", padx=(0, 6))

        name = entry["filename"]
        if len(name) > 32:
            name = name[:29] + "..."

        ctk.CTkLabel(
            top, text=name,
            font=("SF Pro Display", 13, "bold"),
            text_color=COLORS["text"], anchor="w"
        ).pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            top, text=entry["date"],
            font=("SF Pro Display", 10),
            text_color=COLORS["text_dim"]
        ).pack(side="right")

        # --- Preview text ---
        preview = entry["text"][:100].replace("\n", " ")
        if len(entry["text"]) > 100:
            preview += "..."

        ctk.CTkLabel(
            self, text=preview,
            font=("SF Pro Display", 11),
            text_color=COLORS["text_dim"],
            anchor="w", justify="left", wraplength=340
        ).pack(fill="x", padx=14, pady=(2, 4))

        # --- Bottom row: tags + delete ---
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=14, pady=(0, 10))

        # Stats tags
        tags_frame = ctk.CTkFrame(bottom, fg_color="transparent")
        tags_frame.pack(side="left")

        words = entry.get("words", len(entry["text"].split()))
        self._make_tag(tags_frame, f"{words} palavras")

        duration = entry.get("duration_secs", 0)
        if duration > 0:
            self._make_tag(tags_frame, f"⚡ {format_duration(duration)}")

        file_size = entry.get("file_size", "")
        if file_size:
            self._make_tag(tags_frame, file_size)

        # Delete button
        del_btn = ctk.CTkButton(
            bottom, text="✕", width=26, height=26,
            font=("SF Pro Display", 11),
            fg_color="transparent", hover_color="#3a1525",
            text_color=COLORS["text_dim"],
            corner_radius=6,
            command=lambda: on_delete(entry["id"])
        )
        del_btn.pack(side="right")

        # Bind click to all children
        self.bind("<Button-1>", lambda e: on_click(entry))
        for child in self.winfo_children():
            child.bind("<Button-1>", lambda e: on_click(entry))
            for grandchild in child.winfo_children():
                grandchild.bind("<Button-1>", lambda e: on_click(entry))
                for ggchild in grandchild.winfo_children():
                    ggchild.bind("<Button-1>", lambda e: on_click(entry))

    def _make_tag(self, parent, text):
        tag = ctk.CTkLabel(
            parent, text=text,
            font=("SF Pro Display", 10),
            text_color=COLORS["text_dim"],
            fg_color=COLORS["tag_bg"],
            corner_radius=4, height=22,
            padx=8
        )
        tag.pack(side="left", padx=(0, 4))
        tag.bind("<Button-1>", lambda e: self.on_click(self.entry))


class DropZone(ctk.CTkFrame):
    """Drag & drop zone overlay."""

    def __init__(self, parent, on_drop, **kwargs):
        super().__init__(parent, fg_color=COLORS["drop_zone"], corner_radius=16,
                         border_width=2, border_color=COLORS["border_accent"], **kwargs)
        self.on_drop = on_drop

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            inner, text="📂",
            font=("SF Pro Display", 48),
        ).pack(pady=(0, 8))

        ctk.CTkLabel(
            inner, text="Arraste o arquivo aqui",
            font=("SF Pro Display", 18, "bold"),
            text_color=COLORS["text"]
        ).pack()

        ctk.CTkLabel(
            inner, text="ou clique em 'Transcrever Arquivo'",
            font=("SF Pro Display", 13),
            text_color=COLORS["text_dim"]
        ).pack(pady=(4, 0))

        formats_text = "MP4 · MOV · MP3 · WAV · M4A · FLAC · OGG · WebM · MKV"
        ctk.CTkLabel(
            inner, text=formats_text,
            font=("SF Pro Display", 10),
            text_color=COLORS["text_muted"]
        ).pack(pady=(12, 0))


class StatsBar(ctk.CTkFrame):
    """Bottom stats bar for the text panel."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_card"], corner_radius=0, height=36, **kwargs)
        self.pack_propagate(False)

        self.stats_label = ctk.CTkLabel(
            self, text="",
            font=("SF Pro Display", 11),
            text_color=COLORS["text_dim"]
        )
        self.stats_label.pack(side="left", padx=16)

        self.path_label = ctk.CTkLabel(
            self, text="",
            font=("SF Pro Display", 10),
            text_color=COLORS["text_muted"]
        )
        self.path_label.pack(side="right", padx=16)

    def update_stats(self, entry):
        words = entry.get("words", len(entry["text"].split()))
        chars = entry.get("chars", len(entry["text"]))
        duration = entry.get("duration_secs", 0)
        dur_str = f"  ·  ⚡ {format_duration(duration)}" if duration else ""
        self.stats_label.configure(
            text=f"{words:,} palavras  ·  {chars:,} caracteres{dur_str}".replace(",", ".")
        )
        path = entry.get("original_path", "")
        if len(path) > 50:
            path = "..." + path[-47:]
        self.path_label.configure(text=path)

    def clear(self):
        self.stats_label.configure(text="")
        self.path_label.configure(text="")


class WhisperApp(ctk.CTk):
    """Main application window — v2.0 Premium."""

    def __init__(self):
        super().__init__()

        self.settings = SettingsManager()
        self.history_mgr = HistoryManager()
        self.is_transcribing = False
        self.selected_entry_id = None
        self.search_query = ""
        self._queue = []  # batch queue

        w = self.settings.get("window_width")
        h = self.settings.get("window_height")
        self.title("WhisperTranscribe")
        self.geometry(f"{w}x{h}")
        self.minsize(850, 600)
        self.configure(fg_color=COLORS["bg_dark"])

        # Keyboard shortcuts
        self.bind("<Command-o>", lambda e: self._pick_file())
        self.bind("<Command-n>", lambda e: self._pick_file())
        self.bind("<Command-f>", lambda e: self._focus_search())
        self.bind("<Command-c>", lambda e: self._copy_text())
        self.bind("<Command-e>", lambda e: self._export_txt())
        self.bind("<Escape>", lambda e: self._clear_search())

        # Enable drag & drop via tkinterdnd2 or fallback
        self._setup_dnd()

        self._build_ui()
        self._refresh_history()

        # Force window to front
        self.lift()
        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))
        self.focus_force()

    def _setup_dnd(self):
        """Setup drag and drop — try tkinterdnd2, fallback gracefully."""
        self._dnd_available = False
        try:
            # Try to register as a drop target using Tk DnD
            self.tk.call("package", "require", "tkdnd")
            self._dnd_available = True
        except Exception:
            pass

    def _build_ui(self):
        # === HEADER ===
        header = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"], height=80)
        header.pack(fill="x", padx=28, pady=(20, 0))
        header.pack_propagate(False)

        # Logo + title
        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.pack(side="left", fill="y")

        # Gradient-like W logo
        logo_frame = ctk.CTkFrame(
            title_frame, fg_color=COLORS["accent"],
            corner_radius=12, width=44, height=44
        )
        logo_frame.pack(side="left", padx=(0, 12))
        logo_frame.pack_propagate(False)

        ctk.CTkLabel(
            logo_frame, text="W",
            font=("SF Pro Display", 24, "bold"),
            text_color="#ffffff"
        ).place(relx=0.5, rely=0.5, anchor="center")

        title_text = ctk.CTkFrame(title_frame, fg_color="transparent")
        title_text.pack(side="left")

        ctk.CTkLabel(
            title_text, text="WhisperTranscribe",
            font=("SF Pro Display", 22, "bold"),
            text_color=COLORS["text"]
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_text, text="Transcrição inteligente de áudio e vídeo",
            font=("SF Pro Display", 12),
            text_color=COLORS["text_dim"]
        ).pack(anchor="w")

        # Right side: language selector + upload button
        right_header = ctk.CTkFrame(header, fg_color="transparent")
        right_header.pack(side="right", fill="y")

        # Language selector
        lang_frame = ctk.CTkFrame(right_header, fg_color="transparent")
        lang_frame.pack(side="left", padx=(0, 12), pady=18)

        ctk.CTkLabel(
            lang_frame, text="🌐",
            font=("SF Pro Display", 14)
        ).pack(side="left", padx=(0, 4))

        current_lang = self.settings.get("language_name")
        self.lang_var = ctk.StringVar(value=current_lang)
        self.lang_menu = ctk.CTkOptionMenu(
            lang_frame,
            values=list(LANGUAGES.keys()),
            variable=self.lang_var,
            command=self._on_language_change,
            font=("SF Pro Display", 12),
            fg_color=COLORS["bg_input"],
            button_color=COLORS["accent_dim"],
            button_hover_color=COLORS["accent"],
            dropdown_fg_color=COLORS["bg_card"],
            dropdown_hover_color=COLORS["bg_card_hover"],
            width=130, height=32,
            corner_radius=8
        )
        self.lang_menu.pack(side="left")

        # Upload button
        self.upload_btn = ctk.CTkButton(
            right_header, text="  ＋  Transcrever",
            font=("SF Pro Display", 14, "bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            corner_radius=10, height=42, width=180,
            command=self._pick_file
        )
        self.upload_btn.pack(side="right", pady=18)

        # === DIVIDER ===
        ctk.CTkFrame(self, fg_color=COLORS["divider"], height=1).pack(fill="x", padx=28, pady=(16, 0))

        # === MAIN CONTENT ===
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=28, pady=(16, 20))

        # --- LEFT: History panel ---
        left = ctk.CTkFrame(content, fg_color="transparent", width=380)
        left.pack(side="left", fill="both", padx=(0, 10))
        left.pack_propagate(False)

        # History header with count
        hist_header = ctk.CTkFrame(left, fg_color="transparent")
        hist_header.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            hist_header, text="📋 Histórico",
            font=("SF Pro Display", 15, "bold"),
            text_color=COLORS["text"]
        ).pack(side="left")

        self.history_count = ctk.CTkLabel(
            hist_header, text="0",
            font=("SF Pro Display", 11),
            text_color=COLORS["text_dim"],
            fg_color=COLORS["tag_bg"],
            corner_radius=10, width=30, height=22
        )
        self.history_count.pack(side="left", padx=(8, 0))

        # Clear all button
        self.clear_btn = ctk.CTkButton(
            hist_header, text="Limpar",
            font=("SF Pro Display", 11),
            fg_color="transparent", hover_color=COLORS["bg_card"],
            text_color=COLORS["text_dim"],
            corner_radius=6, height=26, width=60,
            command=self._clear_all_history
        )
        self.clear_btn.pack(side="right")

        # Search bar
        search_frame = ctk.CTkFrame(left, fg_color=COLORS["bg_input"],
                                     corner_radius=10, border_width=1,
                                     border_color=COLORS["border"], height=38)
        search_frame.pack(fill="x", pady=(0, 10))
        search_frame.pack_propagate(False)

        ctk.CTkLabel(
            search_frame, text="🔍",
            font=("SF Pro Display", 13),
            width=30
        ).pack(side="left", padx=(10, 0))

        self.search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="Buscar transcrições... (⌘F)",
            font=("SF Pro Display", 12),
            fg_color="transparent",
            border_width=0,
            text_color=COLORS["text"],
            placeholder_text_color=COLORS["text_muted"],
            height=36
        )
        self.search_entry.pack(side="left", fill="both", expand=True, padx=(4, 10))
        self.search_entry.bind("<KeyRelease>", self._on_search)

        # History scroll
        self.history_scroll = ctk.CTkScrollableFrame(
            left, fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"]
        )
        self.history_scroll.pack(fill="both", expand=True)

        # --- RIGHT: Content panel ---
        right = ctk.CTkFrame(
            content, fg_color=COLORS["bg_main"],
            corner_radius=14, border_width=1,
            border_color=COLORS["border"]
        )
        right.pack(side="right", fill="both", expand=True, padx=(10, 0))

        # Right header with actions
        right_header_frame = ctk.CTkFrame(right, fg_color="transparent")
        right_header_frame.pack(fill="x", padx=18, pady=(16, 4))

        self.preview_title = ctk.CTkLabel(
            right_header_frame, text="",
            font=("SF Pro Display", 15, "bold"),
            text_color=COLORS["text"]
        )
        self.preview_title.pack(side="left")

        # Action buttons frame
        self.actions_frame = ctk.CTkFrame(right_header_frame, fg_color="transparent")

        # Export TXT button
        self.export_btn = ctk.CTkButton(
            self.actions_frame, text="💾 Exportar",
            font=("SF Pro Display", 12),
            fg_color=COLORS["bg_input"],
            hover_color=COLORS["bg_card_hover"],
            text_color=COLORS["text_secondary"],
            corner_radius=8, height=32, width=100,
            border_width=1, border_color=COLORS["border"],
            command=self._export_txt
        )
        self.export_btn.pack(side="left", padx=(0, 6))

        # Copy button
        self.copy_btn = ctk.CTkButton(
            self.actions_frame, text="📋 Copiar",
            font=("SF Pro Display", 12, "bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            corner_radius=8, height=32, width=100,
            command=self._copy_text
        )
        self.copy_btn.pack(side="left")

        # Progress bar
        self.progress = AnimatedProgress(right)
        self.progress.pack(fill="x", padx=18, pady=(4, 0))

        # Content area (text or drop zone)
        self.content_container = ctk.CTkFrame(right, fg_color="transparent")
        self.content_container.pack(fill="both", expand=True, padx=18, pady=(8, 0))

        # Text area
        self.text_area = ctk.CTkTextbox(
            self.content_container,
            font=("SF Mono", 13),
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text"],
            corner_radius=10, border_width=1,
            border_color=COLORS["border"],
            wrap="word", spacing1=2, spacing2=1
        )

        # Drop zone (shown when no entry selected)
        self.drop_zone = DropZone(self.content_container, on_drop=self._on_file_drop)

        # Stats bar
        self.stats_bar = StatsBar(right)
        self.stats_bar.pack(fill="x", side="bottom")

        # Show drop zone by default
        self._show_drop_zone()

    def _show_drop_zone(self):
        """Show the drop zone, hide text area."""
        self.text_area.pack_forget()
        self.drop_zone.pack(fill="both", expand=True)
        self.actions_frame.pack_forget()
        self.preview_title.configure(text="Comece sua transcrição")
        self.stats_bar.clear()

    def _show_text_area(self):
        """Show text area, hide drop zone."""
        self.drop_zone.pack_forget()
        self.text_area.pack(fill="both", expand=True)
        self.actions_frame.pack(side="right")

    def _on_language_change(self, choice):
        lang_code = LANGUAGES.get(choice)
        self.settings.set("language", lang_code)
        self.settings.set("language_name", choice)

    def _focus_search(self):
        self.search_entry.focus_set()

    def _clear_search(self):
        self.search_entry.delete(0, "end")
        self.search_query = ""
        self._refresh_history()

    def _on_search(self, event=None):
        query = self.search_entry.get()
        if query != self.search_query:
            self.search_query = query
            self._refresh_history()

    def _refresh_history(self):
        for widget in self.history_scroll.winfo_children():
            widget.destroy()

        entries = self.history_mgr.search(self.search_query) if self.search_query else self.history_mgr.history

        self.history_count.configure(text=str(len(entries)))

        if not entries:
            if self.search_query:
                msg = f"Nenhum resultado para '{self.search_query}'"
            else:
                msg = "Nenhuma transcrição ainda.\n\nArraste um arquivo ou clique em\n'＋ Transcrever' para começar."

            ctk.CTkLabel(
                self.history_scroll,
                text=msg,
                font=("SF Pro Display", 13),
                text_color=COLORS["text_dim"], justify="center"
            ).pack(pady=60)
            return

        for entry in entries:
            is_selected = entry["id"] == self.selected_entry_id
            card = HistoryCard(
                self.history_scroll, entry,
                on_click=self._show_entry,
                on_delete=self._delete_entry,
                is_selected=is_selected
            )
            card.pack(fill="x", pady=3)

    def _show_entry(self, entry):
        self.selected_entry_id = entry["id"]
        self._show_text_area()

        self.preview_title.configure(text=entry["filename"])
        self.stats_bar.update_stats(entry)

        self.text_area.configure(state="normal")
        self.text_area.delete("0.0", "end")
        self.text_area.insert("0.0", entry["text"])
        self.text_area.configure(state="disabled")

        self._refresh_history()

    def _delete_entry(self, entry_id):
        self.history_mgr.delete(entry_id)
        if self.selected_entry_id == entry_id:
            self.selected_entry_id = None
            self._show_drop_zone()
        self._refresh_history()

    def _clear_all_history(self):
        if not self.history_mgr.history:
            return
        self.history_mgr.clear_all()
        self.selected_entry_id = None
        self._show_drop_zone()
        self._refresh_history()

    def _copy_text(self, event=None):
        self.text_area.configure(state="normal")
        text = self.text_area.get("0.0", "end").strip()
        self.text_area.configure(state="disabled")

        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            original = self.copy_btn.cget("text")
            self.copy_btn.configure(text="✓ Copiado!", fg_color=COLORS["success"])
            self.after(2000, lambda: self.copy_btn.configure(
                text=original, fg_color=COLORS["accent"]
            ))

    def _export_txt(self, event=None):
        """Export current transcription as TXT file."""
        self.text_area.configure(state="normal")
        text = self.text_area.get("0.0", "end").strip()
        self.text_area.configure(state="disabled")

        if not text:
            return

        default_name = "transcricao.txt"
        if self.selected_entry_id:
            for h in self.history_mgr.history:
                if h["id"] == self.selected_entry_id:
                    base = os.path.splitext(h["filename"])[0]
                    default_name = f"{base}_transcricao.txt"
                    break

        filepath = filedialog.asksaveasfilename(
            title="Exportar Transcrição",
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=[("Texto", "*.txt"), ("Todos", "*.*")]
        )
        if filepath:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
            self.export_btn.configure(text="✓ Salvo!", fg_color=COLORS["success_dim"])
            self.after(2000, lambda: self.export_btn.configure(
                text="💾 Exportar", fg_color=COLORS["bg_input"]
            ))

    def _on_file_drop(self, filepath):
        """Handle file drop."""
        if self.is_transcribing:
            return
        if os.path.isfile(filepath):
            ext = os.path.splitext(filepath)[1].lower()
            if ext in AUDIO_VIDEO_EXTENSIONS:
                self._start_transcription(filepath)

    def _pick_file(self, event=None):
        if self.is_transcribing:
            return

        filetypes = [
            ("Áudio e Vídeo", " ".join(f"*{ext}" for ext in sorted(AUDIO_VIDEO_EXTENSIONS))),
            ("Todos os arquivos", "*.*")
        ]
        filepath = filedialog.askopenfilename(
            title="Selecione o áudio ou vídeo",
            filetypes=filetypes
        )
        if not filepath:
            return

        self._start_transcription(filepath)

    def _start_transcription(self, filepath):
        self.is_transcribing = True
        filename = os.path.basename(filepath)

        self.upload_btn.configure(state="disabled", text="⏳ Processando...")
        self._show_text_area()
        self.preview_title.configure(text=filename)
        self.actions_frame.pack_forget()
        self.stats_bar.clear()

        self.text_area.configure(state="normal")
        self.text_area.delete("0.0", "end")
        self.text_area.insert("0.0", "Preparando transcrição...\n\nCarregando modelo WhisperKit...")
        self.text_area.configure(state="disabled")

        file_size = format_file_size(filepath)
        self.progress.start_pulse(f"Transcrevendo {filename} ({file_size})...")

        thread = threading.Thread(
            target=self._run_transcription,
            args=(filepath, filename),
            daemon=True
        )
        thread.start()

    def _run_transcription(self, filepath, filename):
        start = time.time()
        try:
            self.after(0, lambda: self.progress.set_status(
                "Carregando modelo e processando áudio..."
            ))

            lang = self.settings.get("language")
            cmd = [WHISPERKIT, "transcribe", "--audio-path", filepath]
            if lang:
                cmd += ["--language", lang]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600
            )

            output = result.stdout
            lines = output.strip().split("\n")

            text_lines = []
            skip_prefixes = (
                "[WhisperKit]", "Pipeline", "  Token", "  Audio",
                "  First", "  Total", "  Model", "  Fallback",
                "  Decode", "-=-", "  Speed", "  Real", "  Number"
            )
            for line in lines:
                stripped = line.strip()
                if stripped and not any(stripped.startswith(p) for p in skip_prefixes):
                    text_lines.append(stripped)

            text = " ".join(text_lines).strip()
            elapsed = time.time() - start

            if not text:
                self.after(0, lambda: self._transcription_error(
                    "Transcrição vazia. O arquivo pode não conter áudio audível.\n\n"
                    "Dicas:\n"
                    "• Verifique se o arquivo tem áudio\n"
                    "• Tente um formato diferente (MP4, MP3, WAV)\n"
                    "• Verifique o volume do áudio"
                ))
                return

            entry = self.history_mgr.add(filename, filepath, text, elapsed)

            # Save .txt next to original if setting enabled
            if self.settings.get("save_txt"):
                txt_path = os.path.splitext(filepath)[0] + "_transcricao.txt"
                try:
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(text)
                except Exception:
                    pass

            self.after(0, lambda: self._transcription_done(entry, elapsed))

        except subprocess.TimeoutExpired:
            self.after(0, lambda: self._transcription_error(
                "⏱ Timeout — o arquivo é muito longo.\n\n"
                "O limite é de 10 minutos de processamento.\n"
                "Tente um arquivo menor ou corte o áudio."
            ))
        except Exception as e:
            self.after(0, lambda: self._transcription_error(
                f"Erro inesperado:\n\n{str(e)}"
            ))

    def _transcription_done(self, entry, elapsed):
        self.is_transcribing = False
        self.selected_entry_id = entry["id"]

        time_str = format_duration(elapsed)
        words = entry.get("words", 0)
        self.progress.set_complete(f"✓ Concluído em {time_str} — {words} palavras transcritas")

        self.upload_btn.configure(state="normal", text="  ＋  Transcrever")
        self.preview_title.configure(text=entry["filename"])
        self.actions_frame.pack(side="right")
        self.stats_bar.update_stats(entry)

        self.text_area.configure(state="normal")
        self.text_area.delete("0.0", "end")
        self.text_area.insert("0.0", entry["text"])
        self.text_area.configure(state="disabled")

        self._refresh_history()

    def _transcription_error(self, msg):
        self.is_transcribing = False
        self.progress.stop()
        self.progress.hide()
        self.upload_btn.configure(state="normal", text="  ＋  Transcrever")

        self.text_area.configure(state="normal")
        self.text_area.delete("0.0", "end")
        self.text_area.insert("0.0", msg)
        self.text_area.configure(state="disabled")


if __name__ == "__main__":
    app = WhisperApp()
    app.mainloop()
