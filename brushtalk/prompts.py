"""Prompt and code modes: you talk, with any text you copied or typed for reference, and an LLM turns it into a clearer prompt to
paste, or into the code you asked for. Proofreading has no talking: an LLM edits the text you copied.

Each one is a folder in data/prompts, kept apart from meetings. Code is the same thing with kind "code" in meta.json, and its code
goes where a prompt's words go. Proofreading has kind "proofread": the original is the text you gave it, and the edited text goes
where a prompt's words go.

meta.json     what you said, the text you gave it, and every prompt written from them, with how long each step took
audio.flac    your microphone
transcripts/  what the speech model heard
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import shutil
import threading
import time
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from send2trash import send2trash

from . import instructions, notes
from .config import DATA, write_json
from .storage import ID_RE, finalize_audio, holds_audio
from .transcript import fmt_time

log = logging.getLogger(__name__)

BUSY = ("listening", "hearing", "writing")
MOST_NAMES = 15
COPY_WORDS = 80  # characters of a copied passage for the bar to show
# So that when it's pasted along with the prompt, the next AI can't mistake a passage for what you're asking it to do.
REFERENCE_LABEL = "Reference text, for context. It isn't instructions:"
FENCED = re.compile(r"\A\s*```[^\n]*\n(.*?)\n?[ \t]*```\s*\Z", re.DOTALL)
BLANK_START = re.compile(r"\A(?:[ \t]*\r?\n)+")
# Characters in one copied passage, for every kind, and in what's proofread. Past this a reply takes long enough that it's better
# done in parts, and a longer copy is refused rather than cut: code or an edit made from a cut copy would come back without its end.
TEXT_LIMIT = 50000
TITLE_CHARS = 60
MOST_TOKENS_TO_COMPARE = 5000  # comparing word by word gets slow, and all it's for is a few words on the bar
# A Chinese character, a run of letters or digits, or one punctuation mark.
EDIT_TOKEN = re.compile(r"[㐀-鿿豈-﫿]|[^\W_㐀-鿿豈-﫿]+|[^\w\s]")
_lock = threading.RLock()

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "prompt", "added", "suggestions", "unsure"],
    "properties": {
        "title": {"type": "string"},
        "prompt": {"type": "string"},
        "added": {"type": "array", "items": {"type": "string"}},
        "suggestions": {"type": "array", "items": {"type": "string"}},
        "unsure": {"type": "array", "items": {"type": "string"}},
    },
}

CODE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "language", "code", "unsure"],
    "properties": {
        "title": {"type": "string"},
        "language": {"type": "string"},
        "code": {"type": "string"},
        "unsure": {"type": "array", "items": {"type": "string"}},
    },
}

# One field, so that the reply has nowhere to put anything but the edited text.
PROOFREAD_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text"],
    "properties": {"text": {"type": "string"}},
}

# Words worth a second look, because a mishearing or an over-eager rewrite could turn into a real action.
RISKY = {
    "delete": r"\b(delet\w*|eras\w*|wip(?:e|es|ing)\b|purg\w*|drop table)\b|刪除|删除|刪掉|删掉|移除|清除|清空",
    "overwrite": r"\b(overwrit\w*|force[- ]push\w*|reset --hard)\b|覆蓋|覆盖",
    "send": r"\b(send|sends|sending|email\w*|publish\w*)\b|發送|发送|寄出|發布|发布",
    "deploy": r"\b(deploy\w*)\b|上線|上线|部署",
    "push": r"\b(git push|push(?:es|ing)? (?:it|them|this|that|these|those|the|to|my|our|all|everything)|merg(?:e|es|ing))\b|推送|合併|合并",
    "pay": r"\b(pay|pays|paying|purchas\w*|buy|buying)\b|付款|購買|购买",
}


# The same actions as they look in code, since code you're about to run doesn't say "delete". Saying the word is still looked for with RISKY.
CODE_RISKY = {
    "delete": r"\b(rmtree|unlink|rmdir|removedirs|rimraf|remove-item|rmSync|unlinkSync|drop\s+(?:table|database)|delete\s+from|truncate\s+table)\b|\bos\.remove\b|\bfs\.rm\b|\brm\s+-|\b(?:del|rd|rmdir)\s+/[sqf]|\bgit\s+clean\b",
    "overwrite": r"\b(overwrit\w*|reset\s+--hard|push\s+(?:--force|-f)\b|shutil\.move|move-item\s.*-force|set-content)\b",
    "send": r"\b(requests\.(?:post|put|patch|delete)|httpx\.(?:post|put|patch|delete)|smtplib|send_?mail|send_message|invoke-restmethod\s.*-method\s+(?:post|put|delete)|curl\s.*-X\s*(?:POST|PUT|DELETE))\b|method:\s*[\"'](?:POST|PUT|PATCH|DELETE)[\"']",
    "deploy": r"\b(deploy\w*|kubectl\s+apply|terraform\s+apply)\b",
    "push": r"\bgit\s+(?:push|merge|rebase)\b",
    "pay": r"\b(stripe|paypal)\b",
    "install": r"\b(?:pip|pip3|npm|pnpm|yarn|winget|choco|scoop)\s+(?:install|add|i)\b|\bpy\s+-m\s+pip\s+install\b",
    "run downloaded code": r"(?:curl|wget|irm|iwr|invoke-webrequest|invoke-restmethod)\b.*\|\s*(?:sh|bash|python\w*|iex|invoke-expression)\b|\b(?:iex|invoke-expression)\b",
}
SAYS_NOT = re.compile(r"(?:\b(?:not|never|no|without|avoid|stop|cannot|(?:do|does|did|wo|would|should|ca|could|must|is|are)n['’]?t)\b(?:(?!\bbut\b)[^.!?,;:\n]){0,30}|(?:不要|不能|不可|不用|不必|不會|不会|別|别|勿|沒有|没有|未|不)[^。！？，；：.!?,;:\n]{0,6})$", re.IGNORECASE)


def prompts_dir() -> Path:
    return DATA / "prompts"


def folder(prompt_id: str) -> Path:
    if not ID_RE.match(prompt_id):
        raise ValueError("Bad prompt id")
    return prompts_dir() / prompt_id


def is_code(meta: dict) -> bool:
    return meta.get("kind") == "code"


def is_proofread(meta: dict) -> bool:
    return meta.get("kind") == "proofread"


def original(meta: dict) -> str:
    """What was given to be proofread. There's only ever one piece, since it goes back over what you copied."""
    return meta["text"][-1]["text"] if meta.get("text") else ""


