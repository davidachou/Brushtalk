"""Records the microphone and computer audio to two time-aligned tracks.

Both tracks are 16 kHz mono PCM written straight to disk, so a crash loses at most about a second. Every
block is placed on one wall clock instead of being appended: Windows loopback delivers nothing during
silence, and without this the computer-audio track would drift ahead of the mic.

Computer audio is captured from every output device by default. A call can play on a device that isn't the
Windows default, and on this machine the default has been seen to change mid-session.

Pausing takes that time out of the recording altogether, leaving only a short gap to mark where it was. So a long
think or minutes of reading add nothing: no audio to keep, and no silence for a speech model to make things up in.
"""
from __future__ import annotations

import ctypes
import logging
import os
import queue
import re
import threading
import time
import warnings
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pyaudiowpatch as pa
import soxr

log = logging.getLogger(__name__)

RATE = 16000
BLOCK_SECONDS = 0.1
HOLD = int(0.5 * RATE)  # samples kept in memory so late blocks still land in the right place
MAX_SKEW = int(0.25 * RATE)  # a source re-syncs to the clock when it's this far off
SOUND_RMS = 0.003  # about -50 dBFS: anything quieter doesn't count as sound
RESUME_GAP = 2.5  # seconds of silence left where a pause was, just long enough that what came before and after stay separate lines
# How long after Windows says a sound has finished the mic can still hear it, because speakers play late and the mic delivers late.
# Measured on the owner's PC at up to 0.11 seconds, in research_notes/Prompt mode/Real audio testing.md, with a little to spare.
SOUND_TAIL = 0.14
MOST_UNSAVED = RATE * 60 * 30  # samples a track holds in memory while the disk is refusing them, about 115 MB
SHOW_NOTICE_FOR = 30  # seconds a new notice stays up on the floating bar
ALERT_AGAIN_AFTER = 60  # seconds before the same problem interrupts you again, so a device going on and off can't do it every second
OUTPUT_SOUND_FOR = 3  # seconds an output still counts as having sound after it last did, so it doesn't flicker between words
PROBLEM_WORDS = {"save": "This isn't being saved!", "devices": "Nothing's being recorded!"}
_portaudio = threading.Lock()


class AudioStuck(RuntimeError):
    """PortAudio is still busy with an earlier start or shutdown."""


@contextmanager
def _one_at_a_time(wait: float = 5):
    """PortAudio can't start up or shut down on two threads at once: the whole app crashes, with no message. Two Settings pages
    loading together were enough. Shutting down can hang on a device that vanished, so this waits only so long, rather than for ever.
    Then it says so rather than going ahead: PortAudio only reads the devices again after a full shutdown, so starting up during one can't work anyway."""
    if not _portaudio.acquire(timeout=wait):
        raise AudioStuck("Windows audio isn't responding. Try again, and if this keeps happening, quit and reopen the app.")
    try:
        yield
    finally:
        _portaudio.release()


def to_mono(samples: np.ndarray) -> np.ndarray:
    """Average only the channels that carry sound, so stereo in a 7.1 mix doesn't lose level."""
    if samples.shape[1] == 1:
        return samples[:, 0]
    rms = np.sqrt(np.mean(samples**2, axis=0))
    active = rms > 1e-4
    if not active.any():
        return np.zeros(len(samples), dtype=np.float32)
    return samples[:, active].mean(axis=1)


def device_key(name: str) -> str:
    """Windows renumbers devices when they're replugged, as in "Microphone (2- Antlion...)": ignore the number."""
    return re.sub(r"\(\d+-\s*", "(", name).strip().lower()


def _length(seconds: float) -> str:
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def level_from_rms(rms: float) -> float:
    db = 20 * np.log10(max(rms, 1e-5))
    return float(np.clip((db + 60) / 60, 0, 1))


