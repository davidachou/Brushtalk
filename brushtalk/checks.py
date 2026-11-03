"""The setup check shown in Settings: is everything the app relies on actually there?"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from . import engines
from .audio import device_key, list_devices
from .config import find_whisper_model, load_settings
from .notes import find_claude, find_codex
from .storage import meetings_dir


def _run(command: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        out = subprocess.run(
            command,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return out.returncode, (out.stdout + out.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)


def _item(key: str, label: str, status: str, detail: str) -> dict:
    return {"id": key, "label": label, "status": status, "detail": detail}


def check_microphone(settings: dict, devices: dict) -> dict:
    wanted = settings["mic_device"]
    if wanted != "default":
        match = next((m for m in devices["mics"] if device_key(m) == device_key(wanted)), None)
        if match:
            return _item("mic", "Microphone", "ok", match)
        fallback = devices["default_mic"]
        if fallback:
            return _item("mic", "Microphone", "warn", f"{wanted} isn't connected. Using {fallback} instead.")
        return _item("mic", "Microphone", "fail", f"{wanted} isn't connected, and there's no other microphone.")
    if devices["default_mic"]:
        return _item("mic", "Microphone", "ok", devices["default_mic"])
    return _item("mic", "Microphone", "fail", "No microphone found.")


def check_output(settings: dict, devices: dict) -> dict:
    if not devices["outputs"]:
        return _item("output", "Computer audio", "fail", "No speakers or headphones found.")
    if settings["output_device"] == "all":
        count = len(devices["outputs"])
        return _item("output", "Computer audio", "ok", f"Listening to all {count} outputs, so nothing gets missed.")
    return _item("output", "Computer audio", "ok", settings["output_device"])


def check_model(settings: dict) -> dict:
    chosen = engines.get(settings["speech_engine"])
    others = [engine["label"] for engine in engines.available() if engine["id"] not in (chosen["id"], "whisper")]
    also = f" Also installed: {', '.join(others)}." if others else ""
    if chosen["id"] != "whisper":
        return _item("model", "Speech model", "ok", f"{chosen['label']}, with Whisper as the backup.{also}")
    if find_whisper_model(settings):
        return _item("model", "Speech model", "ok", f"Whisper large-v3-turbo is on this PC.{also}")
    return _item("model", "Speech model", "warn", "It downloads the first time you record, about 1.6 GB.")


def check_gpu() -> dict:
    code, out = _run(["nvidia-smi", "--query-gpu=name,memory.free", "--format=csv,noheader,nounits"], 10)
    if code != 0 or not out:
        return _item("gpu", "Graphics card", "warn", "No NVIDIA GPU found. Transcribing will use the CPU, which is slower.")
    name, _, free = out.splitlines()[0].partition(",")
    site = Path(sys.executable).resolve().parent.parent / "Lib" / "site-packages" / "nvidia" / "cublas" / "bin"
    if not site.exists():
        return _item("gpu", "Graphics card", "warn", f"{name.strip()} found, but its libraries are missing. Using the CPU.")
    return _item("gpu", "Graphics card", "ok", f"{name.strip()}, {int(free.strip()) / 1024:.0f} GB free right now.")


def check_notes_engine(settings: dict) -> list[dict]:
    engine = settings["notes_engine"]
    items = []
    codex = find_codex()
    if codex:
        code, out = _run([codex, "login", "status"])
        if code == 0 and "logged in" in out.lower():
            items.append(_item("codex", "Codex", "ok", out.splitlines()[0]))
        else:
            status = "fail" if engine == "codex" else "warn"
            items.append(_item("codex", "Codex", status, "Installed, but not signed in. Run: codex login"))
    else:
        status = "fail" if engine == "codex" else "warn"
        items.append(_item("codex", "Codex", status, "Not found."))
    claude = find_claude()
    if claude:
        # It says whether it's signed in, as Codex does. A version from before it could gets the old check, which can't tell.
        code, out = _run([claude, "auth", "status"])
        try:
            signed_in = json.loads(out).get("loggedIn")
        except (ValueError, AttributeError):
            signed_in = None
        if signed_in is True:
            items.append(_item("claude", "Claude Code", "ok", "Signed in."))
        elif signed_in is False:
            status = "fail" if engine == "claude" else "warn"
            items.append(_item("claude", "Claude Code", status, f'Installed, but not signed in. Run "{claude}" and sign in.'))
        else:
            code, out = _run([claude, "--version"])
            version = out.splitlines()[0] if out else "found"
            items.append(_item("claude", "Claude Code", "ok" if code == 0 else "warn", version))
    else:
        status = "fail" if engine == "claude" else "warn"
        items.append(_item("claude", "Claude Code", status, "Not found. It isn't needed unless you switch to it."))
    return items


def check_disk() -> dict:
    free = shutil.disk_usage(meetings_dir()).free / 1024**3
    status = "ok" if free > 5 else "warn"
    return _item("disk", "Storage", status, f"{free:,.0f} GB free. A one-hour call takes about 45 to 65 MB.")


def run_checks() -> list[dict]:
    settings = load_settings()
    try:
        devices = list_devices()
    except Exception as exc:
        items = [_item("mic", "Audio", "fail", f"Windows audio couldn't be read: {exc}")]
    else:
        items = [check_microphone(settings, devices), check_output(settings, devices)]
    items += [check_model(settings), check_gpu()]
    items += check_notes_engine(settings)
    items.append(check_disk())
    return items
