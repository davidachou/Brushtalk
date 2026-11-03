"""The parts that make it feel like a Windows app: main window, floating recording bar, tray icon, global hotkeys."""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
import winreg
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from . import sounds
from .config import DATA, ROOT, UI_DIR
from .controller import Controller

log = logging.getLogger(__name__)

APP_ID = "KKA.Brushtalk"
ICON_PATH = UI_DIR / "icon.ico"
RECORDING_ICON_PATH = UI_DIR / "icon-recording.ico"
BAR_WIDTH = 430
BAR_REDRAW = 0.08  # seconds
BAR_KEEPS = 10  # seconds a finished prompt stays up
TRAY_KEEPS = 60  # the same, when the tray icon is all there is to see
BAR_MARGIN = 24  # how far it starts from the corner of the screen, before Windows scales it
MARK_SIZE = 26  # the tiny character in low key, before Windows scales it
MARK_MARGIN = 8  # and how far it starts from the corner of the screen
# The windows' colour before their pages have drawn, and the title bar's after: black ink and rice paper.
WINDOW_COLORS = {"ink": "#0b0b0e", "paper": "#f1ecdf"}
TITLE_COLORS = {"ink": "#eee8da", "paper": "#1a1711"}
TRAY_SIZE = 64
# The status characters on the tray icon, beside the clock, so low key has somewhere to say what's going on. Their colours are from ink.css.
TRAY_MARKS = {"paused": ("停", "#eee8da"), "waiting": ("抄", "#eee8da"), "working": ("寫", "#f2cc7a"), "check": ("校", "#f2cc7a"), "problem": ("錯", "#ff3b1f"), "empty": ("無", "#eee8da")}
TRAY_WORDS = {
    "idle": "Brushtalk",
    "recording": "Brushtalk: recording",
    "paused": "Brushtalk: paused",
    "waiting": "Brushtalk: copy the text to proofread",
    "working": "Brushtalk: writing",
    "ready": "Brushtalk: ready, press Ctrl+V",
    "check": "Brushtalk: take a look before you paste",
    "problem": "Brushtalk: something went wrong",
    "empty": "Brushtalk: nothing to paste",
}
ON_SCREEN = (("bar", "The full bar"), ("mark", "Low key: a tiny character"), ("tray", "Low key: only the tray icon"))
SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
CORNERS = 33  # how Windows rounds a window's corners
CORNERS_DEFAULT, CORNERS_ROUND = 0, 2
MONITOR_DEFAULTTONULL, MONITOR_DEFAULTTOPRIMARY = 0, 1
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
WM_HOTKEY = 0x0312
WM_REBIND = 0x0400 + 1
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
MODIFIERS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}


class MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


# Its own copy, so that these argument types can't reach the calls the window library makes.
screens = ctypes.WinDLL("user32")
screens.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
screens.MonitorFromPoint.restype = wintypes.HANDLE
screens.MonitorFromRect.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD]
screens.MonitorFromRect.restype = wintypes.HANDLE
screens.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]


def _work_area(monitor) -> tuple[int, int, int, int]:
    info = MonitorInfo(ctypes.sizeof(MonitorInfo))
    screens.GetMonitorInfoW(monitor, ctypes.byref(info))
    return info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom


def main_area() -> tuple[int, int, int, int]:
    """The main screen without its taskbar, as left, top, right, bottom. Windows is asked each time, because .NET's and the library's lists of screens keep the
    sizes from before the app takes charge of its own scaling. On a screen at 175% they're smaller than where windows really go, by that much."""
    return _work_area(screens.MonitorFromPoint(wintypes.POINT(0, 0), MONITOR_DEFAULTTOPRIMARY))


def area_under(left: int, top: int, right: int, bottom: int) -> tuple[int, int, int, int] | None:
    """The same for whichever screen that rectangle is mostly on, or None if it isn't on any."""
    monitor = screens.MonitorFromRect(ctypes.byref(wintypes.RECT(left, top, right, bottom)), MONITOR_DEFAULTTONULL)
    return _work_area(monitor) if monitor else None


def kept_on_screen(x: int, y: int, width: int, height: int, area: tuple[int, int, int, int]) -> tuple[int, int]:
    return max(area[0], min(x, area[2] - width)), max(area[1], min(y, area[3] - height))