def replace_text(prompt_id: str, kind: str, text: str, at: float | None = None) -> dict:
    """For proofreading: what you give it last is what gets proofread."""
    with _lock:
        meta = load(prompt_id)
        meta["text"] = [{"kind": kind, "at": at, "between_takes": False, "text": text}]
        write_json(folder(prompt_id) / "meta.json", meta)
    return meta


def create(kind: str = "prompt") -> dict:
    now = datetime.now().astimezone()
    base = now.strftime("%Y-%m-%d_%H%M%S")
    prompt_id, n = base, 1
    with _lock:
        while (prompts_dir() / prompt_id).exists():
            n += 1
            prompt_id = f"{base}-{n}"
        path = prompts_dir() / prompt_id
        path.mkdir(parents=True)
        meta = {"id": prompt_id, "kind": kind, "started_at": now.isoformat(timespec="seconds"), "duration": 0, "status": "listening", "text": [], "attempts": [], "prompt": "", "title": "", "include_text": False, "error": None}
        write_json(path / "meta.json", meta)
    return meta


def load(prompt_id: str) -> dict:
    with _lock:
        return json.loads((folder(prompt_id) / "meta.json").read_text(encoding="utf-8"))


def update(prompt_id: str, **changes) -> dict:
    with _lock:
        meta = load(prompt_id)
        meta.update(changes)
        write_json(folder(prompt_id) / "meta.json", meta)
    return meta


def add_text(prompt_id: str, kind: str, text: str, at: float | None = None, between_takes: bool = False) -> dict:
    """kind is copied or typed. at is when it was copied, in seconds into the recording, or None for before it started."""
    with _lock:
        meta = load(prompt_id)
        if text.strip() and not any(item["text"] == text for item in meta["text"]):
            meta["text"].append({"kind": kind, "at": at, "between_takes": between_takes, "text": text})
            write_json(folder(prompt_id) / "meta.json", meta)
    return meta


def set_typed(prompt_id: str, text: str) -> None:
    with _lock:
        meta = load(prompt_id)
        meta["text"] = [item for item in meta["text"] if item["kind"] != "typed"]
        if text.strip():
            meta["text"].append({"kind": "typed", "at": None, "text": text})
        write_json(folder(prompt_id) / "meta.json", meta)


