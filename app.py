#!/usr/bin/env python3
"""WhisperTranscribe v2.0 — App premium de transcrição de áudio/vídeo."""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import threading
import os
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from shared import COLORS, AUDIO_VIDEO_EXTENSIONS, WHISPERKIT, format_duration, format_file_size
from batch_queue import BatchProcessor, QueuePanel
from export_modal import ExportModal
from whisper_server import WhisperServer

# --- Config ---
HISTORY_DIR = Path.home() / ".whisper_transcribe"
HISTORY_FILE = HISTORY_DIR / "history.json"
SETTINGS_FILE = HISTORY_DIR / "settings.json"
LOG_FILE = HISTORY_DIR / "app.log"

HISTORY_DIR.mkdir(exist_ok=True)

# --- Logging ---
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("WhisperTranscribe")

# --- Theme ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

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
                saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                merged = {**self.DEFAULTS, **saved}
                return merged
            except Exception:
                return dict(self.DEFAULTS)
        return dict(self.DEFAULTS)

    def save(self):
        SETTINGS_FILE.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, key, default=None):
        return self.settings.get(key, default if default is not None else self.DEFAULTS.get(key))

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
                return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def save(self):
        HISTORY_FILE.write_text(json.dumps(self.history, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, filename, filepath, text, duration_secs=0, segments=None):
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
        if segments:
            entry["segments"] = segments
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
        # Tag delete button so we can skip it in click binding
        del_btn._is_delete_btn = True

        # Bind click to all children EXCEPT the delete button
        def _bind_click(widget):
            if getattr(widget, '_is_delete_btn', False):
                return
            widget.bind("<Button-1>", lambda e: on_click(entry))
            for child in widget.winfo_children():
                _bind_click(child)

        _bind_click(self)

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
    """Drag & drop zone overlay — clickable to open file picker."""

    def __init__(self, parent, on_drop, on_click=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["drop_zone"], corner_radius=16,
                         border_width=2, border_color=COLORS["border_accent"], **kwargs)
        self.on_drop = on_drop
        self.on_click = on_click
        self.configure(cursor="hand2")

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
            inner, text="ou clique para selecionar",
            font=("SF Pro Display", 13),
            text_color=COLORS["text_dim"]
        ).pack(pady=(4, 0))

        formats_text = "MP4 · MOV · MP3 · WAV · M4A · FLAC · OGG · WebM · MKV"
        ctk.CTkLabel(
            inner, text=formats_text,
            font=("SF Pro Display", 10),
            text_color=COLORS["text_muted"]
        ).pack(pady=(12, 0))

        # Make the entire zone clickable
        self.bind("<Button-1>", self._handle_click)
        inner.bind("<Button-1>", self._handle_click)
        for child in inner.winfo_children():
            child.bind("<Button-1>", self._handle_click)

    def _handle_click(self, event=None):
        if self.on_click:
            self.on_click()


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
        log.info("=== WhisperTranscribe starting ===")

        self.settings = SettingsManager()
        self.history_mgr = HistoryManager()
        self.is_transcribing = False
        self.selected_entry_id = None
        self.search_query = ""
        self._transcription_cancelled = False
        self._current_process = None
        self._elapsed_timer = None
        self.batch = BatchProcessor()
        self.server = WhisperServer()
        self._server_ready = False

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
        self.bind("<Command-e>", lambda e: self._export_txt())
        self.bind("<Escape>", lambda e: self._clear_search())

        self._build_ui()
        self._refresh_history()
        log.info("UI built, checking dependencies...")

        # First-run dependency check
        if not self._check_dependencies():
            log.warning("Dependencies missing, aborting init")
            return

        log.info("Dependencies OK, starting server...")
        # Show loading state and start server
        self._show_server_loading()

        # Force window to front
        self.lift()
        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))
        self.focus_force()

        # Defer DnD setup to after mainloop is running (avoids GIL crash)
        self.after(500, self._setup_native_dnd)

        # Shut down server when window closes
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_native_dnd(self):
        """Setup native macOS drag-and-drop via pyobjc."""
        try:
            from macos_drop import enable_drop
            enable_drop(self, self._on_files_dropped, extensions=AUDIO_VIDEO_EXTENSIONS)
        except Exception as e:
            print(f"[WhisperTranscribe] Drag & drop indisponível: {e}")

        # Also handle macOS "Open With" / dock icon drops
        try:
            self.createcommand("::tk::mac::OpenDocument", self._tk_open_document)
        except Exception:
            pass

    def _show_server_loading(self):
        """Show loading state while WhisperKit server starts."""
        self.upload_btn.configure(state="disabled", text="⏳ Iniciando...")
        self.progress.start_pulse("Carregando modelo WhisperKit...")
        lang = self.settings.get("language")
        self.server.start(
            language=lang,
            on_ready=lambda: self.after(0, self._on_server_ready),
            on_error=lambda e: self.after(0, lambda: self._on_server_error(e)),
        )

    def _on_server_ready(self):
        """Called when WhisperKit server is ready."""
        log.info("Server READY")
        self._server_ready = True
        self.progress.set_complete("✓ WhisperKit pronto")
        self._restore_upload_btn()

    def _on_server_error(self, error_msg):
        """Called if WhisperKit server fails to start."""
        log.error(f"Server FAILED: {error_msg}")
        self._server_ready = False
        self.progress.stop()
        self.progress.set_status(f"✕ Erro: {error_msg}")
        self._restore_upload_btn()

    def _check_dependencies(self):
        """Check all dependencies and show guidance for missing ones."""
        missing = []

        # Check paths directly (shutil.which fails inside .app bundles due to minimal PATH)
        brew_paths = ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"]
        whisperkit_paths = ["/opt/homebrew/bin/whisperkit-cli", "/usr/local/bin/whisperkit-cli"]

        has_brew = any(os.path.exists(p) for p in brew_paths)
        has_whisperkit = os.path.exists(WHISPERKIT) or any(os.path.exists(p) for p in whisperkit_paths)

        if not has_brew:
            missing.append(
                "Homebrew (gerenciador de pacotes):\n"
                '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
            )

        if not has_whisperkit:
            missing.append(
                "WhisperKit CLI (motor de transcrição):\n"
                "  brew install whisperkit-cli"
            )

        if not missing:
            return True

        # Build the message
        steps = "\n\n".join(f"{i+1}. {m}" for i, m in enumerate(missing))
        messagebox.showwarning(
            "Dependências necessárias",
            f"Para usar o WhisperTranscribe, instale no Terminal:\n\n"
            f"{steps}\n\n"
            f"Após instalar, reinicie o WhisperTranscribe.",
            parent=self
        )

        self.upload_btn.configure(state="disabled", text="Dependências ausentes")
        self.progress.set_status("Instale as dependências e reinicie o app")

        # Show install instructions in the text area
        self._show_text_area()
        self.preview_title.configure(text="Instalação necessária")
        self.text_area.configure(state="normal")
        self.text_area.delete("0.0", "end")

        instructions = "Como instalar as dependências\n"
        instructions += "=" * 40 + "\n\n"
        instructions += "Abra o Terminal (Cmd+Espaço, digite 'Terminal') e execute:\n\n"

        if not has_brew:
            instructions += '1. Instalar Homebrew:\n'
            instructions += '   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"\n\n'

        if not has_whisperkit:
            step = "2" if not has_brew else "1"
            instructions += f'{step}. Instalar WhisperKit CLI:\n'
            instructions += '   brew install whisperkit-cli\n\n'

        instructions += "Depois feche e reabra o WhisperTranscribe."

        self.text_area.insert("0.0", instructions)
        self.text_area.configure(state="disabled")
        return False

    def _on_close(self):
        """Shutdown server and close app."""
        self.server.stop()
        self.destroy()

    def _show_about(self):
        """Show About dialog."""
        about = ctk.CTkToplevel(self)
        about.title("Sobre")
        about.configure(fg_color=COLORS["bg_main"])
        about.resizable(False, False)
        w, h = 360, 280
        px = self.winfo_rootx() + (self.winfo_width() - w) // 2
        py = self.winfo_rooty() + (self.winfo_height() - h) // 2
        about.geometry(f"{w}x{h}+{px}+{py}")
        about.transient(self)
        about.grab_set()

        # Logo
        logo = ctk.CTkFrame(about, fg_color=COLORS["accent"], corner_radius=16, width=56, height=56)
        logo.pack(pady=(24, 8))
        logo.pack_propagate(False)
        ctk.CTkLabel(logo, text="W", font=("SF Pro Display", 28, "bold"), text_color="#fff").place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(about, text="WhisperTranscribe", font=("SF Pro Display", 20, "bold"), text_color=COLORS["text"]).pack()
        ctk.CTkLabel(about, text="v2.0.0", font=("SF Pro Display", 13), text_color=COLORS["text_dim"]).pack(pady=(2, 8))
        ctk.CTkLabel(about, text="Transcrição inteligente de áudio e vídeo\npara macOS com WhisperKit", font=("SF Pro Display", 12), text_color=COLORS["text_secondary"], justify="center").pack()
        ctk.CTkLabel(about, text="Atalhos: Cmd+O (abrir) · Cmd+F (buscar) · Cmd+E (exportar)", font=("SF Pro Display", 10), text_color=COLORS["text_muted"], justify="center").pack(pady=(12, 0))
        ctk.CTkButton(about, text="Fechar", width=80, height=28, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], command=about.destroy).pack(pady=(12, 0))

    def _on_files_dropped(self, file_paths):
        """Handle files dropped via native macOS drag-and-drop."""
        log.info(f"Files dropped: {len(file_paths)} files")
        if file_paths:
            self.after(0, lambda fps=list(file_paths): self._add_to_queue(fps))

    def _tk_open_document(self, *args):
        """Handle macOS open document events (file drag onto dock icon)."""
        for filepath in args:
            filepath = str(filepath).strip("{}")
            if os.path.isfile(filepath):
                ext = os.path.splitext(filepath)[1].lower()
                if ext in AUDIO_VIDEO_EXTENSIONS:
                    self.after(0, lambda p=filepath: self._on_file_drop(p))
                    return

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

        # About button
        ctk.CTkButton(
            right_header, text="?", width=32, height=32,
            font=("SF Pro Display", 14),
            fg_color="transparent", hover_color=COLORS["bg_card"],
            text_color=COLORS["text_dim"],
            corner_radius=8,
            command=self._show_about
        ).pack(side="left", padx=(0, 6), pady=22)

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

        # Export all button
        self.export_all_btn = ctk.CTkButton(
            hist_header, text="Exportar",
            font=("SF Pro Display", 11),
            fg_color="transparent", hover_color=COLORS["bg_card"],
            text_color=COLORS["text_dim"],
            corner_radius=6, height=26, width=70,
            command=self._open_export_modal
        )
        self.export_all_btn.pack(side="right", padx=(0, 4))

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

        # Queue panel (hidden by default)
        self.queue_panel = QueuePanel(
            left,
            on_cancel_all=self._cancel_batch,
            on_remove_item=self._remove_from_queue
        )

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

        # Close button (back to drop zone)
        self.close_btn = ctk.CTkButton(
            right_header_frame, text="✕", width=28, height=28,
            font=("SF Pro Display", 13),
            fg_color="transparent", hover_color=COLORS["bg_card_hover"],
            text_color=COLORS["text_dim"],
            corner_radius=6,
            command=self._close_preview
        )

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
        self.drop_zone = DropZone(self.content_container, on_drop=self._on_file_drop, on_click=self._pick_file)

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
        self.close_btn.pack_forget()
        self.preview_title.configure(text="Comece sua transcrição")
        self.stats_bar.clear()
        self.progress.stop()
        self.progress.hide()

    def _show_text_area(self):
        """Show text area, hide drop zone."""
        self.drop_zone.pack_forget()
        self.text_area.pack(fill="both", expand=True)
        self.close_btn.pack(side="right", padx=(6, 0))
        self.actions_frame.pack(side="right")

    def _close_preview(self):
        """Close the current transcription preview and return to drop zone."""
        self.selected_entry_id = None
        self._show_drop_zone()
        self._refresh_history()

    def _on_language_change(self, choice):
        lang_code = LANGUAGES.get(choice)
        self.settings.set("language", lang_code)
        self.settings.set("language_name", choice)
        # Restart server with new language if not transcribing
        if not self.is_transcribing:
            self._server_ready = False
            self.server.stop()
            self._show_server_loading()

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

        self._history_entries = (
            self.history_mgr.search(self.search_query)
            if self.search_query else self.history_mgr.history
        )
        self._history_rendered = 0

        self.history_count.configure(text=str(len(self._history_entries)))

        if not self._history_entries:
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

        self._render_history_batch()

    def _render_history_batch(self, batch_size=30):
        """Render the next batch of history cards (lazy loading)."""
        entries = self._history_entries
        start = self._history_rendered
        end = min(start + batch_size, len(entries))

        for entry in entries[start:end]:
            is_selected = entry["id"] == self.selected_entry_id
            card = HistoryCard(
                self.history_scroll, entry,
                on_click=self._show_entry,
                on_delete=self._delete_entry,
                is_selected=is_selected
            )
            card.pack(fill="x", pady=3)

        self._history_rendered = end

        # Add "load more" button if there are remaining entries
        if end < len(entries):
            remaining = len(entries) - end
            self._load_more_btn = ctk.CTkButton(
                self.history_scroll,
                text=f"Carregar mais ({remaining} restantes)",
                font=("SF Pro Display", 12),
                fg_color=COLORS["bg_card"],
                hover_color=COLORS["bg_card_hover"],
                text_color=COLORS["text_dim"],
                corner_radius=8, height=32,
                command=self._load_more_history
            )
            self._load_more_btn.pack(fill="x", pady=(6, 3))

    def _load_more_history(self):
        """Load more history entries."""
        if hasattr(self, '_load_more_btn'):
            self._load_more_btn.destroy()
        self._render_history_batch()

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
        confirm = messagebox.askyesno(
            "Limpar histórico",
            f"Tem certeza que deseja apagar todas as {len(self.history_mgr.history)} transcrições?\n\nEsta ação não pode ser desfeita.",
            parent=self
        )
        if not confirm:
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
        """Handle single file drop."""
        if os.path.isfile(filepath):
            ext = os.path.splitext(filepath)[1].lower()
            if ext in AUDIO_VIDEO_EXTENSIONS:
                self._add_to_queue([filepath])

    def _pick_file(self, event=None):
        filetypes = [
            ("Áudio e Vídeo", " ".join(f"*{ext}" for ext in sorted(AUDIO_VIDEO_EXTENSIONS))),
            ("Todos os arquivos", "*.*")
        ]
        filepaths = filedialog.askopenfilenames(
            title="Selecione áudios ou vídeos",
            filetypes=filetypes
        )
        if not filepaths:
            return
        valid = [
            fp for fp in filepaths
            if os.path.isfile(fp) and os.path.splitext(fp)[1].lower() in AUDIO_VIDEO_EXTENSIONS
        ]
        if valid:
            self._add_to_queue(valid)

    # --- Batch queue ---

    def _add_to_queue(self, filepaths):
        """Add files to the batch queue and start processing if idle."""
        log.info(f"_add_to_queue: {len(filepaths)} files, server_ready={self._server_ready}, is_ready={self.server.is_ready}")
        if not self._server_ready and not self.server.is_ready:
            log.warning("Server not ready, retrying in 2s...")
            self.progress.set_status("Aguardando servidor iniciar...")
            # Retry after 2s
            self.after(2000, lambda fps=filepaths: self._add_to_queue(fps))
            return
        self.batch.add_files(filepaths)
        self._update_queue_panel()
        if not self.is_transcribing:
            self._process_next_in_queue()

    def _process_next_in_queue(self):
        """Start transcribing the current processing item in the queue."""
        current = self.batch.current_file()
        if current:
            self._start_transcription(current["filepath"])
        else:
            # Queue finished
            self._on_queue_finished()

    def _update_queue_panel(self):
        """Refresh the queue panel UI."""
        queue = self.batch.get_queue()
        if queue:
            self.queue_panel.set_items(queue)
            self.queue_panel.show()
        else:
            self.queue_panel.hide()

    def _cancel_batch(self):
        """Cancel all remaining items in the queue."""
        self.batch.cancel_all()
        self._cancel_transcription()
        self._update_queue_panel()

    def _remove_from_queue(self, filepath):
        """Remove a waiting item from the queue."""
        self.batch.remove_file(filepath)
        self._update_queue_panel()

    def _on_queue_finished(self):
        """Called when all items in the queue have been processed."""
        self.is_transcribing = False
        self._restore_upload_btn()
        self._update_queue_panel()
        stats = self.batch.stats
        if stats["completed"] > 0:
            msg = (
                f"✓ Fila concluída — {stats['completed']} transcritos"
                + (f", {stats['errors']} com erro" if stats["errors"] else "")
            )
            self.progress.set_complete(msg)
            # macOS notification
            self._send_notification("WhisperTranscribe", msg)
        # Clear the batch queue
        self.batch = BatchProcessor()
        self._update_queue_panel()

    def _send_notification(self, title, message):
        """Send a macOS notification."""
        try:
            os.system(
                f'osascript -e \'display notification "{message}" with title "{title}"\''
            )
        except Exception:
            pass

    def _open_export_modal(self):
        """Open the bulk export modal."""
        if not self.history_mgr.history:
            return
        ExportModal(self, self.history_mgr.history)

    def _start_transcription(self, filepath):
        self.is_transcribing = True
        self._transcription_cancelled = False
        self._current_process = None
        self._elapsed_timer = None
        filename = os.path.basename(filepath)

        self.upload_btn.configure(
            state="normal", text="✕ Cancelar",
            fg_color=COLORS["danger"], hover_color=COLORS["danger_hover"],
            command=self._cancel_transcription
        )
        self._show_text_area()
        self.preview_title.configure(text=filename)
        self.actions_frame.pack_forget()
        self.close_btn.pack_forget()
        self.stats_bar.clear()

        self.text_area.configure(state="normal")
        self.text_area.delete("0.0", "end")
        self.text_area.insert("0.0", "Transcrevendo...")
        self.text_area.configure(state="disabled")

        file_size = format_file_size(filepath)
        self.progress.start_pulse(f"Transcrevendo {filename} ({file_size})...")

        thread = threading.Thread(
            target=self._run_transcription,
            args=(filepath, filename),
            daemon=True
        )
        thread.start()

    def _restart_server_and_retry(self, filepath, filename):
        """Restart the WhisperKit server and retry the transcription."""
        self.after(0, lambda: self.progress.set_status(
            "Reiniciando servidor WhisperKit..."
        ))
        lang = self.settings.get("language")
        ready_event = threading.Event()
        error_holder = {}

        def on_ready():
            self._server_ready = True
            ready_event.set()

        def on_error(e):
            error_holder["msg"] = e
            ready_event.set()

        self.server.restart(language=lang, on_ready=on_ready, on_error=on_error)
        ready_event.wait(timeout=120)

        if "msg" in error_holder:
            raise RuntimeError(f"Falha ao reiniciar servidor: {error_holder['msg']}")
        if not self.server.is_ready:
            raise RuntimeError("Timeout reiniciando servidor WhisperKit")

    def _run_transcription(self, filepath, filename):
        log.info(f"_run_transcription START: {filename} (server_ready={self.server.is_ready})")
        start = time.time()
        retried = False
        try:
            self.after(0, lambda: self.progress.set_status(
                f"Transcrevendo {filename}..."
            ))

            # Start elapsed timer
            def update_elapsed():
                if not self._transcription_cancelled:
                    elapsed = time.time() - start
                    self.after(0, lambda e=elapsed: self.progress.set_status(
                        f"Transcrevendo {filename}... ({format_duration(e)})"
                    ))
                    self._elapsed_timer = self.after(1000, update_elapsed)
            self.after(0, update_elapsed)

            lang = self.settings.get("language")

            segments = None

            # Use server API if available, fallback to subprocess
            if self.server.is_ready:
                try:
                    log.info(f"Sending to server API: {filename}")
                    result = self.server.transcribe(filepath, language=lang)
                    text = result.get("text", "").strip()
                    segments = result.get("segments", [])
                    log.info(f"Transcription OK: {filename} ({len(text)} chars)")
                except RuntimeError as e:
                    log.error(f"Server error during transcription: {e}")
                    if not retried and not self._transcription_cancelled:
                        # Server died — restart and retry once
                        retried = True
                        self._restart_server_and_retry(filepath, filename)
                        self.after(0, lambda: self.progress.set_status(
                            f"Retomando transcrição de {filename}..."
                        ))
                        result = self.server.transcribe(filepath, language=lang)
                        text = result.get("text", "").strip()
                        segments = result.get("segments", [])
                    else:
                        raise
            else:
                # Fallback: direct subprocess call
                cmd = [WHISPERKIT, "transcribe", "--audio-path", filepath]
                if lang:
                    cmd += ["--language", lang]
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                self._current_process = proc
                stdout, stderr = proc.communicate(timeout=600)

                skip_prefixes = (
                    "[WhisperKit]", "Pipeline", "  Token", "  Audio",
                    "  First", "  Total", "  Model", "  Fallback",
                    "  Decode", "-=-", "  Speed", "  Real", "  Number"
                )
                text_lines = []
                for line in stdout.strip().split("\n"):
                    stripped = line.strip()
                    if stripped and not any(stripped.startswith(p) for p in skip_prefixes):
                        text_lines.append(stripped)
                text = " ".join(text_lines).strip()

            # Stop elapsed timer (dispatch to main thread)
            self.after(0, self._stop_elapsed_timer)

            if self._transcription_cancelled:
                return

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

            entry = self.history_mgr.add(filename, filepath, text, elapsed, segments=segments)

            # Save .txt next to original if setting enabled
            if self.settings.get("save_txt"):
                txt_path = os.path.splitext(filepath)[0] + "_transcricao.txt"
                try:
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(text)
                except Exception:
                    pass

            self.after(0, lambda: self._transcription_done(entry, elapsed))

        except Exception as e:
            log.error(f"_run_transcription EXCEPTION: {type(e).__name__}: {e}", exc_info=True)
            self.after(0, self._stop_elapsed_timer)
            self.after(0, lambda: self._transcription_error(
                f"Erro inesperado:\n\n{str(e)}"
            ))

    def _stop_elapsed_timer(self):
        """Stop the elapsed timer (must be called from main thread)."""
        if self._elapsed_timer:
            try:
                self.after_cancel(self._elapsed_timer)
            except Exception:
                pass
            self._elapsed_timer = None

    def _cancel_transcription(self):
        """Cancel the running transcription."""
        self._transcription_cancelled = True
        if self._current_process and self._current_process.poll() is None:
            self._current_process.kill()
        self._stop_elapsed_timer()
        self.is_transcribing = False
        self._restore_upload_btn()
        self.selected_entry_id = None
        self._show_drop_zone()

    def _restore_upload_btn(self):
        """Restore the upload button to its default state."""
        self.upload_btn.configure(
            state="normal", text="  ＋  Transcrever",
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            command=self._pick_file
        )

    def _transcription_done(self, entry, elapsed):
        self.is_transcribing = False
        self.selected_entry_id = entry["id"]

        time_str = format_duration(elapsed)
        words = entry.get("words", 0)

        self.preview_title.configure(text=entry["filename"])
        self.close_btn.pack(side="right", padx=(6, 0))
        self.actions_frame.pack(side="right")
        self.stats_bar.update_stats(entry)

        self.text_area.configure(state="normal")
        self.text_area.delete("0.0", "end")
        self.text_area.insert("0.0", entry["text"])
        self.text_area.configure(state="disabled")

        self._refresh_history()

        # Advance the batch queue
        next_item = self.batch.next()
        self._update_queue_panel()
        if next_item:
            stats = self.batch.stats
            self.progress.set_status(
                f"✓ {entry['filename']} concluído — próximo na fila ({stats['remaining']} restantes)"
            )
            self.after(500, self._process_next_in_queue)
        else:
            self.progress.set_complete(f"✓ Concluído em {time_str} — {words} palavras transcritas")
            self._on_queue_finished()

    def _transcription_error(self, msg):
        self.is_transcribing = False
        self.progress.stop()
        self.progress.hide()
        self._restore_upload_btn()

        # Show error with close button so user can dismiss
        self.preview_title.configure(text="Erro na transcrição")
        self.close_btn.pack(side="right", padx=(6, 0))
        self.actions_frame.pack_forget()

        self.text_area.configure(state="normal")
        self.text_area.delete("0.0", "end")
        self.text_area.insert("0.0", msg)
        self.text_area.configure(state="disabled")

        # Mark error in batch and advance
        current = self.batch.current_file()
        if current:
            self.batch.mark_error(current["filepath"])
        next_item = self.batch.next()
        self._update_queue_panel()
        if next_item:
            self.after(1000, self._process_next_in_queue)
        else:
            self._on_queue_finished()


if __name__ == "__main__":
    app = WhisperApp()
    app.mainloop()
