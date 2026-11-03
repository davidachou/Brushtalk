"""Turns the two transcribed tracks into one readable conversation, and checks quotes against it."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

MAX_JOIN_GAP = 2.0
MAX_LINE_SECONDS = 30.0
UTTERANCE_GAP = 1.0
TOKEN = re.compile(r"[㐀-鿿豈-﫿]|[^\W_㐀-鿿豈-﫿]+")
WIDE_END = re.compile(r"[　-〿㐀-鿿豈-﫿＀-￯]$")
WIDE_START = re.compile(r"^[　-〿㐀-鿿豈-﫿＀-￯]")


CHINESE = re.compile("[㐀-鿿豈-﫿]")
MIN_ECHO_WORDS = 3  # a Chinese character counts as half a word
# Words that change what a sentence says, so no text check waves through a difference in one of them. "t" is what's left of "can't" and "don't".
NEGATIONS = set("not no never none nobody nothing neither nor without cannot t 不 沒 没 別 别 未 無 无 非 勿 莫 否".split())
NUMBER_WORDS = set(
    "zero one two three four five six seven eight nine ten eleven twelve twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million billion half "
    "零 一 二 兩 两 三 四 五 六 七 八 九 十 百 千 萬 万 億 亿 半".split()
)
# The only words a model can leave out or put in when it tidies a quote. Nothing that says who, how much, when or whether, so not "you" for "we", or "is" for "was".
TIDY_WORDS = set("a an the to of and that so um uh er ah like just really actually basically well okay ok then 呃 嗯 啊 吧 呢 啦 哦 喔 的 了 地 得 著 着".split())


def fmt_time(seconds: float) -> str:
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def parse_time(text: str) -> float | None:
    parts = text.strip().split(":")
    try:
        numbers = [int(p) for p in parts]
    except ValueError:
        return None
    if len(numbers) == 2:
        return numbers[0] * 60 + numbers[1]
    if len(numbers) == 3:
        return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
    return None


def normalize(text: str) -> str:
    """Lowercase words without punctuation. Chinese has no spaces, so each character counts as a word."""
    return " ".join(TOKEN.findall(text.lower()))


def join_text(first: str, second: str) -> str:
    """Chinese runs together without a space. Everything else gets one."""
    if WIDE_END.search(first) and WIDE_START.search(second):
        return first + second
    return f"{first} {second}"


def split_by_pauses(words: list[tuple[float, float, str]]) -> list[dict]:
    """Break one Whisper segment wherever the speaker really paused.

    Voice detection cuts out the silence before Whisper sees the audio, so one segment can span two separate
    remarks with the other person talking in between. Word timings show where the gap was.
    """
    lines: list[dict] = []
    current: list[tuple[float, float, str]] = []
    for word in words:
        if current and word[0] - current[-1][1] >= UTTERANCE_GAP:
            lines.append(_words_to_line(current))
            current = []
        current.append(word)
    if current:
        lines.append(_words_to_line(current))
    return [line for line in lines if line["text"]]


def _words_to_line(words: list[tuple[float, float, str]]) -> dict:
    return {
        "start": round(float(words[0][0]), 2),
        "end": round(float(words[-1][1]), 2),
        "text": "".join(word[2] for word in words).strip(),
        "words": words,
    }


def _turn_at(start: float, end: float, turns: list[dict]) -> str | None:
    """Who was talking for most of this stretch of time."""
    best, best_overlap = None, 0.0
    for turn in turns:
        overlap = min(end, turn["end"]) - max(start, turn["start"])
        if overlap > best_overlap:
            best, best_overlap = turn["who"], overlap
    return best


def assign_speakers(lines: list[dict], turns: list[dict]) -> list[dict]:
    """Labels lines from a who-spoke-when list. With word timings, a line that spans two people gets split between them."""
    out = []
    for line in lines:
        words = line.get("words")
        if not words:
            out.append(dict(line, who=_turn_at(line["start"], line["end"], turns)))
            continue
        current: list[tuple[float, float, str]] = []
        # A word with no length has no turn of its own, so it goes with its neighbours rather than with nobody.
        who = _turn_at(line["start"], line["end"], turns)
        for word in words:
            word_who = _turn_at(word[0], word[1], turns) or who
            if current and word_who != who:
                out.append(dict(_words_to_line(current), who=who))
                current = []
            who = word_who
            current.append(word)
        out.append(dict(_words_to_line(current), who=who))
    return out


def number_speakers(lines: list[dict]) -> list[dict]:
    """Speaker 1, Speaker 2, in order of first appearance. With only one person on that side, the plain label says it all."""
    order = {}
    for line in lines:
        if line.get("who") and line["who"] not in order:
            order[line["who"]] = f"Speaker {len(order) + 1}"
    for line in lines:
        if len(order) < 2:
            line.pop("who", None)
        elif line.get("who"):
            line["who"] = order[line["who"]]
    return lines


def with_names(lines: list[dict], names: dict | None) -> list[dict]:
    """Applies the names typed in for Speaker 1, Speaker 2 and so on."""
    if not names:
        return lines
    return [dict(line, who=names.get(line["who"], line["who"])) if line.get("who") else line for line in lines]


def _changes_meaning(word: str) -> bool:
    return word in NEGATIONS or word in NUMBER_WORDS or any(character.isdigit() for character in word)


def _repeats(words: list[str], other: list[str]) -> bool:
    """Whether a mic line could be the other side's words coming back. A line that adds a "not" or a number to them is someone answering."""
    if sum(0.5 if CHINESE.match(word) else 1 for word in words) < MIN_ECHO_WORDS:
        return False
    match = SequenceMatcher(None, words, other, autojunk=False)
    if sum(block.size for block in match.get_matching_blocks()) / len(words) < 0.6:
        return False
    return not any(tag in ("replace", "delete") and any(_changes_meaning(word) for word in words[a:b]) for tag, a, b, _, _ in match.get_opcodes())


