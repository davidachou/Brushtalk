"""Test models: you talk, every speech model writes down what it heard, and you score them.

Each test is a folder in data/model_tests, kept apart from meetings so tests never show up in the list, the search or the
Overview.

meta.json     when, and one entry per model run: how it went and the score you gave it
audio.flac    your microphone
transcripts/  what each model heard
"""
from __future__ import annotations

import json
import logging
import shutil
import threading
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from statistics import mean, median

from send2trash import send2trash

from . import instructions
from .config import DATA, write_json
from .storage import ID_RE, TRANSCRIPTS, finalize_audio, holds_audio
from .transcript import TOKEN

log = logging.getLogger(__name__)

LANGUAGES = ("mixed", "en", "zh", "auto")
HINTS = ("talking", "meeting", "none")
UNFINISHED = ("waiting", "running")
# Comparing every model's words with every other's gets slow on very long clips, and marks stop being any use there.
MARK_LIMIT = 8000
_lock = threading.RLock()


def tests_dir() -> Path:
    return DATA / "model_tests"


def folder(test_id: str) -> Path:
    if not ID_RE.match(test_id):
        raise ValueError("Bad test id")
    return tests_dir() / test_id


def create(language: str, hint: str = "talking") -> dict:
    now = datetime.now().astimezone()
    base = now.strftime("%Y-%m-%d_%H%M%S")
    test_id, n = base, 1
    with _lock:
        while (tests_dir() / test_id).exists():
            n += 1
            test_id = f"{base}-{n}"
        path = tests_dir() / test_id
        path.mkdir(parents=True)
        meta = {"id": test_id, "started_at": now.isoformat(timespec="seconds"), "language": language, "hint": hint, "duration": 0, "status": "recording", "runs": []}
        write_json(path / "meta.json", meta)
    return meta


def load(test_id: str) -> dict:
    # Under the lock, because Windows won't let a file be read while it's being replaced, or replaced while it's being read.
    with _lock:
        return json.loads((folder(test_id) / "meta.json").read_text(encoding="utf-8"))


def update(test_id: str, **changes) -> dict:
    with _lock:
        meta = load(test_id)
        meta.update(changes)
        write_json(folder(test_id) / "meta.json", meta)
    return meta


def add_runs(test_id: str, engines: list[dict], language: str, hint: str = "talking") -> None:
    with _lock:
        meta = load(test_id)
        meta["runs"] += [{"engine": engine["id"], "label": engine["label"], "language": language, "hint": hint, "hint_edit": instructions.edited_hint(engine["id"], hint, language), "built_in": instructions.built_in_hints(hint, language), "state": "waiting", "score": None} for engine in engines]
        write_json(folder(test_id) / "meta.json", meta)


def update_run(test_id: str, index: int, **changes) -> dict:
    with _lock:
        meta = load(test_id)
        meta["runs"][index].update(changes)
        write_json(folder(test_id) / "meta.json", meta)
    return meta["runs"][index]


def finish_run(test_id: str, index: int, version: str | None) -> None:
    """version is None when there was nothing to transcribe. The times come from what the model filed."""
    if not version:
        update_run(test_id, index, state="done", version=None)
        return
    record = json.loads((folder(test_id) / TRANSCRIPTS / f"{version}.json").read_text(encoding="utf-8"))
    update_run(test_id, index, state="done", version=version, seconds=record.get("seconds"), device=record.get("device"))


def is_busy(meta: dict) -> bool:
    return any(run["state"] in UNFINISHED for run in meta["runs"])


def give_up(test_id: str, error: str) -> None:
    """Nothing is working on this test any more, so it mustn't go on looking busy. Its audio stays, for trying again."""
    with _lock:
        meta = load(test_id)
        for run in meta["runs"]:
            if run["state"] in UNFINISHED:
                run["state"] = "stopped"
        meta.update(status="failed", error=error)
        write_json(folder(test_id) / "meta.json", meta)


def audio_path(test_id: str) -> Path | None:
    path = folder(test_id) / "audio.flac"
    return path if path.exists() else None


