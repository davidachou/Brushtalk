"""Saves and transcribes one meeting. Runs as its own process, so a speech model crash can't touch the app,
and its GPU memory is released as soon as it exits. Reports progress as JSON lines on stdout.

For a prompt, where seconds matter, it starts when you do, with --hold: it loads Whisper and waits to be told what to hear.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

from . import instructions
from .config import write_text_safely
from .transcript import TOKEN, fmt_time, split_by_pauses

CPU_THREADS = 12
MIN_FREE_VRAM_MB = 3000
HOLD_SECONDS = 30 * 60  # a prompt left open this long lets go of the graphics memory, and takes the usual time when it's finished
WHISPER_LANGUAGE = {"auto": None, "mixed": "zh"}
# Boosting a very quiet track further than this turns room noise into words Whisper makes up.
MAX_GAIN = 8.0
RATE = 16000
# Nobody talks this fast, in words or Chinese characters a second. With little left to hear, Whisper can finish a clip the way
# videos usually end ("see you next time"), squeezed into a fraction of a second. Real speech in testing topped out at about 7.
TOO_FAST = 20


def emit(**fields) -> None:
    print(json.dumps(fields), flush=True)


def add_dll_folders() -> None:
    """CTranslate2 finds its CUDA libraries through these folders."""
    site = Path(sys.executable).resolve().parent.parent / "Lib" / "site-packages"
    for folder in (site / "nvidia" / "cublas" / "bin", site / "ctranslate2"):
        if folder.exists():
            os.add_dll_directory(str(folder))
            os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")


def free_vram_mb() -> int | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return int(out.stdout.split()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def load_model(model_source: str, download_root: str, compute: str):
    from faster_whisper import WhisperModel

    if compute != "cpu":
        free = free_vram_mb()
        if compute == "gpu" or free is None or free >= MIN_FREE_VRAM_MB:
            try:
                model = WhisperModel(model_source, device="cuda", compute_type="float16", download_root=download_root)
                return model, "GPU"
            except Exception as exc:
                emit(note=f"The GPU wasn't available ({exc}), so this is running on the CPU.")
        else:
            emit(note=f"The GPU is busy, with {free} MB free, so this is running on the CPU.")
    model = WhisperModel(
        model_source, device="cpu", compute_type="int8", cpu_threads=CPU_THREADS, download_root=download_root
    )
    return model, "CPU"


def too_fast(text: str, seconds: float) -> bool:
    units = len(TOKEN.findall(text))
    return units >= 3 and units / max(seconds, 0.01) > TOO_FAST


def transcribe_track(model, audio, language, hotwords, on_progress, removed: list[dict]) -> list[dict]:
    """The track's lines. Text too fast to be speech goes in removed instead, so the owner can be told."""
    segments, _ = model.transcribe(
        audio,
        language=WHISPER_LANGUAGE.get(language, language),
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 200},
        condition_on_previous_text=False,
        beam_size=5,
        hotwords=hotwords or None,
        word_timestamps=True,
    )
    total = max(len(audio) / RATE, 1.0)
    out = []
    for segment in segments:
        if too_fast(segment.text, segment.end - segment.start):
            removed.append({"start": round(segment.start, 2), "end": round(segment.end, 2), "text": segment.text.strip()})
        else:
            out.extend(split_by_pauses([(word.start, word.end, word.word) for word in segment.words or []]))
        on_progress(min(segment.end / total, 1.0))
    return out


def run_whisper(args, tracks: dict, terms: list[str], held: tuple | None = None) -> tuple[dict, str, list[dict]]:
    """held is the model and its device, if they're already loaded."""
    emit(stage="loading")
    if held is None:
        add_dll_folders()
        held = load_model(args.model, args.download_root, args.compute)
    model, device = held
    emit(device=device)
    prompt = None if args.hint == "none" else f"{instructions.whisper_hint(args.hint, args.language)} {', '.join(terms)}".strip()
    results = {"You": [], "Them": []}
    removed = []
    active = [name for name, track in tracks.items() if track is not None]
    for position, name in enumerate(active):
        emit(stage="transcribing", track=name, fraction=position / len(active))

        def on_progress(fraction, position=position, name=name):
            emit(stage="transcribing", track=name, fraction=round((position + fraction) / len(active), 4))

        results[name] = transcribe_track(model, tracks[name], args.language, prompt, on_progress, removed)
    removed = in_chosen_script(removed, args.chinese)
    for item in removed:
        emit(note=f'Whisper wrote "{item["text"]}" at {fmt_time(item["start"])}, faster than anyone can talk, so it was left out as made up.')
    return results, device, removed


