"""Meetings on disk: one folder each, plain files only.

meta.json        title, times, status
mic.pcm/system.pcm   raw tracks while recording, replaced by audio.flac (left = you, right = them)
transcript.json  [{speaker, start, end, text}]
notes.md         the notes, as you see and edit them
my_notes.md      your own notes, which nothing else writes to
originals/       every version the AI wrote, each with its raw reply: read-only, and never written to again
transcripts/     every transcript made, with the model that made it; transcript.json is the one in use
"""
from __future__ import annotations

import calendar
import json
import logging
import os
import re
import stat
import threading
import time
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf
from send2trash import send2trash

from .audio import RATE
from .config import load_settings, write_json, write_text_safely

log = logging.getLogger(__name__)

ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}(-\d+)?$")
ORIGINALS = "originals"
TRANSCRIPTS = "transcripts"
PROCESSING = ("saving", "transcribing", "notes")
# Playback evens out the two sides, because a quiet mic can sit far below the call. The saved file isn't changed.
PLAYBACK_TARGET = 0.16  # about -16 dBFS, for the loudest few seconds of speech
PLAYBACK_PEAK = 0.7  # leaves room for both sides talking at once
PLAYBACK_MAX_GAIN = 16.0
SILENT_PEAK = 0.002
_text_cache: dict[str, tuple[float, str]] = {}
_lock = threading.RLock()


@lru_cache(maxsize=1)
def meetings_dir() -> Path:
    path = Path(load_settings()["meetings_dir"])
    path.mkdir(parents=True, exist_ok=True)
    return path


def folder(meeting_id: str) -> Path:
    if not ID_RE.match(meeting_id):
        raise ValueError("Bad meeting id")
    return meetings_dir() / meeting_id


def create(title: str = "", mode: str = "meeting") -> dict:
    now = datetime.now().astimezone()
    base = now.strftime("%Y-%m-%d_%H%M%S")
    meeting_id, n = base, 1
    with _lock:
        while (meetings_dir() / meeting_id).exists():
            n += 1
            meeting_id = f"{base}-{n}"
        path = meetings_dir() / meeting_id
        path.mkdir(parents=True)
    meta = {
        "id": meeting_id,
        "title": title.strip() or f"{'Note' if mode == 'solo' else 'Call'} on {now.strftime('%b')} {now.day}, {now.strftime('%I:%M %p').lstrip('0')}",
        "title_source": "user" if title.strip() else "default",
        "mode": mode,
        "started_at": now.isoformat(timespec="seconds"),
        "duration": 0,
        "status": "recording",
        "error": None,
        "failed_stage": None,
        "warnings": [],
        "notes_edited": False,
        "notes_stale": False,
    }
    write_json(path / "meta.json", meta)
    return meta


def load_meta(meeting_id: str) -> dict:
    # Under the lock, because Windows won't let a file be read while it's being replaced, or replaced while it's being read.
    with _lock:
        return json.loads((folder(meeting_id) / "meta.json").read_text(encoding="utf-8"))


def update_meta(meeting_id: str, **changes) -> dict:
    with _lock:
        meta = load_meta(meeting_id)
        meta.update(changes)
        write_json(folder(meeting_id) / "meta.json", meta)
    return meta


def list_ids() -> list[str]:
    root = meetings_dir()
    ids = [p.name for p in root.iterdir() if p.is_dir() and ID_RE.match(p.name) and (p / "meta.json").exists()]
    return sorted(ids, reverse=True)


def list_meetings(query: str = "") -> list[dict]:
    out = []
    terms = query.lower().split()
    for meeting_id in list_ids():
        try:
            meta = load_meta(meeting_id)
        except (OSError, json.JSONDecodeError):
            continue
        if terms:
            haystack = (meta["title"] + "\n" + _searchable_text(meeting_id)).lower()
            if not all(term in haystack for term in terms):
                continue
        out.append(meta)
    return out