def about_copy(text: str) -> dict:
    """What the bar and the window say about a copied passage, and the name Undo knows it by."""
    chars = len(text)
    return {
        "key": hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16],
        "words": " ".join(text.split())[:COPY_WORDS],
        "said": f"Added {chars:,} {'character' if chars == 1 else 'characters'}",
    }


def remove_copied(prompt_id: str, key: str) -> dict:
    """Takes out one copied passage. A key that isn't there any more, as with a double click, changes nothing, and what you typed always stays."""
    with _lock:
        meta = load(prompt_id)
        meta["text"] = [item for item in meta["text"] if item["kind"] != "copied" or about_copy(item["text"])["key"] != key]
        write_json(folder(prompt_id) / "meta.json", meta)
    return meta


def audio_path(prompt_id: str) -> Path | None:
    path = folder(prompt_id) / "audio.flac"
    return path if path.exists() else None


def list_prompts() -> list[dict]:
    """Newest first, without the long parts."""
    root = prompts_dir()
    if not root.exists():
        return []
    out = []
    for path in sorted(root.iterdir(), key=lambda p: p.name, reverse=True):
        if path.is_dir() and ID_RE.match(path.name):
            try:
                meta = load(path.name)
            except (OSError, json.JSONDecodeError):
                continue
            out.append({key: meta.get(key) for key in ("id", "started_at", "duration", "status", "title", "error", "timing", "language")} | {"kind": meta.get("kind", "prompt"), "preview": meta.get("prompt", "")[:140]})
    return out


def delete(prompt_id: str) -> None:
    """To the Recycle Bin, like a meeting."""
    send2trash(str(folder(prompt_id)))


def recover() -> dict[str, str]:
    """After a crash or a quit nothing is running any more. Only a prompt with nothing in it is removed: audio that can't be saved
    properly yet stays as it is, to try again. One that can't even be marked is left looking unfinished, so the next start comes back to it,
    and doesn't stop the others, or the app opening. Returns what to tell you about those."""
    failures = {}
    for summary in list_prompts():
        # Cancelled, and the app closed before the time to bring it back was up: it goes, as it would have.
        if summary["status"] == "cancelled":
            shutil.rmtree(folder(summary["id"]), ignore_errors=True)
        elif summary["status"] in BUSY:
            try:
                _recover_one(summary["id"])
            except Exception as exc:
                log.warning("Couldn't pick up prompt %s: %s", summary["id"], exc)
                failures[f"prompt {summary['id']}"] = f"A prompt couldn't be picked up after the app closed, but its files are still there: {exc}"
    return failures


def _recover_one(prompt_id: str) -> None:
    path = folder(prompt_id)
    error = "The app closed before this finished."
    if holds_audio(path):
        try:
            finalize_audio(path)
        except (OSError, RuntimeError) as exc:
            log.warning("Couldn't save the audio of prompt %s: %s", prompt_id, exc)
            error = f"The app closed before this finished, and its audio couldn't be saved yet: {exc}"
    elif not any(load(prompt_id).get(key) for key in ("text", "prompt", "attempts", "spoken", "spoken_edited")):
        shutil.rmtree(path, ignore_errors=True)
        return
    update(prompt_id, status="failed", error=error)


def spoken_text(meta: dict) -> str:
    if meta.get("spoken_edited") is not None:
        return meta["spoken_edited"]
    return "\n".join(line["text"] for line in meta.get("spoken", []))


def names_from_text(texts: list[str], limit: int = MOST_NAMES) -> list[str]:
    """File names, code names and acronyms in the reference text, so the speech model can hear them right."""
    counts = Counter()
    for text in texts:
        for token in re.findall(r"[A-Za-z][\w.\-/\\]*[A-Za-z0-9]", text):
            if re.search(r"[A-Z]{2}|[a-z][A-Z]|[_./\\\d]", token) and len(token) <= 40:
                counts[token] += 1
    return [token for token, _ in counts.most_common(limit)]


def _where(item: dict) -> str:
    if item["kind"] == "typed":
        return "typed into the app"
    if item["at"] is None:
        return "copied just before they started talking"
    if item.get("between_takes"):
        return f"copied at {fmt_time(item['at'])}, while paused between takes"
    return f"copied at {fmt_time(item['at'])}, while they were talking"


def _in_order(meta: dict) -> list[tuple[float, int, str, str]]:
    """What they said and what they copied, by when it happened. Typed text and anything from before they started go first."""
    items = []
    if meta.get("spoken_edited") is not None:
        items.append((0.0, 1, "spoken", meta["spoken_edited"]))
    else:
        for line in meta.get("spoken", []):
            items.append((line["start"], 1, "spoken", f"[{fmt_time(line['start'])}] {line['text']}"))
    for item in meta.get("text", []):
        items.append((-1.0 if item["at"] is None else item["at"], 0, _where(item), item["text"]))
    return sorted(items, key=lambda entry: entry[:2])