def run_program(engine: dict, tracks: dict, language: str, terms: list[str], speakers: bool, show_progress: bool = True, hint: str = "meeting") -> tuple[dict, str | None]:
    """Runs a model that lives in engines/, handing it each track as a file. Whatever it reports goes on up to the app."""
    import numpy as np
    import soundfile as sf
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    from .config import ROOT

    with tempfile.TemporaryDirectory(prefix="brushtalk-") as tmp:
        job_tracks = []
        for name, channel in tracks.items():
            if channel is None:
                continue
            path = Path(tmp) / f"{name}.wav"
            sf.write(path, np.clip(channel, -1.0, 1.0), RATE, subtype="PCM_16")
            stamps = get_speech_timestamps(channel, VadOptions(min_silence_duration_ms=500, speech_pad_ms=200))
            job_tracks.append(
                {
                    "name": name,
                    "audio": str(path),
                    "speakers": speakers and name == "Them",
                    "speech": [[round(s["start"] / RATE, 2), round(s["end"] / RATE, 2)] for s in stamps],
                }
            )
        output = Path(tmp) / "result.json"
        job = Path(tmp) / "job.json"
        # Tested on speech that mixes the two inside sentences: left to detect, Qwen3 translated some of the Chinese.
        language = "zh" if language == "mixed" else language
        job.write_text(
            json.dumps({"tracks": job_tracks, "language": language, "terms": terms, "hint": hint, "output": str(output), **instructions.for_engine(engine["id"], hint)}, ensure_ascii=False),
            encoding="utf-8",
        )
        process = subprocess.Popen(
            [str(ROOT / engine["python"]), str(ROOT / engine["script"]), "--job", str(job)],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        names = [track["name"] for track in job_tracks]
        device, error = None, None
        for raw in process.stdout:
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            error = event.get("error", error)
            device = event.get("device", device)
            if not show_progress:
                continue
            if event.get("stage") == "transcribing" and event.get("track") in names:
                position = names.index(event["track"])
                emit(stage="transcribing", track=event["track"], fraction=round((position + float(event.get("fraction", 0))) / len(names), 4))
            elif event.get("stage") == "loading" or "device" in event or "note" in event:
                emit(**event)
        if process.wait() != 0 or not output.exists():
            raise RuntimeError(error or f"{engine['label']} stopped unexpectedly.")
        return json.loads(output.read_text(encoding="utf-8")), device


def in_chosen_script(lines: list[dict], script: str) -> list[dict]:
    """Speech models mostly write Simplified, so every model's Chinese goes through the same conversion.

    Character by character, in Taiwan's forms, with no change of vocabulary: what was said stays what was said.
    """
    if script != "traditional":
        return lines
    from opencc import OpenCC

    convert = OpenCC("s2tw").convert
    return [dict(line, text=convert(line["text"])) for line in lines]


def save_version(path: Path, lines: list[dict], engine: dict, started: float, device: str | None, args, speakers: bool, removed: list[dict], echoes: list[dict] = ()) -> str:
    """Every transcript is kept, so models can be compared on the same recording."""
    from .storage import save_transcript_version

    return save_transcript_version(
        path,
        lines,
        engine=engine["id"],
        label=engine["label"],
        seconds=round(time.perf_counter() - started, 1),
        device=device,
        language=args.language,
        speakers=speakers,
        hint=args.hint,
        removed=removed,
        echoes=[{key: line[key] for key in ("start", "end", "text")} for line in echoes],
    )


def run(args, held: tuple | None = None) -> int:
    import numpy as np
    import soundfile as sf

    from . import engines
    from .echo import RoomEcho
    from .storage import finalize_audio
    from .transcript import assign_speakers, drop_echo, merge

    path = Path(args.folder)
    emit(stage="saving")
    flac = finalize_audio(path)
    audio, _ = sf.read(str(flac), dtype="float32", always_2d=True)
    duration = len(audio) / RATE
    emit(duration=round(duration, 2))

    tracks, warnings = {}, []
    for index, name in enumerate(("You", "Them")):
        if name == "Them" and args.mic_only:
            tracks[name] = None
            continue
        channel = audio[:, index]
        peak = float(np.abs(channel).max()) if len(channel) else 0.0
        if peak < 0.002:
            warnings.append(
                "Your microphone was silent for the whole call."
                if name == "You"
                else "No computer audio was captured, so the other people on the call are missing. "
                "Check Settings, then try a test recording."
            )
            tracks[name] = None
        else:
            # Quiet tracks are common, and voice detection is sensitive to level.
            tracks[name] = channel * min(0.8 / peak, MAX_GAIN) if peak < 0.5 else channel

    if not any(track is not None for track in tracks.values()):
        emit(warnings=warnings, device=None)
        if not args.compare:
            write_text_safely(path / "transcript.json", "[]")
        emit(stage="done")
        return 0

    terms = []
    if args.hint != "none" and args.terms_file and Path(args.terms_file).exists():
        terms = [t.strip() for t in Path(args.terms_file).read_text(encoding="utf-8").splitlines() if t.strip()]

    started = time.perf_counter()
    engine = engines.get(args.engine)
    if engine["id"] != "whisper":
        free = engines.free_vram_gb()
        reason = None
        if args.compute == "cpu":
            reason = "Run on is set to the CPU, which this model is too slow for"
        elif free is not None and free < engine.get("needs_gb", 0):
            reason = f"it needs about {engine['needs_gb']} GB of graphics memory and {free:.0f} GB is free"
        if reason and args.compare:
            raise RuntimeError(f"{engine['label']} can't run right now: {reason}.")
        if reason:
            emit(note=f"This used Whisper instead of {engine['label']}: {reason}.")
            engine = engines.WHISPER

    results, device, removed = {}, None, []
    if engine["id"] != "whisper":
        emit(stage="loading")
        try:
            results, device = run_program(engine, tracks, args.language, terms, args.speakers and engine.get("labels_speakers", False), hint=args.hint)
        except Exception as exc:
            if args.compare:
                raise
            emit(note=f"This used Whisper instead of {engine['label']}: {exc}")
            engine = engines.WHISPER
    if engine["id"] == "whisper":
        results, device, removed = run_whisper(args, tracks, terms, held)
    if not args.compare:
        emit(engine=engine["id"], engine_label=engine["label"])

    them = results.get("Them", [])
    if args.speakers and not engine.get("labels_speakers") and tracks["Them"] is not None:
        helper = engines.diarizer()
        if helper:
            emit(stage="transcribing", track="Them", fraction=0.99, hint=f"Telling speakers apart with {helper['label']}.")
            try:
                turns, _ = run_program(helper, {"Them": tracks["Them"]}, args.language, terms, True, show_progress=False)
                them = assign_speakers(them, turns.get("Them", []))
            except Exception as exc:
                emit(note=f"The speakers couldn't be told apart: {exc}")
        else:
            emit(note="The speaker model isn't installed, so the other side is all labelled Them.")

    you, echoes = drop_echo(results.get("You", []), them, RoomEcho(audio[:, 0], audio[:, 1]).from_speakers)
    echoes = in_chosen_script(echoes, args.chinese)
    if echoes:
        lines_text = "1 line" if len(echoes) == 1 else f"{len(echoes)} lines"
        emit(note=f"Removed {lines_text} your mic picked up from the speakers. They're listed under the transcript, in case one was really you. Headphones avoid this.")
    lines = in_chosen_script(merge(you, them), args.chinese)
    version = save_version(path, lines, engine, started, device, args, args.speakers, removed, echoes)
    if not args.compare:
        tmp = path / "transcript.json.part"
        tmp.write_text(json.dumps(lines, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path / "transcript.json")
    emit(version=version)
    emit(warnings=warnings, lines=len(lines))
    emit(stage="done")
    return 0


def next_line(seconds: float) -> str | None:
    """A line from the app, or None if the app goes away or it takes too long."""
    lines: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: lines.put(sys.stdin.readline()), daemon=True).start()
    try:
        return lines.get(timeout=seconds).strip() or None
    except queue.Empty:
        return None


def warm_up(model) -> None:
    """The first time through is the slowest, because of the voice detector and the graphics card's first run. This gets that out of the way too."""
    import numpy as np

    silence = np.zeros(RATE, dtype=np.float32)
    for vad in (True, False):
        segments, _ = model.transcribe(silence, language="en", beam_size=1, vad_filter=vad)
        list(segments)


def hold(model_source: str, download_root: str, compute: str) -> int:
    """Gets everything ready, then waits for the arguments of one job. Exits after it, like any other job, which frees the graphics memory."""
    import soundfile  # noqa: F401
    from opencc import OpenCC  # noqa: F401

    from . import engines, storage  # noqa: F401

    try:
        add_dll_folders()
        held = load_model(model_source, download_root, compute)
        warm_up(held[0])
    except Exception:
        # The app notices this has gone, and does the job the usual way.
        traceback.print_exc()
        return 1
    line = next_line(HOLD_SECONDS)
    if line is None:
        # The thread still waiting on stdin would stop Python from exiting normally.
        sys.stdout.flush()
        os._exit(0)
    return go(json.loads(line), held)


def main() -> int:
    if sys.argv[1:2] == ["--hold"]:
        return hold(*sys.argv[2:5])
    return go(sys.argv[1:])


def go(arguments: list[str], held: tuple | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--model", required=True)
    parser.add_argument("--download-root", required=True)
    parser.add_argument("--language", default="en")
    parser.add_argument("--chinese", default="traditional")
    parser.add_argument("--hint", default="meeting", choices=("meeting", "talking", "none"))
    parser.add_argument("--mic-only", action="store_true", help="there's no other side, so don't warn that it's missing")
    parser.add_argument("--compute", default="auto")
    parser.add_argument("--terms-file", default="")
    parser.add_argument("--engine", default="whisper")
    parser.add_argument("--speakers", action="store_true")
    parser.add_argument("--compare", action="store_true", help="keep this as another version, leaving the current transcript in place")
    args = parser.parse_args(arguments)
    try:
        return run(args, held)
    except Exception as exc:
        traceback.print_exc()
        emit(error=str(exc) or exc.__class__.__name__)
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
