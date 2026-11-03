"""Writes notes from a transcript through the Codex or Claude Code command line, on the plans you already pay for.

The transcript is untrusted text that anyone on a call could have spoken, so these calls run with tools off:
the model can only answer, it can't act on anything said in the call.
"""
from __future__ import annotations

import glob
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import instructions
from .transcript import find_quote, fmt_time, parse_time, to_text

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 15 * 60
KILL_WAIT_SECONDS = 5  # how long to wait for a stopped program's last output
CODEX_DISABLED_FEATURES = (
    "shell_tool",
    "unified_exec",
    "apps",
    "plugins",
    "browser_use",
    "browser_use_external",
    "computer_use",
    "in_app_browser",
    "multi_agent",
    "image_generation",
    "hooks",
    "memories",
    "view_image",
    "tool_suggest",
    "skill_search",
    "goals",
)

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "summary", "decisions", "action_items", "open_questions", "key_points"],
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "time", "quote"],
                "properties": {"text": {"type": "string"}, "time": {"type": "string"}, "quote": {"type": "string"}},
            },
        },
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["owner", "task", "due", "time", "quote"],
                "properties": {
                    "owner": {"type": "string"},
                    "task": {"type": "string"},
                    "due": {"type": "string"},
                    "time": {"type": "string"},
                    "quote": {"type": "string"},
                },
            },
        },
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "key_points": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["topic", "points"],
                "properties": {
                    "topic": {"type": "string"},
                    "points": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}

def find_codex() -> str | None:
    found = shutil.which("codex.cmd") or shutil.which("codex.exe")
    if found:
        return found
    fallback = Path(os.environ.get("APPDATA", "")) / "npm" / "codex.cmd"
    return str(fallback) if fallback.exists() else None


def find_claude() -> str | None:
    found = shutil.which("claude.exe") or shutil.which("claude.cmd")
    if found:
        return found
    # Claude Code's own installer puts it here, and the folder isn't always on the PATH: it wasn't on the owner's PC.
    installed = Path.home() / ".local" / "bin" / "claude.exe"
    if installed.exists():
        return str(installed)
    # The Claude desktop app keeps its own copy of the command-line tool, in a folder per version.
    pattern = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Claude-Data", "*", "claude-code", "*", "*", "claude.exe")
    matches = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    return matches[0] if matches else None


def build_prompt(lines: list[dict], terms: str = "", extra: str = "", title: str = "", language: str = "same", script: str = "traditional", mode: str = "meeting") -> str:
    language_line = {"en": "notes_language_en", "zh": "notes_language_zh", "zh-hant": "notes_language_zh_hant"}.get(language, "notes_language_same")
    parts = [instructions.get("notes_solo" if mode == "solo" else "notes_meeting"), instructions.get(language_line)]
    if language == "same" and script == "traditional":
        parts.append(instructions.get("notes_traditional"))
    if any(line.get("who") for line in lines):
        parts.append(instructions.get("notes_speakers"))
    if terms.strip():
        parts.append("Names and terms that may come up:\n" + terms.strip())
    if extra.strip():
        parts.append("The recorder's own preferences for these notes:\n" + extra.strip())
    if title.strip():
        parts.append("The recorder named this meeting: " + title.strip())
    parts.append("<transcript>\n" + to_text(lines) + "\n</transcript>")
    return "\n\n".join(part for part in parts if part.strip())


def sample_prompt(settings: dict, mode: str = "meeting") -> str:
    """What gets sent, with stand-ins for the transcript, for the Hints and prompts page."""
    lines = [{"start": 1.0, "end": 4.0, "speaker": "You", "text": "(what was said)"}]
    if mode != "solo":
        lines.append({"start": 5.0, "end": 8.0, "speaker": "Them", "text": "(what was said)"})
    return build_prompt(lines, settings.get("terms", ""), settings.get("extra_instructions", ""), language=settings.get("notes_language", "same"), script=settings.get("chinese_script", "traditional"), mode=mode)


class NotesError(Exception):
    pass


def _error_lines(output: str) -> str:
    """Only the tool's own error lines. Codex repeats the prompt in its output, and that holds the transcript:
    it must stay out of the log, and words spoken on a call mustn't be mistaken for an error."""
    lines = [line for line in output.splitlines() if re.match(r"^\s*(error|fatal)\b", line, re.IGNORECASE)]
    return "\n".join(lines)[-800:]