def build_request(meta: dict, terms: str, language: str, extra: str, adds: bool = True) -> str:
    language_line = {"same": "prompt_language_same", "zh-hant": "prompt_language_zh_hant"}.get(language, "prompt_language_en")
    parts = [instructions.prompt_writer(adds), instructions.get(language_line)]
    if terms.strip():
        parts.append("Names and terms that may come up:\n" + terms.strip())
    if extra.strip():
        parts.append("Their own preferences for how prompts are written:\n" + extra.strip())
    return _with_everything(parts, meta)


def build_code_request(meta: dict, terms: str, extra: str, script: str = "traditional") -> str:
    parts = [instructions.get("code_writer")]
    if script == "traditional":
        parts.append(instructions.get("code_traditional"))
    if terms.strip():
        parts.append("Names and terms that may come up:\n" + terms.strip())
    if extra.strip():
        parts.append("Their own preferences for how code is written:\n" + extra.strip())
    return _with_everything(parts, meta)


def build_proofread_request(text: str, terms: str, extra: str, said: str = "") -> str:
    parts = [instructions.get("proofread_writer")]
    if terms.strip():
        parts.append("Names and terms that may come up:\n" + terms.strip())
    if extra.strip():
        parts.append("Their own preferences for how text is edited:\n" + extra.strip())
    # A fresh marker each time, so the text can't pretend to close its own block, or open one for what was said.
    marker = secrets.token_hex(4)
    if said.strip():
        parts.append(instructions.get("proofread_said"))
        parts.append(f"<said-{marker}>\n{said.strip()}\n</said-{marker}>")
    parts.append(f"<text-{marker}>\n{text}\n</text-{marker}>")
    return "\n\n".join(parts)


def _with_everything(parts: list[str], meta: dict) -> str:
    # A fresh marker each time, so copied text can't pretend to close its own block.
    marker = secrets.token_hex(4)
    parts.append(f"Here's everything in order. What they said is between the markers spoken-{marker}. Reference text is between the markers reference-{marker}.")
    run: list[str] = []

    def end_run():
        if run:
            parts.append(f"<spoken-{marker}>\n" + "\n".join(run) + f"\n</spoken-{marker}>")
            run.clear()

    for _, _, source, text in _in_order(meta):
        if source == "spoken":
            run.append(text)
        else:
            end_run()
            parts.append(f"<reference-{marker} source=\"{source}\">\n{text}\n</reference-{marker}>")
    end_run()
    return "\n\n".join(part for part in parts if part.strip())


def sample_request(settings: dict, kind: str = "prompt") -> str:
    """What gets sent, with stand-ins for what you said and copied, for the Hints and prompts page."""
    sample = {
        "spoken": [{"start": 1.0, "end": 4.0, "text": "(what you said in your first take)"}, {"start": 21.0, "end": 24.0, "text": "(what you said in your next take)"}],
        "text": [{"kind": "copied", "at": None, "text": "(what you copied before you started)"}, {"kind": "copied", "at": 9.0, "between_takes": True, "text": "(what you copied while paused)"}],
    }
    if kind == "code":
        return build_code_request(sample, settings.get("terms", ""), settings.get("code_extra", ""), settings.get("chinese_script", "traditional"))
    if kind == "proofread":
        return build_proofread_request("(the text you copied)", settings.get("terms", ""), settings.get("proofread_extra", ""), "(what you said, if you used the shortcut for talking)")
    return build_request(sample, settings.get("terms", ""), settings.get("prompt_language", "en"), settings.get("prompt_extra", ""), settings.get("prompt_add_knowledge", True))


def _clean_list(values) -> list[str]:
    return [str(value).strip() for value in values or [] if str(value).strip()]


def _ask(request: str, settings: dict, kind: str, schema: dict, engine: str | None, model: str | None, effort: str | None, on_process) -> tuple[dict, str, str, str]:
    """kind is whose settings to use, "prompt", "code" or "proofread"."""
    engine = engine or settings[f"{kind}_engine"]
    # So a failure says what it couldn't write, not "the notes".
    what = {"code": "the code", "proofread": "the edited text"}.get(kind, "the prompt")
    if engine == "claude":
        model = settings[f"{kind}_claude_model"] if model is None else model
        effort = settings[f"{kind}_claude_effort"] if effort is None else effort
        return notes.run_claude(request, {"claude_model": model, "claude_effort": effort}, on_process, schema, instructions.get(f"{kind}_system"), what=what), "Claude Code", model, effort
    model = settings[f"{kind}_codex_model"] if model is None else model
    effort = settings[f"{kind}_codex_effort"] if effort is None else effort
    return notes.run_codex(request, {"codex_model": model, "codex_effort": effort}, on_process, schema, what=what), "Codex", model, effort


