"""The overview page: totals for each mode, the latest of each, and everything still open, read from each recording's notes."""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta

from . import prompts, storage

TASK = re.compile(r"^\s*[-*] \[( |x|X)\] (.*)$")
BULLET = re.compile(r"^\s*[-*] (.*)$")
OWNER = re.compile(r"^\*\*(.+?):\*\*\s*(.*)$")
DUE = re.compile(r"\s*\(due (.+?)\)")
TIME = re.compile(r"\s*\[(\d{1,2}:\d{2}(?::\d{2})?)\]")
FLAG = re.compile(r"\s*\[unverified\]")
WEEKS = 8
RECENT = 6
DECISIONS = 8
_parsed: dict[str, tuple[float, dict]] = {}


def _clean(text: str) -> dict:
    """Separates the plain text from the time and the check-this flag that the notes carry inline."""
    found = TIME.search(text)
    return {
        "text": FLAG.sub("", TIME.sub("", text)).strip(),
        "time": found[1] if found else None,
        "unverified": bool(FLAG.search(text)),
    }


def parse_notes(markdown: str) -> dict:
    tasks, decisions, summary, section = [], [], [], ""
    for index, line in enumerate(markdown.splitlines()):
        if line.startswith("#"):
            section = line.lstrip("#").strip().lower()
            continue
        task = TASK.match(line)
        if task:
            item = _clean(task[2])
            owner = OWNER.match(item["text"])
            text = owner[2] if owner else item["text"]
            due = DUE.search(text)
            item.update(
                line=index,
                raw=line,
                done=task[1].lower() == "x",
                owner=owner[1] if owner else "",
                text=DUE.sub("", text).strip(),
                due=due[1] if due else "",
            )
            tasks.append(item)
        elif section == "decisions" and BULLET.match(line):
            decisions.append(_clean(BULLET.match(line)[1]))
        elif section == "summary" and line.strip():
            summary.append(line.strip())
    return {"tasks": tasks, "decisions": decisions, "summary": " ".join(summary)}


def _notes_of(meeting_id: str) -> dict:
    path = storage.folder(meeting_id) / "notes.md"
    if not path.exists():
        return {"tasks": [], "decisions": [], "summary": ""}
    stamp = path.stat().st_mtime
    cached = _parsed.get(meeting_id)
    if cached and cached[0] == stamp:
        return cached[1]
    parsed = parse_notes(path.read_text(encoding="utf-8"))
    _parsed[meeting_id] = (stamp, parsed)
    return parsed


def overview(now: datetime | None = None) -> dict:
    now = now or datetime.now().astimezone()
    this_week = (now - timedelta(days=now.weekday())).date()
    weeks = {this_week - timedelta(weeks=i): {"seconds": 0.0, "meetings": 0} for i in reversed(range(WEEKS))}
    meetings = solo = seconds = decision_count = 0
    tasks, decisions, recent, attention = [], [], [], []
    for meta in storage.list_meetings():
        meeting_id = meta["id"]
        started = datetime.fromisoformat(meta["started_at"])
        source = {"meeting_id": meeting_id, "meeting": meta["title"], "started_at": meta["started_at"]}
        duration = float(meta.get("duration") or 0)
        if meta.get("mode") == "solo":
            solo += 1
        else:
            meetings += 1
        seconds += duration
        week = weeks.get((started - timedelta(days=started.weekday())).date())
        if week:
            week["seconds"] += duration
            week["meetings"] += 1
        parsed = _notes_of(meeting_id)
        open_tasks = [task for task in parsed["tasks"] if not task["done"]]
        tasks += [{**task, **source} for task in open_tasks]
        decision_count += len(parsed["decisions"])
        decisions += [{**decision, **source} for decision in parsed["decisions"]]
        if len(recent) < RECENT:
            recent.append({**source, "duration": duration, "status": meta.get("status"), "summary": parsed["summary"], "open_tasks": len(open_tasks)})
        if meta.get("status") == "saved":
            attention.append({**source, "kind": "saved"})
        elif meta.get("status") == "failed":
            attention.append({**source, "kind": "failed", "error": meta.get("error")})
        elif meta.get("unverified"):
            attention.append({**source, "kind": "check", "count": meta["unverified"]})
    all_prompts = prompts.list_prompts()
    kinds = Counter(item["kind"] for item in all_prompts)
    return {
        "totals": {"meetings": meetings, "solo": solo, "prompts": kinds["prompt"], "code": kinds["code"], "proofread": kinds["proofread"], "seconds": seconds, "open_tasks": len(tasks), "decisions": decision_count},
        "weeks": [{"start": start.isoformat(), **values} for start, values in weeks.items()],
        "tasks": tasks,
        "decisions": decisions[:DECISIONS],
        "recent": recent,
        "prompts": all_prompts[:RECENT],
        "attention": attention,
    }


def set_task(meeting_id: str, line: int, raw: str, done: bool) -> bool:
    """Ticks one action item in a meeting's notes. False if the notes have changed since the page was drawn."""
    notes = storage.load_notes(meeting_id)
    lines = notes.split("\n") if notes is not None else []
    if not 0 <= line < len(lines) or lines[line].rstrip("\r") != raw or not TASK.match(raw):
        return False
    storage.file_existing_notes(meeting_id)
    lines[line] = re.sub(r"\[( |x|X)\]", "[x]" if done else "[ ]", lines[line], count=1)
    storage.save_notes(meeting_id, "\n".join(lines))
    return True
