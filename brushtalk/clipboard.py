"""The Windows clipboard, for prompts and proofreading.

Until a prompt is being dictated or you ask for a proofread, only the clipboard's change counter is looked at, never what's on it.
Text a password manager has marked as private is left alone.
"""
from __future__ import annotations

import ctypes
import logging
import threading
import time
from ctypes import wintypes

log = logging.getLogger(__name__)

user32 =ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClipboardFormatW.restype = wintypes.UINT
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
PRIVATE = user32.RegisterClipboardFormatW("ExcludeClipboardContentFromMonitorProcessing")
POLL_SECONDS = 0.25


def sequence_number() -> int:
    return user32.GetClipboardSequenceNumber()


def _open() -> bool:
    """Another app can hold the clipboard for a moment."""
    for _ in range(20):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.03)
    return False


def _readable() -> bool:
    return bool(user32.IsClipboardFormatAvailable(CF_UNICODETEXT)) and not user32.IsClipboardFormatAvailable(PRIVATE)


def read_text() -> str | None:
    if not _readable() or not _open():
        return None
    try:
        # Asked again now that nothing else can change it: another app can have copied something private while this waited for its turn.
        if not _readable():
            return None
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        pointer = kernel32.GlobalLock(handle) if handle else None
        if not pointer:
            return None
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def write_text(text: str) -> bool:
    """The new text is made ready before the clipboard is emptied, so a write that can't happen leaves what you had copied."""
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
    pointer = kernel32.GlobalLock(handle) if handle else None
    if not pointer:
        if handle:
            kernel32.GlobalFree(handle)
        return False
    ctypes.memmove(pointer, data, size)
    kernel32.GlobalUnlock(handle)
    if not _open():
        kernel32.GlobalFree(handle)
        return False
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            return False
        return True
    finally:
        user32.CloseClipboard()


class Watcher(threading.Thread):
    """Knows when something was last copied, and hands over each copy while a prompt is listening. Always whole: code and proofreading come
    back to be pasted over the original, so a cut copy would come back without its end. Whoever takes it says when it's too long."""

    def __init__(self):
        super().__init__(daemon=True, name="clipboard")
        self.seen = sequence_number()
        self.changed_at: float | None = None
        self.on_copy = None

    def run(self) -> None:
        while True:
            time.sleep(POLL_SECONDS)
            self._poll_safely()

    def _poll_safely(self) -> None:
        """One bad read, or a prompt being cancelled just then, mustn't stop copies being noticed until the app restarts."""
        try:
            self.poll()
        except Exception:
            log.exception("Reading the clipboard failed")

    def poll(self) -> None:
        current = sequence_number()
        if current == self.seen:
            return
        self.seen = current
        self.changed_at = time.monotonic()
        on_copy = self.on_copy
        if on_copy:
            text = read_text()
            if text and text.strip():
                on_copy(text)

    def recent(self, seconds: float) -> str | None:
        """What's on the clipboard, if it was copied within the last so many seconds."""
        self.poll()
        if self.changed_at is None or time.monotonic() - self.changed_at > seconds:
            return None
        text = read_text()
        if not text or not text.strip():
            return None
        return text

    def write(self, text: str) -> bool:
        """The app's own writing doesn't count as you copying something."""
        written = write_text(text)
        self.seen = sequence_number()
        self.changed_at = None
        return written