def _friendly(engine: str, detail: str, what: str = "the notes") -> str:
    """what is what was being written: the notes, a prompt, the code or the edited text."""
    low = detail.lower()
    if "model_not_found" in low or "model is not supported" in low or "unknown model" in low:
        return f"That {engine} model isn't available on your plan. Choose another one in Settings."
    if "login" in low or "not logged in" in low or "unauthorized" in low or "401" in low or "authenticat" in low:
        return f"{engine} isn't signed in. Sign in, then press Try again."
    # Busy for everyone for a while ("Selected model is at capacity"), which isn't your plan's limit, and another model is often free.
    if "at capacity" in low or "overloaded" in low:
        return f"That {engine} model is busy right now. Try again in a minute, or choose another model in Settings."
    if "rate limit" in low or "usage limit" in low or "quota" in low or "429" in low or "limit reached" in low:
        return f"Your {engine} plan's limit has been reached. Try again later, or switch engines in Settings."
    if "getaddrinfo" in low or "network" in low or "connection" in low or "timed out" in low or "stream disconnected" in low:
        return f"{engine} couldn't reach the internet. Check your connection, then press Try again."
    return f"{engine} couldn't write {what}. Try again, or switch engines in Settings."


def kill_tree(process: subprocess.Popen) -> None:
    """Codex runs through a .cmd wrapper, so killing only the top process would leave it running. The wrapper has to still be there for this,
    because Windows finds the rest through it."""
    try:
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(process.pid)],
            capture_output=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        process.kill()