class Source:
    """One open device feeding a track."""

    def __init__(self, track: "Track", name: str, rate: int, channels: int):
        self.track = track
        self.name = name
        self.rate = rate
        self.channels = channels
        self.next_pos: int | None = None
        self.resampler = soxr.ResampleStream(rate, RATE, 1, dtype="float32", quality="HQ")
        self.stream = None
        self.last_sound: float | None = None  # so a call's screen can say which outputs the call is playing on


class Track:
    """A mixing buffer on the shared timeline, flushed to one PCM file."""

    def __init__(self, name: str, path: Path | None, t0: float):
        self.name = name
        self.t0 = t0
        self.file = open(path, "ab", buffering=0) if path else None
        self.written = self.file.tell() if self.file else 0  # how much of the file is known to be good
        self.overflowed = False  # the disk refused for so long that some audio couldn't wait for it
        self.buffer = np.zeros(RATE * 8, dtype=np.float32)
        self.base = 0  # timeline position of buffer[0]
        self.lock = threading.Lock()
        self.queue: queue.SimpleQueue = queue.SimpleQueue()
        self.level = 0.0
        self.last_block: float | None = None
        self.last_sound: float | None = None
        self.sound_seconds = 0.0
        self.paused = False
        self.frozen_at: float | None = None  # while paused, the moment this track's clock stopped
        self.keep_from = 0.0  # anything from before this moment is left out

    def place(self, source: Source, block: np.ndarray, arrival: float) -> None:
        count = len(block)
        if count == 0:
            return
        start = int((arrival - self.t0) * RATE) - count
        with self.lock:
            # Follow the source's own sample count while it stays near the clock: placing each block by
            # arrival time alone would put jitter into the audio as clicks.
            if source.next_pos is None or abs(start - source.next_pos) > MAX_SKEW:
                source.next_pos = start
            pos = source.next_pos
            source.next_pos = pos + count
            offset = pos - self.base
            if offset < 0:
                block = block[-offset:]
                offset = 0
                if len(block) == 0:
                    return
            end = offset + len(block)
            if end > len(self.buffer):
                if end > MOST_UNSAVED:
                    self.overflowed = True
                    return
                grown = np.zeros(min(max(end, len(self.buffer) * 2), MOST_UNSAVED), dtype=np.float32)
                grown[: len(self.buffer)] = self.buffer
                self.buffer = grown
            self.buffer[offset:end] += block

    def flush(self, now: float, final: bool = False) -> None:
        """Write everything older than the hold window; silence is written as zeros. Audio the disk refuses stays here for the next try,
        and the timeline only moves on once it's written, so what comes after still lands in the right place."""
        if self.frozen_at is not None:
            now = self.frozen_at
        target = int((now - self.t0) * RATE) - (0 if final else HOLD)
        with self.lock:
            count = target - self.base
            if count <= 0:
                return
            take = min(count, len(self.buffer))
            data = self.buffer[:take].copy()
        if self.file:
            pcm = (np.clip(data, -1.0, 1.0) * 32767).astype("<i2")
            self._write(pcm.tobytes() + b"\0\0" * (count - take))
        with self.lock:
            self.buffer[:-take] = self.buffer[take:]
            self.buffer[-take:] = 0
            self.base += count

    def _write(self, data: bytes) -> None:
        """All of it or none of it: a full disk can take part of a write and refuse the rest."""
        try:
            remaining = memoryview(data)
            while remaining:
                remaining = remaining[self.file.write(remaining) :]
        except OSError:
            self.file.truncate(self.written)
            raise
        self.written += len(data)

    def sync(self) -> None:
        if self.file:
            os.fsync(self.file.fileno())

    def close(self) -> None:
        if self.file:
            try:
                self.sync()
            finally:
                self.file.close()
                self.file = None


def _wasapi(p: pa.PyAudio) -> dict:
    return p.get_host_api_info_by_type(pa.paWASAPI)


