"""Batch file processing queue — UI panel and queue logic for WhisperTranscribe."""

import os
import customtkinter as ctk
from shared import COLORS

STATUS_ICONS = {
    "waiting": "\u23f3",
    "processing": "\u26a1",
    "completed": "\u2713",
    "error": "\u2715",
}

STATUS_COLORS = {
    "waiting": COLORS["text_dim"],
    "processing": COLORS["accent"],
    "completed": COLORS["success"],
    "error": COLORS["danger"],
}


# ---------------------------------------------------------------------------
# BatchProcessor — queue logic (non-UI)
# ---------------------------------------------------------------------------

class BatchProcessor:
    """Manages batch transcription queue state."""

    def __init__(self):
        self._queue: list[dict] = []

    # -- mutators --

    def add_files(self, filepaths: list[str]) -> None:
        for fp in filepaths:
            self._queue.append({
                "filepath": fp,
                "filename": os.path.basename(fp),
                "status": "waiting",
            })
        # Auto-start: mark the first waiting item as processing if nothing is active
        if not any(item["status"] == "processing" for item in self._queue):
            for item in self._queue:
                if item["status"] == "waiting":
                    item["status"] = "processing"
                    break

    def remove_file(self, filepath: str) -> None:
        self._queue = [
            item for item in self._queue
            if not (item["filepath"] == filepath and item["status"] == "waiting")
        ]

    def next(self) -> dict | None:
        """Mark current processing item as completed and advance to the next."""
        for item in self._queue:
            if item["status"] == "processing":
                item["status"] = "completed"
                break
        # Find next waiting item
        for item in self._queue:
            if item["status"] == "waiting":
                item["status"] = "processing"
                return item
        return None

    def mark_error(self, filepath: str) -> None:
        for item in self._queue:
            if item["filepath"] == filepath and item["status"] == "processing":
                item["status"] = "error"
                break

    def cancel_all(self) -> None:
        self._queue = [
            item for item in self._queue
            if item["status"] not in ("waiting", "processing")
        ]

    # -- queries --

    def get_queue(self) -> list[dict]:
        return [dict(item) for item in self._queue]

    def current_file(self) -> dict | None:
        for item in self._queue:
            if item["status"] == "processing":
                return dict(item)
        return None

    @property
    def is_active(self) -> bool:
        return any(item["status"] in ("waiting", "processing") for item in self._queue)

    @property
    def stats(self) -> dict:
        total = len(self._queue)
        completed = sum(1 for i in self._queue if i["status"] == "completed")
        errors = sum(1 for i in self._queue if i["status"] == "error")
        remaining = sum(1 for i in self._queue if i["status"] in ("waiting", "processing"))
        return {
            "total": total,
            "completed": completed,
            "errors": errors,
            "remaining": remaining,
        }


# ---------------------------------------------------------------------------
# QueuePanel — compact scrollable queue display (ctk.CTkFrame)
# ---------------------------------------------------------------------------

class QueuePanel(ctk.CTkFrame):
    """Compact scrollable list of queued files with status indicators."""

    def __init__(self, parent, on_cancel_all=None, on_remove_item=None, **kwargs):
        super().__init__(
            parent,
            fg_color=COLORS["bg_dark"],
            corner_radius=8,
            border_width=1,
            border_color=COLORS["border"],
            **kwargs,
        )
        self._on_cancel_all = on_cancel_all
        self._on_remove_item = on_remove_item
        self._item_rows: list[ctk.CTkFrame] = []

        # -- header row --
        header = ctk.CTkFrame(self, fg_color="transparent", height=30)
        header.pack(fill="x", padx=8, pady=(6, 2))

        ctk.CTkLabel(
            header,
            text="Fila de processamento",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text_secondary"],
        ).pack(side="left")

        self._cancel_btn = ctk.CTkButton(
            header,
            text="\u2715 Cancelar fila",
            font=ctk.CTkFont(size=11),
            width=100,
            height=24,
            corner_radius=4,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            text_color=COLORS["text"],
            command=self._handle_cancel_all,
        )
        self._cancel_btn.pack(side="right")

        # -- scrollable area --
        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            height=120,
        )
        self._scroll.pack(fill="x", padx=4, pady=(0, 6))

    # -- public API --

    def set_items(self, items: list[dict]) -> None:
        """Rebuild the list from scratch. Each dict has filepath, filename, status."""
        # Clear old rows
        for row in self._item_rows:
            row.destroy()
        self._item_rows.clear()

        for item in items:
            self._add_row(item)

    def show(self) -> None:
        self.pack(fill="x", padx=12, pady=(0, 6))

    def hide(self) -> None:
        self.pack_forget()

    # -- internals --

    def _add_row(self, item: dict) -> None:
        status = item.get("status", "waiting")
        is_processing = status == "processing"

        row_bg = COLORS["bg_card_selected"] if is_processing else COLORS["bg_card"]
        row = ctk.CTkFrame(
            self._scroll,
            fg_color=row_bg,
            corner_radius=4,
            height=28,
        )
        row.pack(fill="x", pady=1)
        row.pack_propagate(False)

        # Status icon
        icon = STATUS_ICONS.get(status, "?")
        ctk.CTkLabel(
            row,
            text=icon,
            font=ctk.CTkFont(size=13),
            text_color=STATUS_COLORS.get(status, COLORS["text_dim"]),
            width=24,
        ).pack(side="left", padx=(6, 2))

        # Filename (truncated)
        name = item.get("filename", "???")
        if len(name) > 32:
            name = name[:29] + "..."

        ctk.CTkLabel(
            row,
            text=name,
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text"] if is_processing else COLORS["text_secondary"],
            anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=2)

        # Remove button — only for waiting items
        if status == "waiting":
            filepath = item.get("filepath", "")
            remove_btn = ctk.CTkButton(
                row,
                text="\u2715",
                font=ctk.CTkFont(size=11),
                width=22,
                height=22,
                corner_radius=4,
                fg_color="transparent",
                hover_color=COLORS["danger"],
                text_color=COLORS["text_dim"],
                command=lambda fp=filepath: self._handle_remove(fp),
            )
            remove_btn.pack(side="right", padx=(0, 4))

        self._item_rows.append(row)

    def _handle_cancel_all(self) -> None:
        if self._on_cancel_all:
            self._on_cancel_all()

    def _handle_remove(self, filepath: str) -> None:
        if self._on_remove_item:
            self._on_remove_item(filepath)