def tidy_code(text: str) -> str:
    """Only around the code, never in it. A first line's indent stays, because it may have to fit where it's pasted. There's no line ending
    at the end, so pasting into a terminal doesn't run the last line before you've looked at it."""
    fenced = FENCED.match(text)
    if fenced:
        text = fenced[1]
    return BLANK_START.sub("", text).rstrip()


def write_code(meta: dict, settings: dict, engine: str | None = None, model: str | None = None, effort: str | None = None, on_process=None) -> dict:
    """One attempt at the code. Raises notes.NotesError with a message fit to show. Nothing in the code gets converted: it runs as the model wrote it."""
    request = build_code_request(meta, settings.get("terms", ""), settings.get("code_extra", ""), settings.get("chinese_script", "traditional"))
    started = time.perf_counter()
    data, label, model, effort = _ask(request, settings, "code", CODE_SCHEMA, engine, model, effort, on_process)
    code = tidy_code(str(data.get("code", "")))
    unsure = _clean_list(data.get("unsure"))
    if not code.strip():
        raise notes.NotesError(f"{label} didn't write any code. {' '.join(unsure) or 'It could not tell what code you wanted.'}")
    return {
        "engine": label,
        "model": model,
        "effort": effort or None,
        "seconds": round(time.perf_counter() - started, 1),
        "title": str(data.get("title", "")).strip(),
        "language": str(data.get("language", "")).strip(),
        "prompt": code,
        "added": [],
        "suggestions": [],
        "unsure": unsure,
    }


def fit_like(source: str, edited: str) -> str:
    """So it drops back where it came from: the same space around it and the same line endings as what you copied, which the AI doesn't get to see."""
    edited = edited.replace("\r\n", "\n").strip()
    if "\r\n" in source:
        edited = edited.replace("\n", "\r\n")
    return source[: len(source) - len(source.lstrip())] + edited + source[len(source.rstrip()) :]


def _title_from(text: str) -> str:
    line = " ".join(text.split())
    return f"{line[:TITLE_CHARS].rstrip()}…" if len(line) > TITLE_CHARS else line


def edits_made(before: str, after: str) -> int | None:
    """How many places differ, for the bar. None if it's too long to be worth working out. Punctuation counts, since a comma can change
    what a sentence means, and fixing ，and 。 is much of what proofreading Chinese is."""
    old, new = EDIT_TOKEN.findall(before), EDIT_TOKEN.findall(after)
    if len(old) > MOST_TOKENS_TO_COMPARE or len(new) > MOST_TOKENS_TO_COMPARE:
        return None
    return sum(tag != "equal" for tag, *_ in SequenceMatcher(None, old, new, autojunk=False).get_opcodes())


def write_proofread(meta: dict, settings: dict, engine: str | None = None, model: str | None = None, effort: str | None = None, on_process=None) -> dict:
    """One attempt at the edit, following anything you said about how. Raises notes.NotesError with a message fit to show. Nothing gets converted:
    Chinese stays in whichever characters you wrote it in."""
    source = original(meta)
    if not source.strip():
        raise notes.NotesError("Nothing was copied to proofread.")
    if len(source) > TEXT_LIMIT:
        raise notes.NotesError(f"Too long: {len(source):,} characters, and the limit is {TEXT_LIMIT:,}. Copy a smaller part.")
    request = build_proofread_request(source.strip().replace("\r\n", "\n"), settings.get("terms", ""), settings.get("proofread_extra", ""), spoken_text(meta))
    started = time.perf_counter()
    data, label, model, effort = _ask(request, settings, "proofread", PROOFREAD_SCHEMA, engine, model, effort, on_process)
    text = str(data.get("text", ""))
    if not text.strip():
        raise notes.NotesError(f"{label} sent back nothing. Try again.")
    return {
        "engine": label,
        "model": model,
        "effort": effort or None,
        "seconds": round(time.perf_counter() - started, 1),
        "title": _title_from(text),
        "prompt": fit_like(source, text),
        "added": [],
        "suggestions": [],
        "unsure": [],
    }


