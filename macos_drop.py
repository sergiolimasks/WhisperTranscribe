"""
macos_drop.py -- Native macOS file drag-and-drop for tkinter/customtkinter windows.

Works on macOS with Tk 9.x by injecting drag-and-drop methods directly into
Tk's TKContentView via PyObjC. Uses a file-based queue to avoid GIL conflicts
between Cocoa's drag system and tkinter's event loop.

Requirements:
    pip install pyobjc-core pyobjc-framework-Cocoa
"""

from __future__ import annotations

import sys
import os
import tempfile
import json

if sys.platform != "darwin":
    raise ImportError("macos_drop only works on macOS")

import objc
from Foundation import NSURL
from AppKit import (
    NSApp,
    NSPasteboardTypeFileURL,
    NSDragOperationCopy,
    NSDragOperationNone,
)

# ---------------------------------------------------------------------------
# File-based drop queue (decouples Cocoa callbacks from Python/Tk GIL)
# ---------------------------------------------------------------------------
_DROP_QUEUE_FILE = os.path.join(tempfile.gettempdir(), f".tkdrop_{os.getpid()}.json")
_methods_injected = False


def _inject_methods_once():
    """
    Inject drag methods into TKContentView. The performDragOperation_
    method writes file paths to a temp file instead of calling Python
    directly, avoiding GIL conflicts with tkinter's event loop.
    """
    global _methods_injected
    if _methods_injected:
        return
    _methods_injected = True

    TKContentView = objc.lookUpClass("TKContentView")
    queue_path = _DROP_QUEUE_FILE

    def _has_file_urls(sender):
        pboard = sender.draggingPasteboard()
        types = pboard.types()
        return types is not None and NSPasteboardTypeFileURL in types

    # -- draggingEntered: -- pure ObjC, no Python callback needed
    def draggingEntered_(self, sender):
        if _has_file_urls(sender):
            return NSDragOperationCopy
        return NSDragOperationNone

    # -- draggingUpdated: --
    def draggingUpdated_(self, sender):
        if _has_file_urls(sender):
            return NSDragOperationCopy
        return NSDragOperationNone

    # -- performDragOperation: -- writes to file instead of calling Python
    def performDragOperation_(self, sender):
        pboard = sender.draggingPasteboard()
        files = []

        items = pboard.pasteboardItems()
        if items:
            for item in items:
                url_str = item.stringForType_(NSPasteboardTypeFileURL)
                if url_str:
                    url = NSURL.URLWithString_(url_str)
                    if url and url.path():
                        files.append(str(url.path()))

        if not files:
            return False

        # Write to temp file — tkinter timer will read it
        try:
            with open(queue_path, "w") as f:
                json.dump(files, f)
        except Exception:
            return False
        return True

    objc.classAddMethods(TKContentView, [
        objc.selector(
            draggingEntered_,
            selector=b"draggingEntered:",
            signature=b"Q@:@",
        ),
        objc.selector(
            draggingUpdated_,
            selector=b"draggingUpdated:",
            signature=b"Q@:@",
        ),
        objc.selector(
            performDragOperation_,
            selector=b"performDragOperation:",
            signature=b"B@:@",
        ),
    ])


def _find_nswindow_for_tk(tk_widget):
    """Find the NSWindow matching a tkinter/CTk window by title."""
    tk_widget.update_idletasks()
    title = tk_widget.title()

    for nswin in NSApp.windows():
        cv = nswin.contentView()
        if cv is None:
            continue
        if str(cv.className()) != "TKContentView":
            continue
        if str(nswin.title()) == title:
            return nswin

    # Fallback: first TKContentView window
    for nswin in NSApp.windows():
        cv = nswin.contentView()
        if cv is not None and str(cv.className()) == "TKContentView":
            return nswin

    return None


def enable_drop(tk_window, callback, *, extensions=None, poll_ms=150):
    """
    Enable native file drag-and-drop on a tkinter/customtkinter window.

    Parameters
    ----------
    tk_window : tkinter.Tk | ctk.CTk
        The window to enable drops on.
    callback : callable(list[str])
        Called with a list of file paths when files are dropped.
    extensions : set[str] | None
        Optional set of allowed extensions (e.g., {".mp3", ".wav"}).
    poll_ms : int
        How often to check for dropped files (default 150ms).
    """
    tk_window.update_idletasks()

    _inject_methods_once()

    nswin = _find_nswindow_for_tk(tk_window)
    if nswin is None:
        raise RuntimeError(
            "Could not find NSWindow for the given tkinter window. "
            "Make sure the window is visible before calling enable_drop()."
        )

    cv = nswin.contentView()
    cv.registerForDraggedTypes_([NSPasteboardTypeFileURL])

    # Build filtered callback
    if extensions:
        normalized = {ext.lower() for ext in extensions}

        def filtered_callback(files):
            accepted = [f for f in files if os.path.splitext(f)[1].lower() in normalized]
            if accepted:
                callback(accepted)
    else:
        filtered_callback = callback

    # Clean up any stale queue file
    try:
        os.unlink(_DROP_QUEUE_FILE)
    except FileNotFoundError:
        pass

    # Start polling timer on tkinter's event loop (safe — runs with GIL held)
    def _poll_drop_queue():
        try:
            if os.path.exists(_DROP_QUEUE_FILE):
                with open(_DROP_QUEUE_FILE, "r") as f:
                    files = json.load(f)
                os.unlink(_DROP_QUEUE_FILE)
                if files:
                    filtered_callback(files)
        except (json.JSONDecodeError, OSError):
            try:
                os.unlink(_DROP_QUEUE_FILE)
            except FileNotFoundError:
                pass
        tk_window.after(poll_ms, _poll_drop_queue)

    tk_window.after(poll_ms, _poll_drop_queue)


def disable_drop(tk_window):
    """Disable drag-and-drop on a previously enabled window."""
    tk_window.update_idletasks()
    nswin = _find_nswindow_for_tk(tk_window)
    if nswin:
        cv = nswin.contentView()
        cv.unregisterDraggedTypes()
    try:
        os.unlink(_DROP_QUEUE_FILE)
    except FileNotFoundError:
        pass