def _run(command: list[str], prompt: str, engine: str, on_process, cwd: str | None = None, env: dict | None = None, what: str = "the notes"):
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except OSError as exc:
        raise NotesError(f"{engine} couldn't start: {exc}") from exc
    try:
        # A cancel can arrive while this was starting, when there was nothing yet to stop. Then nothing gets handed over.
        if on_process and on_process(process) is False:
            raise NotesError("Stopped.")
        stdout, stderr = process.communicate(prompt, timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        kill_tree(process)
        try:
            process.communicate(timeout=KILL_WAIT_SECONDS)
        except subprocess.TimeoutExpired:
            log.warning("%s didn't stop when it was told to", engine)
        raise NotesError(f"{engine} took longer than 15 minutes, so this was stopped.") from exc
    finally:
        if on_process:
            on_process(None)
    if process.returncode != 0:
        detail = _error_lines(f"{stderr or ''}\n{stdout or ''}")
        log.warning("%s failed (exit %s): %s", engine, process.returncode, detail or "no error line")
        raise NotesError(_friendly(engine, detail, what))
    return stdout


def run_codex(prompt: str, settings: dict, on_process=None, schema: dict = SCHEMA, what: str = "the notes") -> dict:
    codex = find_codex()
    if not codex:
        raise NotesError("Codex isn't installed, or isn't on your PATH. Choose another engine in Settings.")
    with tempfile.TemporaryDirectory(prefix="brushtalk-", ignore_cleanup_errors=True) as tmp:
        schema_file = Path(tmp) / "schema.json"
        schema_file.write_text(json.dumps(schema), encoding="utf-8")
        output = Path(tmp) / "reply.json"
        work = Path(tmp) / "work"
        work.mkdir()
        command = [
            codex,
            "exec",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
            "--ephemeral",
            "--color",
            "never",
            "-s",
            "read-only",
            "-C",
            str(work),
            "-c",
            'web_search="disabled"',
            "-c",
            f"model_reasoning_effort={settings.get('codex_effort') or 'medium'}",
            "--output-schema",
            str(schema_file),
            "-o",
            str(output),
        ]
        for feature in CODEX_DISABLED_FEATURES:
            command += ["--disable", feature]
        model = (settings.get("codex_model") or "").strip()
        if model:
            command += ["-m", model]
        command.append("-")
        _run(command, prompt, "Codex", on_process, what=what)
        if not output.exists():
            raise NotesError(f"Codex finished without writing {what}. Try again.")
        return _parse(output.read_text(encoding="utf-8"), "Codex", schema)


def run_claude(prompt: str, settings: dict, on_process=None, schema: dict = SCHEMA, system: str | None = None, what: str = "the notes") -> dict:
    claude = find_claude()
    if not claude:
        raise NotesError("Claude Code wasn't found. Choose another engine in Settings.")
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    command = [
        claude,
        "-p",
        "--tools",
        "",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(schema),
        "--system-prompt",
        instructions.get("notes_system") if system is None else system,
    ]
    model = (settings.get("claude_model") or "").strip()
    if model:
        command += ["--model", model]
    effort = (settings.get("claude_effort") or "").strip()
    if effort:
        command += ["--effort", effort]
    with tempfile.TemporaryDirectory(prefix="brushtalk-", ignore_cleanup_errors=True) as tmp:
        stdout = _run(command, prompt, "Claude Code", on_process, cwd=tmp, env=env, what=what)
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise NotesError("Claude Code sent back something that couldn't be read. Press Try again.") from exc
    if envelope.get("is_error"):
        detail = str(envelope.get("result", ""))[:500]
        log.warning("Claude Code reported an error: %s", detail)
        raise NotesError(_friendly("Claude Code", detail, what))
    structured = envelope.get("structured_output")
    if isinstance(structured, dict):
        return structured
    return _parse(str(envelope.get("result", "")), "Claude Code", schema)


def _parse(text: str, engine: str, schema: dict = SCHEMA) -> dict:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise NotesError(f"{engine} sent back something that couldn't be read. Press Try again.")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise NotesError(f"{engine} sent back something that couldn't be read. Press Try again.") from exc
    if not isinstance(data, dict) or not all(key in data for key in schema["required"]):
        raise NotesError(f"{engine} sent back something that couldn't be read. Press Try again.")
    return data


def _evidence(item: dict, lines: list[dict]) -> tuple[str, bool]:
    """A timestamp chip that points at where the quote really is, and whether the quote was found at all."""
    near = parse_time(str(item.get("time", "")))
    found = find_quote(str(item.get("quote", "")), lines, near)
    if found is not None:
        return f"[{fmt_time(found)}]", True
    return (f"[{fmt_time(near)}]" if near is not None else ""), False


def render(notes: dict, lines: list[dict]) -> tuple[str, int]:
    """Markdown for the notes, plus how many items couldn't be traced back to the transcript."""
    unverified = 0
    out = ["## Summary", "", str(notes.get("summary", "")).strip(), ""]

    decisions = notes.get("decisions") or []
    if decisions:
        out += ["## Decisions", ""]
        for item in decisions:
            chip, ok = _evidence(item, lines)
            unverified += not ok
            flag = "" if ok else " [unverified]"
            out.append(f"- {str(item.get('text', '')).strip()} {chip}{flag}".rstrip())
        out.append("")

    actions = notes.get("action_items") or []
    if actions:
        out += ["## Action items", ""]
        for item in actions:
            chip, ok = _evidence(item, lines)
            unverified += not ok
            flag = "" if ok else " [unverified]"
            owner = str(item.get("owner", "")).strip() or "Unassigned"
            due = str(item.get("due", "")).strip()
            due_text = f" (due {due})" if due and due.lower() not in ("not stated", "none", "unspecified") else ""
            task = str(item.get("task", "")).strip().rstrip(".")
            out.append(f"- [ ] **{owner}:** {task}{due_text} {chip}{flag}".rstrip())
        out.append("")

    questions = notes.get("open_questions") or []
    if questions:
        out += ["## Open questions", ""]
        out += [f"- {str(q).strip()}" for q in questions]
        out.append("")

    points = notes.get("key_points") or []
    if points:
        out += ["## Key points", ""]
        for group in points:
            out += [f"### {str(group.get('topic', '')).strip()}", ""]
            out += [f"- {str(p).strip()}" for p in group.get("points") or []]
            out.append("")

    return "\n".join(out).strip() + "\n", unverified


def generate(lines: list[dict], settings: dict, title: str = "", on_process=None, mode: str = "meeting") -> dict:
    """Returns {markdown, title, unverified, engine}. Raises NotesError with a message fit to show."""
    engine = settings.get("notes_engine", "codex")
    prompt = build_prompt(lines, settings.get("terms", ""), settings.get("extra_instructions", ""), title, settings.get("notes_language", "same"), settings.get("chinese_script", "traditional"), mode)
    if engine == "claude":
        data, label = run_claude(prompt, settings, on_process), "Claude Code"
        model, effort = settings.get("claude_model"), settings.get("claude_effort")
    else:
        data, label = run_codex(prompt, settings, on_process), "Codex"
        model, effort = settings.get("codex_model"), settings.get("codex_effort") or "medium"
    markdown, unverified = render(data, lines)
    return {
        "markdown": markdown,
        "title": str(data.get("title", "")).strip(),
        "unverified": unverified,
        "engine": label,
        "model": model,
        "effort": effort or None,
        "raw": data,
    }
