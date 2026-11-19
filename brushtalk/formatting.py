"""Format's tables and lists, made to paste well. The AI writes them in Markdown. Email, Teams and Word paste the formatted copy made here as a
real table or list. Slack can't show a table in a message, so it gets the columns lined up with spaces in a code box, and everything else gets
them lined up as plain text.

Only what Format asks for is understood: tables, bulleted and numbered lists, headings, paragraphs, bold, italics and code. Anything else
comes through as the words it is. Every word is escaped on its way into the formatted copy, so nothing in the text can become markup.
"""
from __future__ import annotations

import html
import re
import unicodedata

SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
BULLET = re.compile(r"^\s*[-*•]\s+(.*)$")
NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s*```")
CELL_SPLIT = re.compile(r"(?<!\\)\|")
CODE_SPAN = re.compile(r"`([^`\n]+)`")
BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*|__(?=\S)(.+?)(?<=\S)__")
ITALIC = re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])|(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])")
NUMBER = re.compile(r"^[-+−(]?[$€£¥]?\d[\d,]*(?:\.\d+)?%?\)?$")
# Inline styles, because email strips style sheets. A font of its own, or Outlook pastes an unstyled table in Times New Roman.
FONT = "font-family:Aptos,Calibri,Arial,Helvetica,sans-serif;font-size:11pt"
TABLE = "border-collapse:collapse"
CELL = "border:1px solid #bfbfbf;padding:4px 10px;text-align:left;vertical-align:top"
HEAD = CELL + ";background:#f2f2f2;font-weight:bold"
NUMBER_CELL = CELL.replace("text-align:left", "text-align:right")
NUMBER_HEAD = HEAD.replace("text-align:left", "text-align:right")