def _text_of(test_id: str, run: dict) -> str:
    if not run.get("version"):
        return ""
    try:
        record = json.loads((folder(test_id) / TRANSCRIPTS / f"{run['version']}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # One bad file left by a failing disk mustn't stop the rest of the test's page opening.
        log.warning("Couldn't read what %s wrote: %s", run.get("label"), exc)
        return ""
    return "\n".join(line["text"] for line in record.get("lines", []))


def mark_differences(texts: list[str]) -> list[list[list]]:
    """Splits each text into [piece, differs], marking the words no other text has. That's where to look when comparing."""
    tokens = [[(m.start(), m.end(), m.group().lower()) for m in TOKEN.finditer(text)] for text in texts]
    words = [[token[2] for token in row] for row in tokens]
    if len(texts) < 2 or sum(len(row) for row in words) > MARK_LIMIT:
        return [[[text, False]] if text else [] for text in texts]
    out = []
    for index, text in enumerate(texts):
        shared = [False] * len(words[index])
        for other, other_words in enumerate(words):
            if other == index or not other_words:
                continue
            for block in SequenceMatcher(None, words[index], other_words, autojunk=False).get_matching_blocks():
                shared[block.a : block.a + block.size] = [True] * block.size
        pieces, position = [], 0
        for (start, end, _), same in zip(tokens[index], shared):
            if same:
                continue
            if start > position:
                pieces.append([text[position:start], False])
            pieces.append([text[start:end], True])
            position = end
        if position < len(text):
            pieces.append([text[position:], False])
        out.append(pieces)
    return out


def detail(test_id: str) -> dict:
    meta = load(test_id)
    done = [run for run in meta["runs"] if run["state"] == "done"]
    for run, pieces in zip(done, mark_differences([_text_of(test_id, run) for run in done])):
        run["pieces"] = pieces
    return dict(meta, has_audio=audio_path(test_id) is not None, can_run=holds_audio(folder(test_id)))


def list_tests() -> list[dict]:
    """Newest first."""
    root = tests_dir()
    if not root.exists():
        return []
    out = []
    for path in sorted(root.iterdir(), key=lambda p: p.name, reverse=True):
        if path.is_dir() and ID_RE.match(path.name):
            try:
                out.append(load(path.name))
            except (OSError, json.JSONDecodeError):
                continue
    return out


def summaries() -> list[dict]:
    out = []
    for meta in list_tests():
        scored = [run for run in meta["runs"] if run.get("score")]
        best = max(scored, key=lambda run: run["score"]) if scored else None
        out.append(
            {
                "id": meta["id"],
                "started_at": meta["started_at"],
                "duration": meta["duration"],
                "language": meta["language"],
                "status": meta["status"],
                "best": best["label"] if best else None,
                "best_score": best["score"] if best else None,
            }
        )
    return out


def scoreboard() -> list[dict]:
    """Average score per model, separately for each language setting and hint: a model can be good at one and poor at another."""
    groups: dict[tuple[str, str, str | None], dict[str, dict]] = {}
    for meta in list_tests():
        for run in meta["runs"]:
            if run["state"] != "done":
                continue
            # Tests from before there was a choice of hint used the meeting one. Runs from before the built-in hints were noted have none.
            key = (run["language"], run.get("hint", "meeting"), run.get("hint_edit"), run.get("built_in"))
            row = groups.setdefault(key, {}).setdefault(run["engine"], {"engine": run["engine"], "label": run["label"], "scores": [], "seconds": []})
            if run.get("score"):
                row["scores"].append(run["score"])
            if run.get("seconds") is not None:
                row["seconds"].append(run["seconds"])
    out = []
    for (language, hint, hint_edit, built_in), rows in groups.items():
        models = [
            {
                "engine": row["engine"],
                "label": row["label"],
                "average": round(mean(row["scores"]), 1) if row["scores"] else None,
                "scored": len(row["scores"]),
                "seconds": round(median(row["seconds"]), 1) if row["seconds"] else None,
            }
            for row in rows.values()
        ]
        models.sort(key=lambda model: (-(model["average"] or 0), model["label"]))
        # "earlier" is the built-in hints as they were before a rewrite, and "unknown" is from before they were noted.
        hints = "unknown" if built_in is None else "current" if built_in == instructions.built_in_hints(hint, language) else "earlier"
        out.append({"language": language, "hint": hint, "hint_edit": hint_edit, "hints": hints, "models": models})
    return out


def recover() -> dict[str, str]:
    """After a crash or a quit nothing is running any more. Only a clip with no audio at all is removed: audio that can't be saved
    properly yet stays as it is, to try again. A clip that can't even be marked is left for the next start, and doesn't stop the others, or the app
    opening. Returns what to tell you about those."""
    failures = {}
    for meta in list_tests():
        try:
            _recover_one(meta)
        except Exception as exc:
            log.warning("Couldn't pick up test %s: %s", meta["id"], exc)
            failures[f"test {meta['id']}"] = f"A test clip couldn't be picked up after the app closed, but its files are still there: {exc}"
    return failures


def _recover_one(meta: dict) -> None:
    path = folder(meta["id"])
    if meta["status"] in ("recording", "saving", "failed"):
        if not holds_audio(path):
            shutil.rmtree(path, ignore_errors=True)
            return
        try:
            finalize_audio(path)
            update(meta["id"], status="saved", error=None)
        except (OSError, RuntimeError) as exc:
            log.warning("Couldn't save the audio of test %s: %s", meta["id"], exc)
            give_up(meta["id"], f"This clip's audio couldn't be saved yet: {exc}")
            return
    for index, run in enumerate(meta["runs"]):
        if run["state"] in UNFINISHED:
            update_run(meta["id"], index, state="stopped")


def delete(test_id: str) -> None:
    """To the Recycle Bin, like a meeting."""
    send2trash(str(folder(test_id)))