def saved_place(saved, width: int, height: int) -> tuple[int, int] | None:
    """Where you last left it, all of it on screen, unless the screen it was on isn't there now. Then what's saved stays saved, for when that screen comes back."""
    try:
        x, y = (int(value) for value in saved)
    except (TypeError, ValueError):
        return None
    area = area_under(x, y, x + width, y + height)
    return kept_on_screen(x, y, width, height, area) if area else None


def tray_image(recording: bool = False) -> Image.Image:
    """Red mic on black, turning to a black mic on red when recording, so the tray shows the state at a glance. tools/make_icon.py paints them."""
    image = Image.open(RECORDING_ICON_PATH if recording else ICON_PATH)
    image.size = (64, 64)
    image.load()
    return image.convert("RGBA")


def _tray_ground(color: str) -> Image.Image:
    image = Image.new("RGBA", (TRAY_SIZE, TRAY_SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(image).rounded_rectangle((0, 0, TRAY_SIZE - 1, TRAY_SIZE - 1), TRAY_SIZE // 5, fill=color)
    return image


def tray_mark(ch: str, color: str) -> Image.Image:
    """A status character on the icon's black. The right half of its picture says how dark each spot is. It's thickened, because the tray shows about 28 pixels of it."""
    sheet = Image.open(UI_DIR / "glyphs" / f"u{ord(ch):x}.png").convert("L")
    ink = sheet.crop((sheet.height, 0, sheet.height * 2, sheet.height)).filter(ImageFilter.MaxFilter(5)).resize((TRAY_SIZE, TRAY_SIZE), Image.LANCZOS)
    image = _tray_ground(WINDOW_COLORS["ink"])
    image.paste(Image.new("RGBA", image.size, color), (0, 0), ink)
    return image


def tray_seal() -> Image.Image:
    """The 完 seal, on paper, since its character is left bare and would otherwise be whatever colour the taskbar is."""
    image = _tray_ground(WINDOW_COLORS["paper"])
    image.alpha_composite(Image.open(UI_DIR / "glyphs" / "seal.png").convert("RGBA").resize(image.size, Image.LANCZOS))
    return image


def tray_images() -> dict[str, Image.Image]:
    return {"idle": tray_image(False), "recording": tray_image(True), "ready": tray_seal(), **{state: tray_mark(*mark) for state, mark in TRAY_MARKS.items()}}


def parse_hotkey(spec: str) -> tuple[int, int] | None:
    modifiers, key = 0, None
    for part in spec.split("+"):
        part = part.strip().lower()
        if part in MODIFIERS:
            modifiers |= MODIFIERS[part]
        elif len(part) == 1 and part.isalnum():
            key = ord(part.upper())
        elif part.startswith("f") and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            key = 0x70 + int(part[1:]) - 1
        elif part == "enter":
            key = 0x0D
        else:
            return None
    if key is None or modifiers == 0:
        return None
    return modifiers | MOD_NOREPEAT, key


class Hotkeys(threading.Thread):
    """RegisterHotKey needs no admin rights or keyboard hook; messages arrive on the registering thread."""

    def __init__(self, bindings: dict):
        """bindings maps each shortcut's setting to (the keys, what it does)."""
        super().__init__(daemon=True, name="hotkey")
        self.names = list(bindings)
        self.specs = {name: spec for name, (spec, _) in bindings.items()}
        self.callbacks = {name: callback for name, (_, callback) in bindings.items()}
        self.errors: dict[str, str | None] = {}
        self.thread_id = 0
        self.ready = threading.Event()
        self.rebound = threading.Event()

    def _register(self, name: str) -> None:
        number = self.names.index(name) + 1
        spec = self.specs[name]
        user32.UnregisterHotKey(None, number)
        parsed = parse_hotkey(spec)
        if not parsed:
            self.errors[name] = f"{spec} isn't a usable shortcut. Use a modifier plus a letter, a number or F1 to F24."
        elif user32.RegisterHotKey(None, number, parsed[0], parsed[1]):
            self.errors[name] = None
        else:
            self.errors[name] = f"{spec} is already used by another app, or by another shortcut here. Try a different one."
        if self.errors[name]:
            log.warning(self.errors[name])

    def run(self) -> None:
        self.thread_id = kernel32.GetCurrentThreadId()
        message = wintypes.MSG()
        # Create this thread's message queue before anyone can post to it.
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        for name in self.names:
            self._register(name)
        self.ready.set()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            if message.message == WM_HOTKEY:
                threading.Thread(target=self.callbacks[self.names[message.wParam - 1]], daemon=True).start()
            elif message.message == WM_REBIND:
                self._register(self.names[message.wParam])
                self.rebound.set()

    def rebind(self, name: str, spec: str) -> str | None:
        self.specs[name] = spec
        self.rebound.clear()
        user32.PostThreadMessageW(self.thread_id, WM_REBIND, self.names.index(name), 0)
        self.rebound.wait(2)
        return self.errors.get(name)


def _shortcut_script(path: Path, minimized: bool = False) -> str:
    python = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    arguments = "-m brushtalk" + (" --background" if minimized else "")
    return (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{}');"
        "$s.TargetPath = '{}'; $s.Arguments = '{}'; $s.WorkingDirectory = '{}';"
        "$s.IconLocation = '{}'; $s.Description = 'Brushtalk'; $s.Save()"
    ).format(path, python, arguments, ROOT, ICON_PATH)


def _powershell(script: str) -> None:
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        capture_output=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _folder(name: str) -> Path:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"[Environment]::GetFolderPath('{name}')"],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return Path(out.stdout.strip())


def set_app_id(path: Path) -> None:
    """Tells Windows a shortcut and the app's windows are the same app. Without this, pinning the running app pins Python, with Python's icon."""

    class Key(ctypes.Structure):
        _fields_ = [("fmtid", ctypes.c_byte * 16), ("pid", wintypes.DWORD)]

    class Value(ctypes.Structure):
        _fields_ = [("vt", wintypes.USHORT), ("reserved", wintypes.USHORT * 3), ("text", ctypes.c_wchar_p), ("spare", ctypes.c_void_p)]

    def guid(text: str):
        return (ctypes.c_byte * 16).from_buffer_copy(uuid.UUID(text).bytes_le)

    started = ctypes.windll.ole32.CoInitializeEx(None, 2) in (0, 1)
    try:
        store = ctypes.c_void_p()
        shell32 = ctypes.windll.shell32
        shell32.SHGetPropertyStoreFromParsingName.restype = ctypes.HRESULT
        shell32.SHGetPropertyStoreFromParsingName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        shell32.SHGetPropertyStoreFromParsingName(str(path), None, 2, ctypes.byref(guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")), ctypes.byref(store))
        methods = ctypes.cast(store, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        try:
            key = Key(guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), 5)
            value = Value(31, (0, 0, 0), APP_ID, None)  # 31 is a wide string
            ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(Key), ctypes.POINTER(Value))(methods[6])(store, ctypes.byref(key), ctypes.byref(value))
            ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p)(methods[7])(store)
        finally:
            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(methods[2])(store)
    finally:
        if started:
            ctypes.windll.ole32.CoUninitialize()


def _make_shortcut(path: Path, minimized: bool = False) -> None:
    _powershell(_shortcut_script(path, minimized))
    set_app_id(path)


def install_shortcuts() -> list[Path]:
    desktop = _folder("Desktop") / "Brushtalk.lnk"
    programs = _folder("Programs") / "Brushtalk.lnk"
    for path in (desktop, programs):
        _make_shortcut(path)
    return [desktop, programs]


def set_autostart(enabled: bool) -> None:
    path = _folder("Startup") / "Brushtalk.lnk"
    if enabled:
        _make_shortcut(path, minimized=True)
    else:
        path.unlink(missing_ok=True)


def windows_is_light() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return bool(winreg.QueryValueEx(key, "AppsUseLightTheme")[0])
    except OSError:
        return False


def resolved_theme(theme: str) -> str:
    if theme == "auto":
        return "paper" if windows_is_light() else "ink"
    return "paper" if theme == "paper" else "ink"


def windows_color(color: str) -> int:
    """Windows keeps colours as blue, green, red."""
    red, green, blue = (int(color[at : at + 2], 16) for at in (1, 3, 5))
    return red | green << 8 | blue << 16


def paint_title_bar(hwnd: int, theme: str) -> None:
    """Colours the window's title bar to match the page. Windows 11 only, and older versions simply ignore it."""
    settings = (
        (20, 0 if theme == "paper" else 1),  # dark mode
        (35, windows_color(WINDOW_COLORS[theme])),  # the bar
        (36, windows_color(TITLE_COLORS[theme])),  # its text
    )
    for attribute, number in settings:
        value = ctypes.c_int(number)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), attribute, ctypes.byref(value), ctypes.sizeof(value))


