"""Telling a real echo from someone talking, by the sound itself.

Without headphones the mic hears the speakers. How the room changes that sound can be worked out from the two tracks, because whatever you say
on top of it has nothing to do with what the computer played, and averages away. Subtract the result from the mic, and what's left is whatever
didn't come out of the speakers.

Only the low frequencies are compared, and the middle of many short slices rather than the whole line. Rooms are predictable down there, and
typing, which can be far louder than the echo, mostly isn't there and only lasts a moment. Measured on the owner's PC, in
research_notes/Prompt mode/Real audio testing.md: real echo scores 0.65 to 0.96, even with typing going on, someone talking over it about 0.3, and
headphones 0.01.
"""
from __future__ import annotations

import numpy as np

RATE = 16000
FRAME = 2**15  # about 2 seconds, long enough to hold the delay and the room together
LONGEST_PATH = int(0.6 * RATE)  # samples: the 0.19 seconds the speakers lag on this PC, plus the room's echo after that
BLOCK = 60 * RATE  # the room is worked out afresh for each minute, because someone can change the volume
MARGIN = 30 * RATE  # a line can run up to 30 seconds past the minute it starts in
LOW_BAND = (100, 500)  # Hz
SLICE = RATE // 10
FROM_SPEAKERS = 0.6  # the score a line needs to count as an echo


def room_response(system: np.ndarray, mic: np.ndarray) -> np.ndarray:
    """What the speakers and the room do to the computer's sound on its way to the mic."""
    window = np.hanning(FRAME)
    played, heard = 0.0, 0.0
    for start in range(0, len(system) - FRAME + 1, FRAME // 2):
        x = np.fft.rfft(system[start : start + FRAME] * window)
        y = np.fft.rfft(mic[start : start + FRAME] * window)
        played = played + np.abs(x) ** 2
        heard = heard + np.conj(x) * y
    if np.isscalar(played):
        return np.zeros(LONGEST_PATH)
    # The small extra term keeps the frequencies the computer hardly played from counting for much.
    return np.fft.irfft(heard / (played + 1e-3 * np.mean(played) + 1e-12), FRAME)[:LONGEST_PATH]


def echo_of(system: np.ndarray, response: np.ndarray) -> np.ndarray:
    size = len(system) + len(response)
    return np.fft.irfft(np.fft.rfft(system, size) * np.fft.rfft(response, size), size)[: len(system)]


def low_band(sound: np.ndarray) -> np.ndarray:
    spectrum = np.fft.rfft(sound)
    frequencies = np.fft.rfftfreq(len(sound), 1 / RATE)
    spectrum[(frequencies < LOW_BAND[0]) | (frequencies >= LOW_BAND[1])] = 0
    return np.fft.irfft(spectrum, len(sound))


def score(heard: np.ndarray, echo: np.ndarray) -> float:
    """How much of the heard sound the echo explains, from 0 to 1: the middle of the short slices that have something in them."""
    starts = range(0, max(len(heard) - SLICE, 0) + 1, SLICE // 2)
    energies = np.array([float(np.sum(heard[start : start + SLICE] ** 2)) for start in starts])
    if not energies.any():
        return 0.0
    left = np.array([float(np.sum((heard[start : start + SLICE] - echo[start : start + SLICE]) ** 2)) for start in starts])
    loud = energies >= np.percentile(energies, 40)
    return max(0.0, float(np.median(1 - left[loud] / np.maximum(energies[loud], 1e-12))))


class RoomEcho:
    """Only does any work when it's asked about a line, so with headphones, where hardly any line gets that far, it costs next to nothing.
    It remembers one minute at a time, because lines are asked about in order and a long call's worth would take gigabytes."""

    def __init__(self, mic: np.ndarray, system: np.ndarray):
        self.mic = mic
        self.system = system
        self.block: int | None = None
        self.first = 0
        self.heard = np.zeros(0)
        self.echo = np.zeros(0)

    def _load(self, block: int) -> None:
        if block != self.block:
            self.block = block
            self.first = max(block * BLOCK - MARGIN, 0)
            last = (block + 1) * BLOCK + MARGIN
            system, mic = self.system[self.first : last].astype(np.float64), self.mic[self.first : last].astype(np.float64)
            self.heard = low_band(mic)
            self.echo = low_band(echo_of(system, room_response(system, mic)))

    def share(self, start: float, end: float) -> float:
        """How much of what the mic heard here came out of the speakers, from 0 to 1."""
        begin = int(start * RATE)
        self._load(begin // BLOCK)
        begin -= self.first
        stop = int(end * RATE) - self.first
        heard = self.heard[begin:stop]
        return score(heard, self.echo[begin:stop]) if len(heard) else 0.0

    def from_speakers(self, start: float, end: float) -> bool:
        return self.share(start, end) >= FROM_SPEAKERS