def list_devices() -> dict:
    """Names of the microphones and output devices, with the current defaults."""
    with _one_at_a_time():
        p = pa.PyAudio()
        try:
            api = _wasapi(p)
            mics, outputs = [], []
            for i in range(p.get_device_count()):
                dev = p.get_device_info_by_index(i)
                if dev["hostApi"] != api["index"] or dev.get("isLoopbackDevice"):
                    continue
                if dev["maxInputChannels"] > 0:
                    mics.append(dev["name"])
                if dev["maxOutputChannels"] > 0:
                    outputs.append(dev["name"])
            default_mic = default_out = None
            if api["defaultInputDevice"] >= 0:
                default_mic = p.get_device_info_by_index(api["defaultInputDevice"])["name"]
            if api["defaultOutputDevice"] >= 0:
                default_out = p.get_device_info_by_index(api["defaultOutputDevice"])["name"]
            return {"mics": mics, "outputs": outputs, "default_mic": default_mic, "default_output": default_out}
        finally:
            p.terminate()


def _windows_devices() -> tuple[str | None, frozenset, frozenset]:
    """Default mic and all devices, from Windows itself. PortAudio only rescans after a full restart."""
    import soundcard as sc

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mics = frozenset(m.name for m in sc.all_microphones())
        try:
            mic = sc.default_microphone().name
        except Exception:
            # Windows has a default whenever there's a mic, so this was a hiccup and the check doesn't count.
            # Read as "no default mic", it would reopen the streams twice: when it happened and when it cleared.
            if mics:
                raise
            mic = None
        return mic, mics, frozenset(s.name for s in sc.all_speakers())


def _named(names: frozenset, wanted: str) -> str | None:
    """The device a setting points at, if it's connected: the same one every time, even with two of a kind. "default" and "all" point at none."""
    wanted = device_key(wanted)
    return min((name for name in names if device_key(name) == wanted), default=None)