def _cells(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    return [cell.strip().replace("\\|", "|") for cell in CELL_SPLIT.split(line)]


def _table_starts(lines: list[str], at: int) -> bool:
    return "|" in lines[at] and at + 1 < len(lines) and bool(SEPARATOR.match(lines[at + 1]))


def _starts_block(lines: list[str], at: int) -> bool:
    line = lines[at]
    return bool(FENCE.match(line) or HEADING.match(line) or BULLET.match(line) or NUMBERED.match(line)) or _table_starts(lines, at)


def blocks(markdown: str) -> list[tuple[str, object]]:
    """The text as ("table", rows), ("bullets", items), ("numbers", items), ("heading", text), ("code", text) and ("text", lines), in order."""
    lines = markdown.replace("\r\n", "\n").split("\n")
    out: list[tuple[str, object]] = []
    at = 0
    while at < len(lines):
        line = lines[at]
        if not line.strip():
            at += 1
        elif FENCE.match(line):
            end = at + 1
            while end < len(lines) and not FENCE.match(lines[end]):
                end += 1
            out.append(("code", "\n".join(lines[at + 1 : end])))
            at = end + 1
        elif _table_starts(lines, at):
            rows = [_cells(line)]
            at += 2
            while at < len(lines) and "|" in lines[at] and lines[at].strip():
                rows.append(_cells(lines[at]))
                at += 1
            out.append(("table", rows))
        elif HEADING.match(line):
            out.append(("heading", HEADING.match(line)[1]))
            at += 1
        elif BULLET.match(line) or NUMBERED.match(line):
            pattern = BULLET if BULLET.match(line) else NUMBERED
            items: list[str] = []
            while at < len(lines) and lines[at].strip():
                item = pattern.match(lines[at])
                if item:
                    items.append(item[1].strip())
                elif lines[at][:1] in (" ", "\t") and not _starts_block(lines, at):
                    # An item that wraps onto the next line.
                    items[-1] += " " + lines[at].strip()
                else:
                    break
                at += 1
            out.append(("numbers" if pattern is NUMBERED else "bullets", items))
        else:
            paragraph = [line.strip()]
            at += 1
            while at < len(lines) and lines[at].strip() and not _starts_block(lines, at):
                paragraph.append(lines[at].strip())
                at += 1
            out.append(("text", paragraph))
    return out


def _inline_html(text: str) -> str:
    pieces = []
    for index, part in enumerate(CODE_SPAN.split(text)):
        if index % 2:
            pieces.append(f"<code>{html.escape(part, quote=False)}</code>")
            continue
        part = html.escape(part, quote=False)
        part = BOLD.sub(lambda match: f"<b>{match[1] or match[2]}</b>", part)
        part = ITALIC.sub(lambda match: f"<i>{match[1] or match[2]}</i>", part)
        pieces.append(part)
    return "".join(pieces)


def _inline_plain(text: str, slack: bool) -> str:
    """Slack's own bold is one star, and plain text has none, so the stars go."""
    pieces = []
    for index, part in enumerate(CODE_SPAN.split(text)):
        if index % 2:
            pieces.append(f"`{part}`" if slack else part)
            continue
        part = BOLD.sub(lambda match: f"*{match[1] or match[2]}*" if slack else (match[1] or match[2]), part)
        if not slack:
            part = ITALIC.sub(lambda match: match[1] or match[2], part)
        pieces.append(part)
    return "".join(pieces)


def _padded(row: list[str], count: int) -> list[str]:
    return row[:count] + [""] * (count - len(row))


def _numeric(rows: list[list[str]], column: int) -> bool:
    """A column of numbers lines up on the right, with its heading."""
    values = [row[column] for row in rows[1:] if row[column]]
    return bool(values) and all(NUMBER.match(value.replace(" ", "")) for value in values)


def width(text: str) -> int:
    """How many columns of a fixed-width font it takes: Chinese characters take two."""
    return sum(0 if unicodedata.combining(ch) else 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def lined_up(rows: list[list[str]]) -> str:
    count = max(len(row) for row in rows)
    rows = [_padded([_inline_plain(cell, False) for cell in row], count) for row in rows]
    widths = [max(width(row[column]) for row in rows) for column in range(count)]
    right = [_numeric(rows, column) for column in range(count)]

    def cell(text: str, column: int) -> str:
        gap = " " * (widths[column] - width(text))
        return gap + text if right[column] else text + gap

    return "\n".join("  ".join(cell(text, column) for column, text in enumerate(row)).rstrip() for row in rows)


def to_html(markdown: str) -> str:
    """The formatted copy: a piece of a page, for the clipboard's HTML."""
    parts = []
    for kind, value in blocks(markdown):
        if kind == "table":
            count = max(len(row) for row in value)
            right = [_numeric([_padded(row, count) for row in value], column) for column in range(count)]

            def row_html(row: list[str], tag: str, head: bool) -> str:
                styles = [(NUMBER_HEAD if head else NUMBER_CELL) if right[column] else (HEAD if head else CELL) for column in range(count)]
                return "<tr>" + "".join(f'<{tag} style="{style}">{_inline_html(cell)}</{tag}>' for cell, style in zip(_padded(row, count), styles)) + "</tr>"

            parts.append(f'<table style="{TABLE}">' + row_html(value[0], "th", True) + "".join(row_html(row, "td", False) for row in value[1:]) + "</table>")
        elif kind in ("bullets", "numbers"):
            tag = "ol" if kind == "numbers" else "ul"
            parts.append(f"<{tag}>" + "".join(f"<li>{_inline_html(item)}</li>" for item in value) + f"</{tag}>")
        elif kind == "heading":
            parts.append(f"<p><b>{_inline_html(value)}</b></p>")
        elif kind == "code":
            parts.append(f"<pre>{html.escape(value, quote=False)}</pre>")
        else:
            parts.append("<p>" + "<br>".join(_inline_html(line) for line in value) + "</p>")
    return f'<div style="{FONT}">' + "".join(parts) + "</div>"


def to_plain(markdown: str, slack: bool = False) -> str:
    """The plain copy: tables lined up, in a code box for Slack, and lists with bullets and numbers."""
    parts = []
    for kind, value in blocks(markdown):
        if kind == "table":
            parts.append(f"```\n{lined_up(value)}\n```" if slack else lined_up(value))
        elif kind == "bullets":
            parts.append("\n".join(f"• {_inline_plain(item, slack)}" for item in value))
        elif kind == "numbers":
            parts.append("\n".join(f"{number}. {_inline_plain(item, slack)}" for number, item in enumerate(value, 1)))
        elif kind == "heading":
            parts.append(f"*{_inline_plain(value, slack)}*" if slack else _inline_plain(value, slack))
        elif kind == "code":
            parts.append(f"```\n{value}\n```" if slack else value)
        else:
            parts.append("\n".join(_inline_plain(line, slack) for line in value))
    return "\n\n".join(parts)
