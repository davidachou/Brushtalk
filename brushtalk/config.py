"""Settings and paths. Settings live in data/settings.json and are written atomically."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("BRUSHTALK_DATA") or ROOT / "data")
SETTINGS_PATH = DATA / "settings.json"
INSTANCE_PATH = DATA / ".instance.json"
LOG_DIR = DATA / "logs"
UI_DIR = Path(__file__).resolve().parent / "ui"
MODEL_NAME = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
# Where Whisper is looked for: the app's own models folder, where it downloads, then the usual download cache.
MODEL_SEARCH = [
    ROOT / "models",
    Path.home() / ".cache" / "huggingface" / "hub",
]

DEFAULTS = {
    "meetings_dir": str(DATA / "meetings"),
    "mic_device": "default",
    "output_device": "all",
    "language": "en",
    "chinese_script": "traditional",
    "compute": "auto",
    "speech_engine": "whisper",
    "speakers": False,
    "whisper_model": "",
    "terms": "",
    "notes_engine": "codex",
    "codex_model": "gpt-6.1-terra",
    "codex_effort": "medium",
    "claude_model": "claude-sonnet-5-5",
    "claude_effort": "medium",
    "notes_language": "same",
    "extra_instructions": "",
    "after_stop": "notes",
    "hotkey": "Ctrl+Alt+R",
    "show_mini": True,
    "close_to_tray": True,
    "start_with_windows": False,
    "notice_text": "Quick heads up: I'd like to record this call so I can take notes. "
    "The recording stays on my computer, and the transcript goes to an AI service to write the notes. "
    "Let me know if you'd rather I didn't.",
    "onboarded": False,
    "test_language": "mixed",
    "test_hint": "talking",
    "test_skip": [],
    "hotkey_solo": "Ctrl+Alt+N",
    "hotkey_prompt": "Ctrl+Alt+D",
    "hotkey_finish": "Ctrl+Alt+Enter",
    "prompt_engine": "codex",
    "prompt_codex_model": "gpt-6.1-terra",
    "prompt_codex_effort": "medium",
    "prompt_claude_model": "claude-sonnet-5-5",
    "prompt_claude_effort": "medium",
    "prompt_speech_engine": "whisper",
    "prompt_language": "en",
    "prompt_use_copied": True,
    "prompt_include_copied": False,
    "prompt_add_knowledge": True,
    "prompt_check_first": False,
    "prompt_extra": "",
    "hotkey_code": "Ctrl+Alt+C",
    "code_engine": "codex",
    "code_codex_model": "gpt-6-astra",  # the one exception: Terra's SQL twice didn't run as pasted (research_notes/Code mode)
    "code_codex_effort": "medium",
    "code_claude_model": "claude-opus-5-5",  # the owner's pick for code
    "code_claude_effort": "medium",
    "code_extra": "",
    "hotkey_proofread": "Ctrl+Alt+P",  # listens too, so you can say how. Finishing straight away is a plain proofread.
    "hotkey_proofread_text": "Ctrl+Alt+Shift+P",  # one press, no mic
    "proofread_engine": "codex",
    "proofread_codex_model": "gpt-6.1-terra",
    "proofread_codex_effort": "medium",
    "proofread_claude_model": "claude-sonnet-5-5",
    "proofread_claude_effort": "medium",
    "proofread_extra": "",
    "theme": "ink",
    "motion": True,
    "sounds": True,
    "copy_sound": True,  # its own switch: it's the one sound that plays while recording, so the mic can hear it
    "on_screen": "bar",
    "bar_place": None,  # where you last dragged the full bar, and the tiny character, as left and top
    "mark_place": None,
}

_lock = threading.Lock()


def write_text_safely(path: Path, text: str) -> None:
    """Write through a temp file, so a crash or a full disk never leaves half a file behind, or an empty one where a good one was."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        for attempt in range(20):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                # Anything holding the file open for a moment, such as a virus scanner, makes Windows refuse.
                if attempt == 19:
                    raise
                time.sleep(0.05)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def write_json(path: Path, data) -> None:
    write_text_safely(path, json.dumps(data, indent=2, ensure_ascii=False))


# Claude models used to be saved by the claude tool's short names, which move to each new release. These are what they meant when the full names came in.
CLAUDE_SHORT_NAMES = {"sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5", "haiku": "claude-haiku-5-5"}


def load_settings() -> dict:
    with _lock:
        settings = dict(DEFAULTS)
        if SETTINGS_PATH.exists():
            try:
                saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                settings.update({k: v for k, v in saved.items() if k in DEFAULTS})
            except (json.JSONDecodeError, OSError):
                pass
        for key in [key for key in settings if key.endswith("claude_model")]:
            settings[key] = CLAUDE_SHORT_NAMES.get(settings[key], settings[key])
        return settings


def save_settings(patch: dict) -> dict:
    with _lock:
        settings = dict(DEFAULTS)
        if SETTINGS_PATH.exists():
            try:
                settings.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass
        settings.update({k: v for k, v in patch.items() if k in DEFAULTS})
        write_json(SETTINGS_PATH, settings)
        return settings


def find_whisper_model(settings: dict) -> str | None:
    """Local folder holding the turbo model, or None if it still has to be downloaded."""
    explicit = (settings.get("whisper_model") or "").strip()
    if explicit and (Path(explicit) / "model.bin").exists():
        return explicit
    for base in MODEL_SEARCH:
        for model_bin in sorted(base.glob("models--*faster-whisper-large-v3-turbo/snapshots/*/model.bin")):
            return str(model_bin.parent)
    return None
