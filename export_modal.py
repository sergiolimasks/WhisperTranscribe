"""
Bulk export modal for WhisperTranscribe.
Lets the user select transcriptions and export them as a single .txt or .md file.
"""

import os
from datetime import datetime
from tkinter import filedialog

import customtkinter as ctk
from shared import COLORS, format_duration


class ExportModal(ctk.CTkToplevel):
    """Modal window for bulk-exporting transcriptions."""

    def __init__(self, parent, entries: list[dict]):
        super().__init__(parent)
        self.entries = entries
        self.checkboxes: list[tuple[ctk.CTkCheckBox, ctk.BooleanVar]] = []
        self.export_dir = os.path.expanduser("~/Desktop")
        self.format_var = ctk.StringVar(value=".md")

        self.title("Exportar Transcrições")
        self.configure(fg_color=COLORS["bg_main"])
        self.resizable(False, False)

        # Size and center on parent
        w, h = 600, 500
        px = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{px}+{py}")

        # Make modal
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._update_preview()

    # ── UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Title
        ctk.CTkLabel(
            self, text="Exportar Transcrições",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLORS["text"],
        ).pack(pady=(14, 6))

        # Scrollable list of entries
        list_frame = ctk.CTkScrollableFrame(
            self, fg_color=COLORS["bg_card"],
            border_color=COLORS["border"], border_width=1,
            height=180,
        )
        list_frame.pack(fill="x", padx=16, pady=(0, 6))

        for entry in self.entries:
            var = ctk.BooleanVar(value=True)
            cb = ctk.CTkCheckBox(
                list_frame,
                text=entry.get("filename", "sem nome"),
                variable=var,
                font=ctk.CTkFont(size=13),
                text_color=COLORS["text_secondary"],
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                border_color=COLORS["border_accent"],
                checkmark_color=COLORS["text"],
            )
            cb.pack(anchor="w", padx=8, pady=2)
            self.checkboxes.append((cb, var))

        # Select all / Deselect all buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 6))

        ctk.CTkButton(
            btn_row, text="Selecionar tudo", width=130, height=28,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_card_hover"],
            text_color=COLORS["text_secondary"],
            border_color=COLORS["border"], border_width=1,
            command=lambda: self._set_all(True),
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            btn_row, text="Desmarcar tudo", width=130, height=28,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_card_hover"],
            text_color=COLORS["text_secondary"],
            border_color=COLORS["border"], border_width=1,
            command=lambda: self._set_all(False),
        ).pack(side="left")

        # Format selector
        fmt_row = ctk.CTkFrame(self, fg_color="transparent")
        fmt_row.pack(fill="x", padx=16, pady=(0, 6))

        ctk.CTkLabel(
            fmt_row, text="Formato:", font=ctk.CTkFont(size=13),
            text_color=COLORS["text_secondary"],
        ).pack(side="left", padx=(0, 8))

        ctk.CTkSegmentedButton(
            fmt_row, values=[".txt", ".md", ".srt", ".vtt"],
            variable=self.format_var,
            font=ctk.CTkFont(size=13),
            fg_color=COLORS["bg_card"],
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
            unselected_color=COLORS["bg_card"],
            unselected_hover_color=COLORS["bg_card_hover"],
            text_color=COLORS["text"],
            command=lambda _: self._update_preview(),
        ).pack(side="left")

        # Filename + directory row
        file_row = ctk.CTkFrame(self, fg_color="transparent")
        file_row.pack(fill="x", padx=16, pady=(0, 6))

        today = datetime.now().strftime("%Y-%m-%d")
        self.filename_entry = ctk.CTkEntry(
            file_row, height=32,
            font=ctk.CTkFont(size=13),
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text"],
            border_color=COLORS["border"],
            placeholder_text="Nome do arquivo",
        )
        self.filename_entry.insert(0, f"transcricoes_{today}")
        self.filename_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.filename_entry.bind("<KeyRelease>", lambda _: self._update_preview())

        ctk.CTkButton(
            file_row, text="Escolher local", width=120, height=32,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            text_color=COLORS["text"],
            command=self._pick_directory,
        ).pack(side="left")

        # Preview label
        self.preview_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11),
            text_color=COLORS["text_dim"], anchor="w",
        )
        self.preview_label.pack(fill="x", padx=18, pady=(0, 8))

        # Export button
        self.export_btn = ctk.CTkButton(
            self, text="Exportar", height=36, width=200,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            text_color=COLORS["text"],
            command=self._do_export,
        )
        self.export_btn.pack(pady=(0, 12))

        # Status label (hidden until export)
        self.status_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=12),
            text_color=COLORS["success"],
        )
        self.status_label.pack(pady=(0, 6))

    # ── Helpers ─────────────────────────────────────────────────────────

    def _set_all(self, state: bool):
        for _, var in self.checkboxes:
            var.set(state)

    def _pick_directory(self):
        path = filedialog.askdirectory(initialdir=self.export_dir, parent=self)
        if path:
            self.export_dir = path
            self._update_preview()

    def _get_full_path(self) -> str:
        name = self.filename_entry.get().strip() or "transcricoes"
        ext = self.format_var.get()
        return os.path.join(self.export_dir, f"{name}{ext}")

    def _update_preview(self):
        self.preview_label.configure(text=self._get_full_path())

    def _selected_entries(self) -> list[dict]:
        return [
            self.entries[i]
            for i, (_, var) in enumerate(self.checkboxes)
            if var.get()
        ]

    # ── Formatting ──────────────────────────────────────────────────────

    @staticmethod
    def _format_date(date_str: str) -> str:
        """Return the date string as-is (already stored as dd/mm/yyyy HH:MM)."""
        return str(date_str) if date_str else ""

    def _build_md(self, entries: list[dict]) -> str:
        blocks: list[str] = []
        for entry in entries:
            filename = entry.get("filename", "sem nome")
            date = self._format_date(entry.get("date", ""))
            duration = format_duration(entry.get("duration_secs", 0))
            words = entry.get("words", 0)
            text = entry.get("text", "").strip()

            header = f"# {filename}"
            meta = f"**Data:** {date} | **Duração:** {duration} | **Palavras:** {words}"
            blocks.append(f"{header}\n{meta}\n\n{text}")

        return "\n\n---\n\n".join(blocks) + "\n"

    def _build_txt(self, entries: list[dict]) -> str:
        blocks: list[str] = []
        for entry in entries:
            filename = entry.get("filename", "sem nome")
            date = self._format_date(entry.get("date", ""))
            duration = format_duration(entry.get("duration_secs", 0))
            words = entry.get("words", 0)
            text = entry.get("text", "").strip()

            header = f"=== {filename} ==="
            meta = f"Data: {date} | Duração: {duration} | Palavras: {words}"
            blocks.append(f"{header}\n{meta}\n\n{text}")

        separator = "\n\n" + "=" * 40 + "\n\n"
        return separator.join(blocks) + "\n"

    def _build_srt(self, entries: list[dict]) -> str:
        """Build SRT subtitle format. Uses segments if available, otherwise one block per entry."""
        srt_index = 1
        blocks: list[str] = []

        for entry in entries:
            segments = entry.get("segments", [])
            if segments:
                for seg in segments:
                    start = self._srt_timestamp(seg.get("start", 0))
                    end = self._srt_timestamp(seg.get("end", 0))
                    text = seg.get("text", "").strip()
                    if text:
                        blocks.append(f"{srt_index}\n{start} --> {end}\n{text}")
                        srt_index += 1
            else:
                # No segments — create one block with full text
                duration = entry.get("duration_secs", 0)
                start = self._srt_timestamp(0)
                end = self._srt_timestamp(duration)
                text = entry.get("text", "").strip()
                if text:
                    blocks.append(f"{srt_index}\n{start} --> {end}\n{text}")
                    srt_index += 1

        return "\n\n".join(blocks) + "\n"

    @staticmethod
    def _srt_timestamp(seconds) -> str:
        """Convert seconds to SRT timestamp format HH:MM:SS,mmm."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    @staticmethod
    def _vtt_timestamp(seconds) -> str:
        """Convert seconds to VTT timestamp format HH:MM:SS.mmm."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

    def _build_vtt(self, entries: list[dict]) -> str:
        """Build WebVTT subtitle format."""
        blocks: list[str] = ["WEBVTT", ""]

        for entry in entries:
            segments = entry.get("segments", [])
            if segments:
                for seg in segments:
                    start = self._vtt_timestamp(seg.get("start", 0))
                    end = self._vtt_timestamp(seg.get("end", 0))
                    text = seg.get("text", "").strip()
                    if text:
                        blocks.append(f"{start} --> {end}\n{text}")
            else:
                duration = entry.get("duration_secs", 0)
                start = self._vtt_timestamp(0)
                end = self._vtt_timestamp(duration)
                text = entry.get("text", "").strip()
                if text:
                    blocks.append(f"{start} --> {end}\n{text}")

        return "\n\n".join(blocks) + "\n"

    # ── Export ──────────────────────────────────────────────────────────

    def _do_export(self):
        selected = self._selected_entries()
        if not selected:
            self.status_label.configure(
                text="Nenhuma transcrição selecionada.",
                text_color=COLORS["text_dim"],
            )
            return

        fmt = self.format_var.get()
        if fmt == ".md":
            content = self._build_md(selected)
        elif fmt == ".srt":
            content = self._build_srt(selected)
        elif fmt == ".vtt":
            content = self._build_vtt(selected)
        else:
            content = self._build_txt(selected)
        path = self._get_full_path()

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            self.status_label.configure(
                text=f"Erro ao salvar: {e}",
                text_color="#ff5555",
            )
            return

        count = len(selected)
        self.status_label.configure(
            text=f"Exportado {count} transcrição{'s' if count != 1 else ''} para {os.path.basename(path)}",
            text_color=COLORS["success"],
        )
        self.export_btn.configure(state="disabled", text="Concluído")
        self.after(1500, self.destroy)
