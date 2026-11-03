"""Speech models the app can use. Whisper is built in. The others live in engines/<name>/, each with its own
engine.json, and run as a separate program that reads a job file and writes a result file (see engines/README.md).
"""
from __future__ import annotations

import json
import logging
import subprocess

from .config import ROOT

log = logging.getLogger(__name__)

WHISPER = {"id": "whisper", "label": "Whisper large-v3-turbo", "labels_speakers": False, "needs_gb": 0, "summary": "built in, and can use the CPU if the graphics card is busy."}
ENGINES_DIR = ROOT / "engines"


def _load(folder) -> dict | None:
    try:
        data = json.loads((folder / "engine.json").read_text(encoding="utf-8"))
        if (ROOT / data["python"]).exists() and (ROOT / data["script"]).exists():
            return {"id": folder.name, **data}
    except (OSError, ValueError, KeyError) as exc:
        log.warning("Skipping speech model in %s: %s", folder, exc)
    return None


def _installed() -> list[dict]:
    if not ENGINES_DIR.exists():
        return []
    found = [_load(folder) for folder in sorted(ENGINES_DIR.iterdir()) if (folder / "engine.json").exists()]
    return [engine for engine in found if engine]


def available() -> list[dict]:
    """Transcribers, Whisper first."""
    return [WHISPER] + [engine for engine in _installed() if not engine.get("diarizer")]


def get(engine_id: str) -> dict:
    """Falls back to Whisper when a model has been removed."""
    return next((engine for engine in available() if engine["id"] == engine_id), WHISPER)


def diarizer() -> dict | None:
    return next((engine for engine in _installed() if engine.get("diarizer")), None)


def free_vram_gb() -> float | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return int(out.stdout.split()[0]) / 1024
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None