def _searchable_text(meeting_id: str) -> str:
    path = folder(meeting_id)
    stamp = 0.0
    parts = []
    for name in ("notes.md", "my_notes.md", "transcript.json"):
        file = path / name
        if file.exists():
            stamp += file.stat().st_mtime
    cached = _text_cache.get(meeting_id)
    if cached and cached[0] == stamp:
        return cached[1]
    with _lock:
        for name in ("notes.md", "my_notes.md"):
            if (path / name).exists():
                parts.append((path / name).read_text(encoding="utf-8"))
    parts.extend(line["text"] for line in load_transcript(meeting_id))
    text = "\n".join(parts)
    _text_cache[meeting_id] = (stamp, text)
    return text


def load_transcript(meeting_id: str) -> list[dict]:
    path = folder(meeting_id) / "transcript.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def write_transcript(meeting_id: str, lines: list[dict]) -> None:
    write_json(folder(meeting_id) / "transcript.json", lines)


def load_notes(meeting_id: str) -> str | None:
    path = folder(meeting_id) / "notes.md"
    with _lock:
        return path.read_text(encoding="utf-8") if path.exists() else None


def save_notes(meeting_id: str, text: str) -> None:
    with _lock:
        write_text_safely(folder(meeting_id) / "notes.md", text)


def save_transcript_version(meeting_folder: Path, lines: list[dict], **details) -> str:
    """Files a transcript from one model run, so different models can be compared on the same recording."""
    path = meeting_folder / TRANSCRIPTS
    path.mkdir(exist_ok=True)
    now = datetime.now().astimezone()
    base = now.strftime("%Y-%m-%d_%H%M%S")
    name, n = base, 1
    while (path / f"{name}.json").exists():
        n += 1
        name = f"{base}-{n}"
    clean = [{k: v for k, v in line.items() if k != "words"} for line in lines]
    record = {**details, "created_at": now.isoformat(timespec="seconds"), "lines": clean}
    write_text_safely(path / f"{name}.json", json.dumps(record, indent=1, ensure_ascii=False))
    return name


def file_existing_transcript(meeting_id: str) -> None:
    """A transcript from before versions were kept: file it the first time another model is tried."""
    path = folder(meeting_id)
    if (path / TRANSCRIPTS).exists() or not (path / "transcript.json").exists():
        return
    meta = load_meta(meeting_id)
    name = save_transcript_version(
        path,
        load_transcript(meeting_id),
        engine=meta.get("transcript_engine", "whisper"),
        label=meta.get("transcribed_with", "Whisper large-v3-turbo"),
        device=meta.get("compute_device"),
    )
    update_meta(meeting_id, transcript_version=name)


def _readable_record(file: Path) -> dict | None:
    """A kept version, or None if it can't be read. One bad file left by a failing disk mustn't stop the rest of its page opening."""
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("Skipped %s: %s", file, exc)
        return None


def list_transcript_versions(meeting_id: str) -> list[dict]:
    """Newest first, without the lines themselves."""
    out = []
    files = (folder(meeting_id) / TRANSCRIPTS).glob("*.json")
    for file in sorted(files, key=lambda f: (f.stem[:17], int(f.stem[18:] or 1)), reverse=True):
        record = _readable_record(file)
        if record:
            lines = record.pop("lines", [])
            out.append({"name": file.stem, "count": len(lines), **record})
    return out


def load_transcript_version(meeting_id: str, name: str) -> dict:
    if not ID_RE.match(name):
        raise ValueError("Bad version name")
    return json.loads((folder(meeting_id) / TRANSCRIPTS / f"{name}.json").read_text(encoding="utf-8"))


def load_my_notes(meeting_id: str) -> str:
    path = folder(meeting_id) / "my_notes.md"
    with _lock:
        return path.read_text(encoding="utf-8") if path.exists() else ""


def save_my_notes(meeting_id: str, text: str) -> None:
    with _lock:
        write_text_safely(folder(meeting_id) / "my_notes.md", text)


