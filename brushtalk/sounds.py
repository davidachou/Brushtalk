"""Plays the app's sound effects, which tools/make_sounds.py makes. controller.py decides when, so they stay out of recordings."""
from __future__ import annotations

import logging
import threading
import time
import wave
import winsound

from .config import UI_DIR

log = logging.getLogger(__name__)

FOLDER = UI_DIR / "sounds"
# A stuck audio device mustn't hold up a recording. The longest wait in normal use is about 0.3 seconds.
WAIT_AT_MOST = 1.0
# What Windows adds to a sound's length, opening the audio device and closing it again. Measured at about 0.09 seconds.
DEVICE_TIME = 0.09


def _play_to_the_end(path: str) -> None:
    try:
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_NODEFAULT)
    except RuntimeError:
        log.exception("Couldn't play %s", path)


def _seconds(path: str) -> float:
    with wave.open(path) as file:
        return file.getnframes() / file.getframerate()


def play(name: str, wait: bool = False) -> None:
    """wait returns once the sound has finished, for when recording starts right after it."""
    path = str(FOLDER / f"{name}.wav")
    if wait:
        began = time.perf_counter()
        thread = threading.Thread(target=_play_to_the_end, args=(path,), daemon=True, name="sound")
        thread.start()
        thread.join(WAIT_AT_MOST)
        # If another sound was still playing, Windows can say this one has finished when it hasn't: 4 of 36 tries, measured.
        time.sleep(max(0.0, began + _seconds(path) + DEVICE_TIME - time.perf_counter()))
    else:
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