def write(meta: dict, settings: dict, engine: str | None = None, model: str | None = None, effort: str | None = None, on_process=None, adds: bool | None = None) -> dict:
    """One attempt at the prompt. adds says whether it may add what it knows, and otherwise Settings decides. Raises notes.NotesError with a message fit to show."""
    if is_code(meta):
        return write_code(meta, settings, engine, model, effort, on_process)
    if is_proofread(meta):
        return write_proofread(meta, settings, engine, model, effort, on_process)
    adds =settings.get("prompt_add_knowledge", True) if adds is None else adds
    request = build_request(meta, settings.get("terms", ""), settings.get("prompt_language", "en"), settings.get("prompt_extra", ""), adds)
    started = time.perf_counter()
    data, label, model, effort = _ask(request, settings, "prompt", SCHEMA, engine, model, effort, on_process)
    text = str(data.get("prompt", "")).strip()
    if not text:
        raise notes.NotesError(f"{label} sent back an empty prompt. Press Write again.")
    if settings.get("chinese_script", "traditional") == "traditional":
        from opencc import OpenCC

        text = OpenCC("s2tw").convert(text)
    return {
        "engine": label,
        "model": model,
        "effort": effort or None,
        "adds": adds,
        "seconds": round(time.perf_counter() - started, 1),
        "title": str(data.get("title", "")).strip(),
        "prompt": text,
        "added": _clean_list(data.get("added")),
        "suggestions": _clean_list(data.get("suggestions")),
        "unsure": _clean_list(data.get("unsure")),
    }


def _only_with_a_not(pattern: str, text: str) -> bool:
    """Whether every mention in the text comes straight after a "not", as in "please don't delete it"."""
    return all(SAYS_NOT.search(text[max(mention.start() - 40, 0) : mention.start()]) for mention in re.finditer(pattern, text, re.IGNORECASE))


def to_check(prompt: str, said: str, copied: str = "") -> list[dict]:
    """Risky words in the prompt, and whether they were said or are in what they copied. Only ever a reminder: nothing is blocked or changed because of it."""
    out = []
    for word, pattern in RISKY.items():
        if re.search(pattern, prompt, re.IGNORECASE):
            mentioned = bool(re.search(pattern, said, re.IGNORECASE))
            item = {"word": word, "said": mentioned, "copied": bool(re.search(pattern, copied, re.IGNORECASE))}
            # You said not to, and the prompt says to: the one case where having said the word is no reassurance at all.
            if mentioned and _only_with_a_not(pattern, said) and not _only_with_a_not(pattern, prompt):
                item.update(said=False, said_not=True)
            out.append(item)
    return out


def code_to_check(code: str, said: str, copied: str = "") -> list[dict]:
    """The same reminder for code: what it can do, whether you said so, and whether what you copied does it too."""
    out = []
    for word, pattern in CODE_RISKY.items():
        if re.search(pattern, code, re.IGNORECASE):
            spoken = RISKY.get(word)
            mentioned = bool(spoken and re.search(spoken, said, re.IGNORECASE))
            item = {"word": word, "said": mentioned, "copied": bool(re.search(pattern, copied, re.IGNORECASE))}
            if mentioned and _only_with_a_not(spoken, said):
                item.update(said=False, said_not=True)
            out.append(item)
    return out


def checks(meta: dict) -> list[dict]:
    # The words in text you're proofreading are your own, and nothing is going to act on them.
    if is_proofread(meta):
        return []
    check = code_to_check if is_code(meta) else to_check
    return check(meta.get("prompt", ""), spoken_text(meta), "\n".join(item["text"] for item in meta.get("text", [])))


def to_paste(meta: dict) -> str:
    text = meta.get("prompt", "")
    # Code goes alone, whatever the switch for prompts says, or it wouldn't run.
    if meta.get("include_text") and not is_code(meta):
        pasted = [item["text"] for item in meta.get("text", [])]
        if pasted:
            text = "\n\n---\n\n".join([text, f"{REFERENCE_LABEL}\n\n{pasted[0]}", *pasted[1:]])
    return text


def detail(prompt_id: str) -> dict:
    meta = load(prompt_id)
    text = [dict(item, key=about_copy(item["text"])["key"]) for item in meta.get("text", [])]
    return dict(meta, text=text, has_audio=audio_path(prompt_id) is not None, can_hear=holds_audio(folder(prompt_id)), spoken_text=spoken_text(meta), check=checks(meta))