def keep_original(meeting_id: str, markdown: str, raw: dict | None = None, **details) -> str:
    """Files a version of the AI's notes for good. Only ever adds a new file: nothing in the app writes to these again."""
    path = folder(meeting_id) / ORIGINALS
    path.mkdir(exist_ok=True)
    now = datetime.now().astimezone()
    base = now.strftime("%Y-%m-%d_%H%M%S")
    name, n = base, 1
    while (path / f"{name}.md").exists():
        n += 1
        name = f"{base}-{n}"
    record = {**details, "written_at": now.isoformat(timespec="seconds"), "reply": raw}
    for file, text in ((path / f"{name}.md", markdown), (path / f"{name}.json", json.dumps(record, indent=1, ensure_ascii=False))):
        write_text_safely(file, text)
        os.chmod(file, stat.S_IREAD)
    return name


def file_existing_notes(meeting_id: str) -> None:
    """Notes written before originals were kept: file them the first time they're about to change."""
    path = folder(meeting_id)
    if (path / ORIGINALS).exists() or not (path / "notes.md").exists():
        return
    meta = load_meta(meeting_id)
    if not meta.get("notes_edited"):
        keep_original(meeting_id, load_notes(meeting_id), engine=meta.get("notes_engine"), model=meta.get("notes_model"))


def list_originals(meeting_id: str) -> list[dict]:
    """Newest first."""
    out = []
    files = (folder(meeting_id) / ORIGINALS).glob("*.json")
    for file in sorted(files, key=lambda f: (f.stem[:17], int(f.stem[18:] or 1)), reverse=True):
        record = _readable_record(file)
        if record:
            out.append({"name": file.stem, **{k: record.get(k) for k in ("engine", "model", "effort", "written_at")}})
    return out


def load_original(meeting_id: str, name: str) -> str:
    if not ID_RE.match(name):
        raise ValueError("Bad original name")
    return (folder(meeting_id) / ORIGINALS / f"{name}.md").read_text(encoding="utf-8")


def audio_path(meeting_id: str) -> Path | None:
    path = folder(meeting_id) / "audio.flac"
    return path if path.exists() else None


def has_raw_audio(meeting_id: str) -> bool:
    path = folder(meeting_id)
    return (path / "mic.pcm").exists() or (path / "system.pcm").exists()


def holds_audio(path: Path) -> bool:
    """Whether a folder has anything in it worth keeping: a finished FLAC, or raw tracks with something in them."""
    if (path / "audio.flac").exists():
        return True
    return any((path / name).exists() and (path / name).stat().st_size > 0 for name in ("mic.pcm", "system.pcm"))


def raw_seconds(path: Path) -> float:
    """How long the raw tracks run, going by the longer one."""
    sizes = [(path / name).stat().st_size for name in ("mic.pcm", "system.pcm") if (path / name).exists()]
    return max(sizes) / 2 / RATE if sizes else 0.0


def saved_seconds(path: Path) -> float:
    return sf.info(str(path / "audio.flac")).frames / RATE


def has_saved_work(path: Path) -> bool:
    """Whether a folder holds anything that couldn't be made again, so it's never cleared away as an empty recording."""
    return any((path / name).exists() for name in ("audio.flac", "notes.md", "my_notes.md", "transcript.json"))


def _remove_raw(*paths: Path) -> None:
    for path in paths:
        for attempt in range(20):
            try:
                path.unlink(missing_ok=True)
                break
            except PermissionError:
                # Anything holding the file open for a moment, such as a virus scanner, makes Windows refuse.
                if attempt == 19:
                    raise
                time.sleep(0.05)