class Recorder:
    """Captures to mic.pcm and system.pcm in a meeting folder. With folder=None it only drives the meters.

    mic_only leaves computer audio out, for when only your own voice matters.
    """

    def __init__(self, folder: Path | None, mic_device: str = "default", output_device: str = "all", mic_only: bool = False):
        self.folder = folder
        self.mic_device = mic_device
        self.output_device = output_device
        self.mic_only = mic_only
        self.t0 = time.perf_counter()
        self.mic = Track("mic", folder / "mic.pcm" if folder else None, self.t0)
        self.system = Track("system", folder / "system.pcm" if folder and not mic_only else None, self.t0)
        self.pa: pa.PyAudio | None = None
        self.sources: list[Source] = []
        self.paused_at: float | None = None
        self.takes = 1  # how many stretches of talking so far, for showing progress
        self.notices: list[str] = []
        self.last_notice: tuple[str, float] | None = None
        self.urgent: list[str] = []  # the notices worth interrupting you about
        self.alerted: set[str] = set()  # said, and still true
        self.alerted_at: dict[str, float] = {}
        self.problems: dict[str, str] = {}  # what's wrong right now, by what it affects: "save" or "devices"
        self.quiet_after = 45.0  # seconds with nothing heard yet before saying so
        self.quiet_again_after = 120.0  # the same once it has heard you, because people go quiet to listen
        self.stopping = threading.Event()
        self.stopped = threading.Event()
        self.streams_lock = threading.Lock()
        self.threads: list[threading.Thread] = []
        self.known_devices: tuple | None = None

    # ------------------------------------------------------------- lifecycle

    def carry_on(self, heard: float, takes: int) -> None:
        """Before start: picks up where a stopped recording of this folder left off, as Undo does. The clock goes on from the end of
        what's on the disk, so nothing is written over it or padded before it, and what it had heard still counts as heard."""
        samples = self.mic.written // 2
        self.t0 -= samples / RATE
        for track in (self.mic, self.system):
            track.t0 = self.t0
            track.base = samples
        self.mic.sound_seconds = heard
        if heard:
            self.mic.last_sound = time.perf_counter()
        self.takes = takes

    def start(self) -> None:
        try:
            with self.streams_lock:
                self._open_all()
            if not self.sources:
                raise RuntimeError("No microphone or output device could be opened.")
        except BaseException:
            # Whatever did open is closed again, or a start that fails part way would leave the mic open and its file held.
            self._close_all()
            for track in (self.mic, self.system):
                track.close()
            raise
        for target, args in (
            (self._process_loop, (self.mic,)),
            (self._process_loop, (self.system,)),
            (self._flush_loop, ()),
            (self._device_loop, ()),
        ):
            thread = threading.Thread(target=target, args=args, daemon=True, name=f"rec-{target.__name__}")
            thread.start()
            self.threads.append(thread)

    def stop(self) -> dict:
        """Stop capture and write everything out. Both tracks end at the same moment, and one that can't be written doesn't cost the other its ending."""
        # Set before taking the lock, so the device thread can't reopen streams after they're closed here.
        self.stopping.set()
        with self.streams_lock:
            devices = self.device_names()
            self._close_all()
        self.stopped.set()
        for thread in self.threads:
            thread.join(timeout=3)
        now = self.paused_at or time.perf_counter()
        self.paused_at = None
        self.problems.clear()
        for track in (self.mic, self.system):
            try:
                try:
                    track.flush(now, final=True)
                finally:
                    track.close()
            except OSError as exc:
                self.problems["save"] = f"The end of this recording couldn't be saved: {exc}"
                log.error(self.problems["save"])
            self._mention_overflow(track)
        return {
            "duration": round(now - self.t0, 2),
            "sound_seconds": {"mic": round(self.mic.sound_seconds, 1), "system": round(self.system.sound_seconds, 1)},
            "devices": devices,
            "notices": list(self.notices),
        }

    def hold(self) -> None:
        """Keeps nothing until release(), for while the start sound plays. Unlike a pause, it isn't a break between stretches of talking."""
        self.mic.paused = self.system.paused = True

    def release(self) -> None:
        self.mic.paused = self.system.paused = False

    def keep_after(self, seconds: float) -> None:
        """Leaves out what's still to come in the next few moments, which could hold the end of a sound the app has just played."""
        self.mic.keep_from = self.system.keep_from = time.perf_counter() + seconds

    def pause(self) -> None:
        if self.paused_at is None:
            self.paused_at = time.perf_counter()
            for track in (self.mic, self.system):
                track.frozen_at = self.paused_at
                track.paused = True

    def resume(self) -> None:
        if self.paused_at is not None:
            # Moving the start forward takes the pause out of the recording's clock, apart from the short gap.
            removed = max(time.perf_counter() - self.paused_at - RESUME_GAP, 0.0)
            self.t0 += removed
            for track in (self.mic, self.system):
                track.t0 += removed
                if track.last_sound is not None:
                    track.last_sound += removed
                track.frozen_at = None
                track.paused = False
            self.paused_at = None
            self.takes += 1

    # ------------------------------------------------------------- status

    @property
    def error(self) -> str | None:
        return next(iter(self.problems.values()), None)

    def elapsed(self) -> float:
        """Where the recording has got to. Pauses don't count."""
        now = self.paused_at or time.perf_counter()
        return now - self.t0

    def _quiet_for(self, track: Track, now: float) -> float | None:
        """How long this track has gone without sound, once that's long enough to mention."""
        silent = now - (track.last_sound if track.last_sound is not None else self.t0)
        return silent if silent > (self.quiet_after if track.last_sound is None else self.quiet_again_after) else None

    def health(self) -> dict | None:
        """The one thing to tell you about this recording right now, so every window says the same. kind is error, warn or note."""
        if self.problems:
            key, text = next(iter(self.problems.items()))
            return {"kind": "error", "text": text, "short": PROBLEM_WORDS[key]}
        now = time.perf_counter()
        if self.paused_at is None:
            quiet = self._quiet_for(self.mic, now)
            if quiet is not None:
                when = f"for {_length(quiet)}" if self.mic.last_sound is not None else "yet"
                return {"kind": "warn", "text": f"No sound from your microphone {when}. Check that it's on and not muted.", "short": f"No mic sound {when}"}
            quiet = None if self.mic_only else self._quiet_for(self.system, now)
            if quiet is not None:
                when = f"for {_length(quiet)}" if self.system.last_sound is not None else "yet"
                return {"kind": "warn", "text": f"No computer audio {when}. If people are talking, check which speaker your call is using.", "short": f"No computer audio {when}"}
        if self.last_notice and now - self.last_notice[1] < SHOW_NOTICE_FOR:
            return {"kind": "note", "text": self.last_notice[0], "short": self.last_notice[0].removeprefix("Audio devices changed. ")}
        return None

    def alert(self) -> str | None:
        """What's worth interrupting you about, once each time it starts. It takes longer than a note on the bar, because someone just listening can go quiet for minutes."""
        now = time.perf_counter()
        words = [*self.problems.values(), *self.urgent]
        if self.paused_at is None:
            silent = now - (self.mic.last_sound if self.mic.last_sound is not None else self.t0)
            if self.mic.last_sound is None and silent > 45:
                words.append("No sound from your microphone yet. Check that it's on and not muted.")
            elif silent > 300:
                words.append("No sound from your microphone for 5 minutes. Check that it's on and not muted.")
            if not self.mic_only and self.system.last_sound is None and now - self.t0 > 120:
                words.append("No computer audio yet. If people are talking, check which speaker your call is using.")
        # Once something stops being true it's said again if it comes back, as a mic muted a second time in the same call would.
        self.alerted &= set(words)
        for text in words:
            if text not in self.alerted and now - self.alerted_at.get(text, -ALERT_AGAIN_AFTER) >= ALERT_AGAIN_AFTER:
                self.alerted.add(text)
                self.alerted_at[text] = now
                return text
        return None

    def device_names(self) -> dict:
        names = {"mic": [], "system": []}
        for source in self.sources:
            names[source.track.name].append(source.name)
        return names

    def status(self) -> dict:
        now = time.perf_counter()

        def silent_for(track: Track) -> float:
            return now - (track.last_sound if track.last_sound is not None else self.t0)

        return {
            "elapsed": round(self.elapsed(), 1),
            "paused": self.paused_at is not None,
            "takes": self.takes,
            "levels": {"mic": round(self.mic.level, 3), "system": round(self.system.level, 3)},
            "silent_for": {"mic": round(silent_for(self.mic), 1), "system": round(silent_for(self.system), 1)},
            "heard": {"mic": self.mic.last_sound is not None, "system": self.system.last_sound is not None},
            "devices": self.device_names(),
            # Every output whose sound is being recorded, and whether it has some now: if the other side is missing, this shows why.
            "outputs": [
                {"name": source.name, "sound": source.last_sound is not None and now - source.last_sound < OUTPUT_SOUND_FOR}
                for source in list(self.sources)
                if source.track is self.system
            ],
            "notices": self.notices[-3:],
            "error": self.error,
            "health": self.health(),
        }

    # ------------------------------------------------------------- devices

    def _resolve_mic(self, p: pa.PyAudio) -> dict | None:
        api = _wasapi(p)
        if self.mic_device != "default":
            wanted = device_key(self.mic_device)
            for i in range(p.get_device_count()):
                dev = p.get_device_info_by_index(i)
                if (
                    dev["hostApi"] == api["index"]
                    and not dev.get("isLoopbackDevice")
                    and dev["maxInputChannels"] > 0
                    and device_key(dev["name"]) == wanted
                ):
                    return dev
            self._notice(f"{self.mic_device} isn't connected, so the default microphone is being used.", urgent=True)
        if api["defaultInputDevice"] >= 0:
            return p.get_device_info_by_index(api["defaultInputDevice"])
        return None

    def _resolve_outputs(self, p: pa.PyAudio) -> list[dict]:
        loopbacks = list(p.get_loopback_device_info_generator())
        if self.output_device == "all":
            return loopbacks
        wanted = device_key(self.output_device)
        for dev in loopbacks:
            if device_key(dev["name"].replace(" [Loopback]", "")) == wanted:
                return [dev]
        self._notice(f"{self.output_device} isn't connected, so all computer audio is being captured.")
        return loopbacks

    def _open_all(self) -> None:
        with _one_at_a_time():
            self.pa = pa.PyAudio()
        self.sources = []
        mic = self._resolve_mic(self.pa)
        if mic:
            self._open(self.mic, mic)
        if not self.sources and not self.mic_only:
            self._notice("No microphone could be opened, so only computer audio is being recorded.", urgent=True)
        if self.mic_only:
            self.known_devices = None
            return
        outputs = self._resolve_outputs(self.pa)
        for dev in outputs:
            self._open(self.system, dev)
        if not any(s.track is self.system for s in self.sources):
            self._notice("Computer audio couldn't be opened, so only your microphone is being recorded.", urgent=True)
        self.known_devices = None

    def _open(self, track: Track, dev: dict) -> None:
        rate = int(dev["defaultSampleRate"])
        channels = max(1, int(dev["maxInputChannels"]))
        source = Source(track, dev["name"].replace(" [Loopback]", ""), rate, channels)

        def callback(in_data, frame_count, time_info, status):
            track.queue.put((source, in_data, time.perf_counter()))
            return (None, pa.paContinue)

        try:
            source.stream = self.pa.open(
                format=pa.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=dev["index"],
                frames_per_buffer=int(rate * BLOCK_SECONDS),
                stream_callback=callback,
            )
            self.sources.append(source)
        except Exception as exc:
            log.warning("Could not open %s: %s", dev["name"], exc)

    def _close_all(self) -> None:
        """Close with a time limit: closing a stream on a device that vanished can hang."""
        sources, self.sources = self.sources, []
        p, self.pa = self.pa, None

        def closer():
            for source in sources:
                try:
                    source.stream.close()
                except Exception as exc:
                    log.warning("Closing %s failed: %s", source.name, exc)
            if p:
                # This has its own thread to wait on, and has to happen, or PortAudio never reads the devices again.
                try:
                    with _one_at_a_time(wait=60):
                        p.terminate()
                except Exception as exc:
                    log.warning("Shutting audio down failed: %s", exc)

        thread = threading.Thread(target=closer, daemon=True, name="rec-close")
        thread.start()
        thread.join(timeout=4)
        if thread.is_alive():
            log.warning("Closing audio streams timed out")

    def _depends_on(self, devices: tuple) -> tuple:
        """The devices this recording uses, chosen as _resolve_mic and _resolve_outputs would choose them.

        Anything else can come and go without interrupting it.
        """
        default_mic, mics, speakers = devices
        mic = _named(mics, self.mic_device) or default_mic
        outputs = None if self.mic_only else _named(speakers, self.output_device) or speakers
        return mic, outputs

    def _notice(self, text: str, urgent: bool = False) -> None:
        if text not in self.notices:
            self.notices.append(text)
            self.last_notice = (text, time.perf_counter())
            if urgent:
                self.urgent.append(text)
            log.info(text)

    def _mention_overflow(self, track: Track) -> None:
        if track.overflowed:
            self._notice("Part of this recording is missing, because the disk refused it for too long.", urgent=True)

    # ------------------------------------------------------------- threads

    def _process_loop(self, track: Track) -> None:
        while not (self.stopped.is_set() and track.queue.empty()):
            try:
                source, data, arrival = track.queue.get(timeout=0.1)
            except queue.Empty:
                continue
            # One bad block mustn't end this track for the rest of the call, with nothing to show for it.
            try:
                self._process_block(track, source, data, arrival)
            except Exception as exc:
                text = f"Part of this recording may be missing, because of an error: {exc}"
                if text not in self.notices:
                    log.exception("Processing %s failed", track.name)
                self._notice(text, urgent=True)

    def _process_block(self, track: Track, source: Source, data: bytes, arrival: float) -> None:
        samples = np.frombuffer(data, dtype=np.int16).reshape(-1, source.channels).astype(np.float32) / 32768.0
        mono = to_mono(samples)
        resampled = source.resampler.resample_chunk(mono)
        rms = float(np.sqrt(np.mean(mono**2))) if len(mono) else 0.0
        # Kept up during a pause too, or the moment after resuming would look like a stalled mic.
        track.last_block = arrival
        if track.paused or arrival <= track.keep_from:
            source.next_pos = None
            track.level = 0.0
            return
        track.level = level_from_rms(rms)
        if rms > SOUND_RMS:
            track.last_sound = source.last_sound = arrival
            track.sound_seconds += len(mono) / source.rate
        begins = arrival - len(resampled) / RATE
        if begins < track.keep_from:
            resampled = resampled[int((track.keep_from - begins) * RATE) :]
        track.place(source, resampled, arrival)

    def _flush_loop(self) -> None:
        last_sync = time.perf_counter()
        while not self.stopped.wait(0.2):
            now = time.perf_counter()
            refused = None
            for track in (self.mic, self.system):
                try:
                    track.flush(now)
                except OSError as exc:
                    refused = exc
                self._mention_overflow(track)
                if track.last_block is None or now - track.last_block > 0.35:
                    track.level = 0.0
            if refused:
                if "save" not in self.problems:
                    log.error("The recording can't be saved: %s", refused)
                self.problems["save"] = f"This recording isn't being saved, because the disk refused it: {refused}. Free up some space if it's full. What's been said is waiting in memory until then."
            elif self.problems.pop("save", None):
                self._notice("Saving this recording stopped for a while, then caught up.")
            if now - last_sync > 5:
                last_sync = now
                for track in (self.mic, self.system):
                    try:
                        track.sync()
                    except OSError:
                        pass

    def _device_loop(self) -> None:
        """Reopen everything when a device this recording uses changes, or the mic goes quiet at the driver."""
        # This comes first: soundcard starts COM itself on its first import, and refuses a thread that already has.
        try:
            import soundcard  # noqa: F401
        except Exception as exc:
            log.warning("Device checks are off for this recording: %s", exc)
            return
        ctypes.windll.ole32.CoInitializeEx(None, 0)
        last_reopen = time.perf_counter()
        while not self.stopped.wait(2.0):
            try:
                current = self._depends_on(_windows_devices())
            except Exception as exc:
                log.warning("Device check failed: %s", exc)
                continue
            if self.known_devices is None:
                self.known_devices = current
                continue
            now = time.perf_counter()
            changed = current != self.known_devices
            mic_stalled = (
                any(s.track is self.mic for s in self.sources)
                and self.mic.last_block is not None
                and now - self.mic.last_block > 3
                and not self.mic.paused
            )
            if not (changed or mic_stalled or "devices" in self.problems) or now - last_reopen < 3:
                continue
            last_reopen = now
            log.info("Reopening audio streams (changed=%s, stalled=%s)", changed, mic_stalled)
            mics_before = self.device_names()["mic"]
            with self.streams_lock:
                if self.stopping.is_set():
                    return
                self._close_all()
                try:
                    self._open_all()
                except Exception as exc:
                    # Nothing is reaching the recording now, so say so. known_devices stays as it was, so this tries again.
                    log.warning("Reopening streams failed: %s", exc)
                    self.problems["devices"] = f"Nothing is being recorded right now, because the audio devices couldn't be reopened. Still trying. {exc}"
                    self._notice("The audio devices stopped working for a while, so part of this recording may be silent.")
                    continue
            if self.sources:
                self.problems.pop("devices", None)
            else:
                self.problems["devices"] = "Nothing is being recorded right now, because no microphone or computer audio could be opened. It will carry on when a device comes back."
                self._notice("The audio devices stopped working for a while, so part of this recording may be silent.")
            self.known_devices = current
            # The new stream hasn't delivered yet, and that isn't a stall. A slow mic gets to start, and a dead one
            # isn't reopened forever, when each try would cut a hole in the computer audio.
            self.mic.last_block = None
            names = self.device_names()
            mic_name = names["mic"][0] if names["mic"] else "none"
            self._notice(f"Audio devices changed. Your microphone is now {mic_name}.", urgent=names["mic"] != mics_before)