def drop_echo(you: list[dict], them: list[dict], from_speakers=None) -> tuple[list[dict], list[dict]]:
    """Without headphones the mic hears the other side too. Mic lines that repeat what they said are taken out, and returned separately.

    Matching words aren't enough, because people answer in each other's words. So a short line always stays, and so does one that adds a
    "not" or a number. from_speakers(start, end), where the audio is there to ask, has to agree that the sound itself came out of the speakers.
    A repeat left in is harmless, and something you really said taken out isn't.
    """
    kept, dropped = [], []
    for line in you:
        words = normalize(line["text"]).split()
        nearby = [t for t in them if t["start"] < line["end"] and t["end"] > line["start"]]
        overlap = sum(min(line["end"], t["end"]) - max(line["start"], t["start"]) for t in nearby)
        # An echo happens at the same moment. Repeating what someone just said ("6.2%, got it") comes after it.
        if (
            words
            and overlap >= 0.5 * (line["end"] - line["start"])
            and _repeats(words, normalize(" ".join(t["text"] for t in nearby)).split())
            and (from_speakers is None or from_speakers(line["start"], line["end"]))
        ):
            dropped.append(line)
        else:
            kept.append(line)
    return kept, dropped


def merge(you: list[dict], them: list[dict]) -> list[dict]:
    """Interleave by time, then join neighbouring lines from the same side so it reads like a conversation."""
    lines = [dict(line, speaker="You") for line in you] + [dict(line, speaker="Them") for line in them]
    lines.sort(key=lambda line: line["start"])
    merged: list[dict] = []
    for line in lines:
        last = merged[-1] if merged else None
        if (
            last
            and last["speaker"] == line["speaker"]
            and last.get("who") == line.get("who")
            and line["start"] - last["end"] <= MAX_JOIN_GAP
            and line["end"] - last["start"] <= MAX_LINE_SECONDS
        ):
            last["text"] = join_text(last["text"], line["text"])
            last["end"] = max(last["end"], line["end"])
        else:
            kept = {"speaker": line["speaker"], "start": line["start"], "end": line["end"], "text": line["text"]}
            if line.get("who"):
                kept["who"] = line["who"]
            merged.append(kept)
    return number_speakers(merged)


def to_text(lines: list[dict]) -> str:
    return "\n".join(f"[{fmt_time(line['start'])}] {line.get('who') or line['speaker']}: {line['text']}" for line in lines)


def _only_tidied(quote: list[str], said: list[str]) -> bool:
    """Whether a quote says what was said, apart from small words left out or put in. A changed fact has to fail this: a dropped "not" or
    "everything except", 6.8 for 6.2, Alice for Bob, March for May, down for up, "you" for "we". On real notes, models nearly always quote exactly."""
    steps = SequenceMatcher(None, quote, said, autojunk=False).get_opcodes()
    matched = [index for index, step in enumerate(steps) if step[0] == "equal"]
    if not matched:
        return False
    for index, (tag, a, b, c, d) in enumerate(steps):
        if tag == "equal":
            continue
        # Words of the line before or after the part quoted aren't being left out.
        left_out = said[c:d] if matched[0] < index < matched[-1] else []
        if any(word not in TIDY_WORDS for word in [*quote[a:b], *left_out]):
            return False
    return True


def find_quote(quote: str, lines: list[dict], near: float | None = None) -> float | None:
    """Where a quote really is in the transcript, or None if it can't be found.

    Exact match first, across line breaks too. Then a close match, because models tidy up a word or two
    when quoting, as long as that's all they did; near limits that to the part of the call the model pointed at.
    """
    target = normalize(quote)
    if not target:
        return None
    normalized = [normalize(line["text"]) for line in lines]
    # Whole words only, or "pay 5" would pass for "pay 50", and "Ann" for "Anna".
    joined, offsets = " ", []
    for index, text in enumerate(normalized):
        offsets.append((len(joined), index))
        joined += text + " "
    position = joined.find(f" {target} ")
    if position >= 0:
        index = max(i for start, i in offsets if start <= position + 1)
        return lines[index]["start"]
    best, best_start = 0.0, None
    words = target.split()
    for index, text in enumerate(normalized):
        if near is not None and abs(lines[index]["start"] - near) > 120:
            continue
        window = (text + " " + (normalized[index + 1] if index + 1 < len(normalized) else "")).split()
        match = SequenceMatcher(None, words, window, autojunk=False)
        score = sum(m.size for m in match.get_matching_blocks()) / max(len(words), 1)
        if score > best and _only_tidied(words, window):
            best, best_start = score, lines[index]["start"]
    return best_start if best >= 0.8 else None