def finalize_audio(path: Path) -> Path:
    """Turn the raw tracks into one stereo FLAC, verify it, then remove them. Safe to run again after a crash, or after any step of this failed."""
    mic_path, system_path, flac = path / "mic.pcm", path / "system.pcm", path / "audio.flac"
    if not mic_path.exists() and not system_path.exists():
        if flac.exists():
            return flac
        raise FileNotFoundError("This meeting has no audio.")
    sizes = [p.stat().st_size // 2 if p.exists() else 0 for p in (mic_path, system_path)]
    total = max(sizes)
    if flac.exists():
        # The FLAC is in place, so it was removing the raw tracks that got cut short, and one of them may already be gone.
        # Building it again from what's left would put silence where that track was.
        if sf.info(str(flac)).frames >= total:
            _remove_raw(mic_path, system_path)
            return flac
        if not (mic_path.exists() and system_path.exists()):
            raise RuntimeError("The saved audio and the raw tracks don't match, so both were kept.")
    tmp = path / "audio.flac.part"
    chunk = RATE * 30
    mic_file = open(mic_path, "rb") if mic_path.exists() else None
    system_file = open(system_path, "rb") if system_path.exists() else None
    try:
        with sf.SoundFile(tmp, "w", samplerate=RATE, channels=2, subtype="PCM_16", format="FLAC") as out:
            written = 0
            while written < total:
                count = min(chunk, total - written)
                frame = np.zeros((count, 2), dtype=np.int16)
                for index, handle in enumerate((mic_file, system_file)):
                    if handle:
                        raw = handle.read(count * 2)
                        data = np.frombuffer(raw[: len(raw) // 2 * 2], dtype="<i2")
                        frame[: len(data), index] = data
                out.write(frame)
                written += count
    finally:
        for handle in (mic_file, system_file):
            if handle:
                handle.close()
    if sf.info(str(tmp)).frames != total:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("Saving the audio failed a size check, so the raw tracks were kept.")
    tmp.replace(flac)
    _remove_raw(mic_path, system_path)
    return flac


def playback_gains(path: Path) -> dict:
    """How much to raise or lower each side of a recording when it's played."""
    frames, peaks = [], np.zeros(2)
    for block in sf.blocks(str(path), blocksize=RATE // 10, dtype="float32", always_2d=True):
        frames.append(np.sqrt(np.mean(block**2, axis=0)))
        peaks = np.maximum(peaks, np.abs(block).max(axis=0))
    if not frames:
        return {"you": 1.0, "them": 1.0}
    # The loudest five seconds, so long silences don't count and a single bump doesn't decide it.
    loudest = np.sort(np.array(frames), axis=0)[-50:]
    levels = np.sqrt(np.mean(loudest**2, axis=0))
    gains = [
        1.0 if peak < SILENT_PEAK else min(PLAYBACK_TARGET / level, PLAYBACK_PEAK / peak, PLAYBACK_MAX_GAIN)
        for level, peak in zip(levels, peaks)
    ]
    return {"you": round(float(gains[0]), 3), "them": round(float(gains[1]), 3)}


def delete_meeting(meeting_id: str) -> None:
    """To the Recycle Bin, so a wrong click can be undone."""
    send2trash(str(folder(meeting_id)))
    _text_cache.pop(meeting_id, None)


def delete_audio(meeting_id: str) -> None:
    path = audio_path(meeting_id)
    if path:
        send2trash(str(path))


AUDIO_FILES = ("audio.flac", "mic.pcm", "system.pcm")


def audio_use(folders: list[Path]) -> dict:
    """How many of these folders hold audio, and how much of it, for what Settings says the recordings take."""
    count = size = 0
    for path in folders:
        sizes = [(path / name).stat().st_size for name in AUDIO_FILES if (path / name).exists()]
        if sizes:
            count, size = count + 1, size + sum(sizes)
    return {"count": count, "bytes": size}


def months_before(day: date, months: int) -> date:
    """The same day so many calendar months earlier, or the last day of that month if it's shorter."""
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def old_audio(months: int, today: date | None = None) -> list[dict]:
    """Meetings whose audio is older than so many months and can go. Only transcribed ones, so the transcript and notes stay: a
    recording that was never transcribed is all there is of it, so it's never on the list."""
    before = months_before(today or date.today(), months)
    found = []
    for meta in list_meetings():
        audio = audio_path(meta["id"])
        if not audio or meta.get("status") != "done" or not load_transcript(meta["id"]):
            continue
        started = datetime.fromisoformat(meta["started_at"]).date() if meta.get("started_at") else date.fromisoformat(meta["id"][:10])
        if started < before:
            found.append({"id": meta["id"], "bytes": audio.stat().st_size})
    return found