class Desktop:
    def __init__(self, controller: Controller, url: str, start_hidden: bool = False):
        self.controller = controller
        self.base_url = url
        self.start_hidden = start_hidden
        self.main = None
        self.mini = None
        self.tray = None
        self.hotkeys: Hotkeys | None = None
        self.quitting = False
        self.images = {}
        self.told_about_tray = False
        self.prompt_target = None
        self.check_target = None
        self.bar_timer: threading.Timer | None = None
        self.bar_open = False
        self.full_bar: tuple[float, float] | None = None
        self.prompt_settled = False  # a finished prompt has had its time on screen
        self.tray_state = "idle"
        controller.play_sound = sounds.play
        controller.listeners.append(self._on_event)

    # ------------------------------------------------------------- window control

    def show_main(self) -> None:
        if not self.main:
            return
        self.main.show()
        self.main.restore()
        # Windows won't let a background process take focus directly; a brief on-top flip brings it forward.
        self.main.on_top = True
        self.main.on_top = False

    def _on_bar_thread(self, action) -> None:
        """The library's own show() takes keyboard focus. The bar never should: your Ctrl+V has to land where you were working."""
        from System import Func, Type

        form = self.mini.native
        form.Invoke(Func[Type](action))

    def hide_mini(self) -> None:
        self.prompt_settled = True
        if self.mini:
            self._on_bar_thread(self.mini.native.Hide)
            self.bar_open = False
            if self.controller.bar_opened_up:
                self.controller.bar_opened_up = False
                self._fit_bar()

    def show_mini(self) -> None:
        if self.mini and self.controller.settings["show_mini"]:
            self._open_bar()

    def _open_bar(self) -> None:
        """Its page has just been told what changed. Opened any sooner, the bar would show whatever it showed last time."""
        if self.controller.settings["on_screen"] == "tray":
            return
        if not self.bar_open:
            time.sleep(BAR_REDRAW)
        self._on_bar_thread(self.mini.native.Show)
        self.bar_open = True

    def _bar_place(self, tiny: bool, window: tuple[int, int, int, int], width: int, height: int, scale: float) -> tuple[int, int]:
        """Where the window goes, as left and top, given where it is now as left, top, right, bottom. The full bar and the tiny character each go where you last
        dragged them. Until you do, the full bar starts at the top right of the main screen, and the tiny character in the corner above the clock, out of the
        way of any window's buttons. The full bar you open from the tiny character comes out of it, with the edges nearest the sides of the screen staying put."""
        settings = self.controller.settings
        if tiny or settings["on_screen"] == "bar":
            place = saved_place(settings["mark_place" if tiny else "bar_place"], width, height)
            if place:
                return place
            area = main_area()
            if tiny:
                return area[2] - width - round(MARK_MARGIN * scale), area[3] - height - round(MARK_MARGIN * scale)
            return area[2] - width - round(BAR_MARGIN * scale), area[1] + round(BAR_MARGIN * scale)
        area = area_under(*window) or main_area()
        left, top, right, bottom = window
        near_right = left + right > area[0] + area[2]
        near_bottom = top + bottom > area[1] + area[3]
        return kept_on_screen(right - width if near_right else left, bottom - height if near_bottom else top, width, height, area)

    def _fit_bar(self) -> None:
        """Puts the window where it goes, at the size it should be. The tiny character is this same window made small, so it keeps its page. Nothing here takes
        focus, or Ctrl+V wouldn't land where you were."""
        from System.Drawing import Size

        tiny = self.controller.settings["on_screen"] == "mark" and not self.controller.bar_opened_up

        def fit():
            form = self.mini.native
            handle = wintypes.HWND(form.Handle.ToInt64())
            scale = (user32.GetDpiForWindow(handle) or 96) / 96
            # In units that hold on any screen. It's measured before the first change, so the full bar stays exactly the size it's always been.
            self.full_bar = self.full_bar or (form.Width / scale, form.Height / scale)
            width, height = (round(side * scale) for side in ((MARK_SIZE, MARK_SIZE) if tiny else self.full_bar))
            # The library gives every window a minimum size bigger than this.
            form.MinimumSize = Size(0, 0)
            x, y = self._bar_place(tiny, (form.Left, form.Top, form.Right, form.Bottom), width, height, scale)
            user32.SetWindowPos(handle, None, x, y, width, height, SWP_NOZORDER | SWP_NOACTIVATE)
            corners = ctypes.c_int(CORNERS_ROUND if tiny else CORNERS_DEFAULT)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(handle, CORNERS, ctypes.byref(corners), ctypes.sizeof(corners))

        self._on_bar_thread(fit)

    def remember_bar_place(self) -> None:
        """You've just dragged it, so that's where it goes from now on, even after a restart. Only your drags count: Windows moves windows by itself, such as when a
        monitor sleeps, and that shouldn't lose your place. Moving the full bar you opened from the tiny character doesn't move the character."""
        key = {"bar": "bar_place", "mark": "mark_place"}.get(self.controller.settings["on_screen"])
        if self.mini and key and not self.controller.bar_opened_up:
            self.controller.update_settings({key: [self.mini.native.Left, self.mini.native.Top]})

    def open_up_bar(self, opened: bool) -> None:
        """Low key: a click on the tiny character brings out the full bar and its buttons, until the mouse moves away."""
        if self.mini and self.controller.settings["on_screen"] == "mark":
            self.controller.bar_opened_up = opened
            self.controller._emit("bar_opened_up")
            self._fit_bar()
            # Clicking on it can move focus to it. Put it back where you were, or your Ctrl+V would go nowhere.
            if not opened and self.prompt_target and user32.GetForegroundWindow() == self.mini.native.Handle.ToInt64():
                user32.SetForegroundWindow(self.prompt_target)

    def _bar_wanted(self) -> bool:
        controller = self.controller
        if controller.is_recording():
            return bool(controller.settings["show_mini"])
        return bool(controller.prompt_stage and not self.prompt_settled)

    def _on_screen_changed(self) -> None:
        self.controller.bar_opened_up = False
        if self.tray:
            self.tray.update_menu()  # so its menu ticks the new choice
        if not self.mini:
            return
        self._fit_bar()
        if self.controller.settings["on_screen"] == "tray":
            settled = self.prompt_settled
            self.hide_mini()
            self.prompt_settled = settled
        elif self._bar_wanted():
            self._open_bar()

    def _prepare_bar(self) -> None:
        """The first time a window shows, the library focuses its page. So that happens now, invisibly, at startup."""

        def first_show():
            form = self.mini.native
            form.Opacity = 0
            form.Show()
            form.Hide()
            form.Opacity = 1

        try:
            self.mini.events.loaded.wait(15)
            self._on_bar_thread(first_show)
            # With only the tray icon nothing shows, and changing that setting fits it then.
            if self.controller.settings["on_screen"] != "tray":
                self._fit_bar()
        except Exception:
            log.exception("Preparing the floating bar failed")

    def _on_prompt_stage(self, stage: str | None) -> None:
        """The bar is how you know a prompt is ready, so it shows whatever the setting for the recording bar is."""
        self.prompt_settled = False
        if self.bar_timer:
            self.bar_timer.cancel()
            self.bar_timer = None
        if not self.mini:
            return
        # A prompt can finish behind a meeting. The bar then belongs to the meeting, with its Stop button and its warnings, and the tray tells you.
        if self.controller.is_recording():
            what = {"code": "code", "proofread": "edited text"}.get(self.controller.prompt_kind, "prompt")
            if stage == "copy":
                self.notify("Copy the text to proofread. It isn't listening while you record.")
            elif stage == "writing" and self.controller.prompt_kind == "proofread":
                self.notify("Proofreading what you copied. It isn't listening while you record.")
            elif stage == "check":
                self.notify(f"Your {what} is waiting for you to check it, on the Prompts page.")
            elif stage in ("ready", "failed", "empty"):
                self.notify(self.controller.prompt_message or f"Your {what} is ready. It's on your clipboard.")
            return
        if stage is None:
            self.check_target = None
            self.hide_mini()
            return
        if stage == "listening" or (stage in ("copy", "writing") and self.controller.prompt_kind == "proofread"):
            self.prompt_target = user32.GetForegroundWindow()
            self.check_target = None
        self._open_bar()
        if stage == "hearing" and self.prompt_target and user32.GetForegroundWindow() == self.mini.native.Handle.ToInt64():
            # Pressing Stop on the bar can move focus to it. Put it back where you were.
            user32.SetForegroundWindow(self.prompt_target)
        if stage == "check":
            # Checking it is why you turned this on. Where you were is kept, for when you send it, even if you stop it partway and come back here.
            self.check_target = self.check_target or user32.GetForegroundWindow()
            self.controller.show_prompt_in_window(None)
            self.show_main()
        # You'll be told to press Ctrl+V, and from the window that would paste into the window.
        if stage == "writing" and self.check_target and self.main and user32.GetForegroundWindow() == self.main.native.Handle.ToInt64():
            user32.SetForegroundWindow(self.check_target)
        if stage in ("ready", "failed", "empty"):
            self.check_target = None
            # Low key can't say why on a tiny character, and what's gone wrong always gets through.
            if self.controller.low_key() and self.controller.prompt_message:
                self.notify(self.controller.prompt_message)
        # It stays up if there's something it needs you to see.
        if stage == "check" or (stage == "ready" and not self.controller.prompt_check and not self.controller.prompt_message):
            self.bar_timer = threading.Timer(TRAY_KEEPS if self.controller.settings["on_screen"] == "tray" else BAR_KEEPS, self._hide_finished_prompt)
            self.bar_timer.daemon = True
            self.bar_timer.start()

    def _hide_finished_prompt(self) -> None:
        """A recording may have started in the meantime, and then the bar is its bar."""
        self.prompt_settled = True
        if not self.controller.is_recording():
            self.hide_mini()
        self._refresh_tray()

    def quit(self) -> None:
        def finish():
            self.quitting = True
            self.controller.shutdown()
            if self.tray:
                self.tray.stop()
            for window in (self.mini, self.main):
                if window:
                    try:
                        window.destroy()
                    except Exception:
                        log.exception("Closing a window failed")

        threading.Thread(target=finish, daemon=True, name="quit").start()

    def _on_closing(self) -> bool:
        if self.quitting:
            return True
        if self.controller.settings["close_to_tray"] or self.controller.is_capturing():
            threading.Thread(target=self._hide_main, daemon=True).start()
            return False
        self.quit()
        return False

    def _hide_main(self) -> None:
        self.main.hide()
        if not self.told_about_tray:
            self.told_about_tray = True
            self.notify(f"Brushtalk is still running. Press {self.controller.settings['hotkey']} to record, or open it from the tray.", routine=True)

    # ------------------------------------------------------------- tray

    def notify(self, message: str, routine: bool = False) -> None:
        """Routine news stays out of the way in low key. What's gone wrong still comes through."""
        if routine and self.controller.low_key():
            return
        if self.tray:
            try:
                self.tray.notify(message, "Brushtalk")
            except Exception:
                log.exception("Notification failed")

    def _tray_state(self) -> str:
        controller = self.controller
        recorder = controller.recorder or controller.prompt_recorder
        if recorder:
            if (recorder.status().get("health") or {}).get("kind") == "error":
                return "problem"
            return "paused" if recorder.paused_at else "recording"
        stage = controller.prompt_stage
        if stage in ("hearing", "writing"):
            return "working"
        if stage == "copy":
            return "waiting"
        if not stage or self.prompt_settled:
            return "idle"
        if stage == "ready" and not controller.prompt_message:
            return "check" if controller.prompt_check else "ready"
        return {"check": "check", "empty": "empty"}.get(stage, "problem")

    def _refresh_tray(self) -> None:
        if not self.tray:
            return
        state = self._tray_state()
        if state != self.tray_state:
            self.tray_state = state
            self.tray.icon = self.images[state]
            self.tray.title = TRAY_WORDS[state]
            self.tray.update_menu()

    def _open_from_tray(self) -> None:
        """What's on the icon is what you'll want to see."""
        if self.tray_state in ("ready", "check", "problem", "empty") and not self.controller.is_capturing():
            self.controller.show_prompt_in_window(None)
            self.prompt_settled = True
            self._refresh_tray()
        self.show_main()

    def _start_tray(self) -> None:
        import pystray

        self.images = tray_images()

        def on_screen_item(value: str, label: str):
            return pystray.MenuItem(label, lambda icon, item: self.controller.update_settings({"on_screen": value}), checked=lambda item: self.controller.settings["on_screen"] == value, radio=True)

        def toggle_label(item) -> str:
            return "Stop recording" if self.controller.is_recording() else "Record a meeting"

        def on_toggle(icon, item):
            self._toggle()

        def nothing_listening(item) -> bool:
            return not self.controller.is_recording() and not self.controller.prompt_recorder

        menu = pystray.Menu(
            pystray.MenuItem("Open Brushtalk", lambda icon, item: self._open_from_tray(), default=True),
            pystray.MenuItem(toggle_label, on_toggle),
            pystray.MenuItem("Record a solo note", lambda icon, item: self._toggle("solo"), enabled=nothing_listening),
            pystray.MenuItem("Dictate a prompt", lambda icon, item: self._toggle("prompt"), enabled=nothing_listening),
            pystray.MenuItem("Dictate code", lambda icon, item: self._toggle("code"), enabled=nothing_listening),
            pystray.MenuItem("Proofread", lambda icon, item: self._toggle("proofread"), enabled=lambda item: not self.controller.prompt_recorder),
            pystray.MenuItem("Proofread without talking", lambda icon, item: self._proofread(), enabled=lambda item: not self.controller.prompt_recorder),
            pystray.MenuItem("Throw this one away", lambda icon, item: self.controller.drop_prompt(), visible=lambda item: bool(self.controller.prompt_recorder)),
            # For low key with only the tray: the bar's Undo isn't there to press.
            pystray.MenuItem("Bring back the one you cancelled", lambda icon, item: self._undo_cancel(), visible=lambda item: self.controller.prompt_stage == "cancelled"),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("On screen", pystray.Menu(*(on_screen_item(*choice) for choice in ON_SCREEN))),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda icon, item: self.quit()),
        )
        self.tray = pystray.Icon("Brushtalk", self.images["idle"], "Brushtalk", menu)
        self.tray.run_detached()

    def _watch_recordings(self) -> None:
        while not self.quitting:
            time.sleep(1)
            try:
                self._check_recordings()
            except Exception:
                log.exception("Checking on the recording failed")

    def _check_recordings(self) -> None:
        """A sound, the bar and a tray notice for each thing going wrong with a recording, because the windows may well be hidden during a call."""
        for recorder in (self.controller.recorder, self.controller.prompt_recorder, self.controller.model_test):
            text = recorder.alert() if recorder else None
            if text:
                self.controller.recording_went_wrong()
                # A model test has no bar. Otherwise it comes back even if you hid it, or it couldn't show you anything.
                if self.mini and recorder is not self.controller.model_test and self.controller.settings["on_screen"] != "tray":
                    self._on_bar_thread(self.mini.native.Show)
                self.notify(text)
        self._refresh_tray()

    def _toggle(self, mode: str = "meeting") -> None:
        try:
            self.controller.toggle_recording(mode)
        except Exception as exc:
            log.exception("Toggle failed")
            self.controller.sound_when_quiet("problem")
            self.notify(str(exc))

    def _proofread(self) -> None:
        try:
            self.controller.proofread()
        except Exception as exc:
            log.exception("Proofreading failed")
            self.controller.sound_when_quiet("problem")
            self.notify(str(exc))

    def _undo_cancel(self) -> None:
        try:
            self.controller.undo_cancel()
        except Exception as exc:
            log.exception("Bringing back a cancelled prompt failed")
            self.notify(str(exc))

    def _finish(self) -> None:
        try:
            self.controller.finish()
        except Exception as exc:
            log.exception("Finishing failed")
            self.controller.sound_when_quiet("problem")
            self.notify(str(exc))

    def _on_event(self, event: str, **data) -> None:
        if event == "recording_started":
            self.show_mini()
            if data.get("mode") == "solo":
                self.notify("Recording your note.", routine=True)
            else:
                # Even in low key: the people on a call are meant to know, so this isn't a thing to keep out of sight.
                self.notify("Recording. Make sure everyone on the call has agreed.")
        elif event == "recording_stopped":
            self.hide_mini()
            after = data.get("after", "notes")
            if after == "notes":
                self.notify("Saved. Your notes are on the way.", routine=True)
            elif after == "save":
                self.notify("Saved without notes. You can make them later from the meeting.", routine=True)
        elif event == "recording_recycled":
            self.notify("Recording deleted. It's in the Recycle Bin.", routine=True)
        elif event == "notes_ready":
            self.notify(f"{data.get('title', 'Meeting')}: {data.get('message', 'Ready.')}", routine=True)
        elif event == "job_failed":
            self.notify(f"{data.get('title', 'Meeting')}: {data.get('message', 'Something went wrong.')}")
        elif event == "settings_changed":
            patch = data.get("patch", {})
            if self.hotkeys:
                for name in self.hotkeys.names:
                    if name in patch:
                        self.hotkeys.rebind(name, patch[name])
                self.controller.hotkey_errors = dict(self.hotkeys.errors)
            if "start_with_windows" in patch:
                threading.Thread(target=set_autostart, args=(bool(patch["start_with_windows"]),), daemon=True).start()
            if "show_mini" in patch and self.controller.is_recording():
                (self.show_mini if patch["show_mini"] else self.hide_mini)()
            if "theme" in patch:
                self._paint_title_bar()
            if "on_screen" in patch:
                self._on_screen_changed()
        elif event == "prompt_stage":
            self._on_prompt_stage(data.get("stage"))
        self._refresh_tray()

    # ------------------------------------------------------------- start

    def _paint_title_bar(self) -> None:
        try:
            self.main.events.loaded.wait(15)
            handle = self.main.native.Handle.ToInt64()
            paint_title_bar(handle, resolved_theme(self.controller.settings["theme"]))
        except Exception:
            log.exception("Colouring the title bar failed")

    def _on_started(self) -> None:
        self._start_tray()
        self._paint_title_bar()
        self._prepare_bar()
        if self.controller.is_recording():
            self.show_mini()

    def run(self) -> None:
        import webview

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        settings = self.controller.settings
        self.hotkeys = Hotkeys(
            {
                "hotkey": (settings["hotkey"], self._toggle),
                "hotkey_solo": (settings["hotkey_solo"], lambda: self._toggle("solo")),
                "hotkey_prompt": (settings["hotkey_prompt"], lambda: self._toggle("prompt")),
                "hotkey_code": (settings["hotkey_code"], lambda: self._toggle("code")),
                "hotkey_proofread": (settings["hotkey_proofread"], lambda: self._toggle("proofread")),
                "hotkey_proofread_text": (settings["hotkey_proofread_text"], self._proofread),
                "hotkey_finish": (settings["hotkey_finish"], self._finish),
            }
        )
        threading.Thread(target=self._watch_recordings, daemon=True, name="alerts").start()
        self.hotkeys.start()
        self.hotkeys.ready.wait(2)
        self.controller.hotkey_errors = dict(self.hotkeys.errors)

        window_color = WINDOW_COLORS[resolved_theme(settings["theme"])]
        self.main = webview.create_window(
            "Brushtalk",
            self.base_url,
            width=1200,
            height=800,
            min_size=(860, 560),
            background_color=window_color,
            hidden=self.start_hidden,
            text_select=True,
        )
        self.main.events.closing += self._on_closing
        mini_url = self.base_url.replace("/?", "/mini?")
        # Top right of the main screen, clear of most call windows' controls, or wherever _prepare_bar then puts it. The main screen is the one at 0, 0,
        # which isn't always listed first.
        screen = next((item for item in webview.screens if not item.x and not item.y), webview.screens[0])
        self.mini = webview.create_window(
            "Brushtalk recording",
            mini_url,
            width=BAR_WIDTH,
            height=64,
            x=screen.width - BAR_WIDTH - 24,
            y=24,
            frameless=True,
            easy_drag=True,
            on_top=True,
            hidden=True,
            focus=False,
            resizable=False,
            background_color=window_color,
            shadow=True,
        )
        webview.start(self._on_started, private_mode=False, storage_path=str(DATA / "webview"), icon=str(ICON_PATH))
