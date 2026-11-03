"""The app's brain: one recorder, one job queue, shared by the window, the tray and the hotkey."""
from __future__ import annotations

import json
import logging
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from . import clipboard, engines, instructions, modeltests, prompts
from . import notes as notes_module
from . import storage
from .audio import SOUND_TAIL, AudioStuck, Recorder, device_key, list_devices
from .config import MODEL_NAME, ROOT, find_whisper_model, load_settings, save_settings
from .transcript import with_names

log = logging.getLogger(__name__)

FIRST_JOB = {"notes": "transcribe", "save": "save", "delete": "discard"}
MODEL_TEST_LIMIT = 600  # seconds, in case a test is left running
MODEL_TEST_MIN_SOUND = 0.3  # seconds of sound from the mic, below which there's nothing to compare
PROMPT_LIMIT = 600  # seconds of talking in one go, in case a prompt is left listening
COPIED_JUST_NOW = 15  # seconds: what you copied this recently counts as being for the prompt you're about to dictate
COPY_WAIT = 60  # seconds a proofread waits for you to copy something, so it can't take something you copy much later
UNDO_FOR = 8  # seconds a cancelled dictation can still be brought back, before it goes for good
EVENT_SOUNDS = {"notes_ready": "ready", "job_failed": "problem"}
PROMPT_SOUNDS = {"ready": "ready", "failed": "problem", "empty": "problem", "check": "check"}


class AppError(Exception):
    """A problem to show the user as it is."""


class JobFailed(Exception):
    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage
        self.message = message


class Controller:
    def __init__(self):
        self.settings = load_settings()
        self.lock = threading.RLock()
        self.recorder: Recorder | None = None
        self.recording_id: str | None = None
        self.recording_mode = "meeting"
        self.audio_test: Recorder | None = None
        self.audio_test_timer: threading.Timer | None = None
        self.model_test: Recorder | None = None
        self.model_test_id: str | None = None
        self.model_test_timer: threading.Timer | None = None
        self.current_test: str | None = None
        self.test_progress: dict | None = None
        self.test_version = 0
        self.clipboard = clipboard.Watcher()
        self.clipboard.start()
        self.prompt_recorder: Recorder | None = None
        self.prompt_timer: threading.Timer | None = None
        self.prompt_id: str | None = None
        self.prompt_stage: str | None = None
        self.prompt_message = ""
        self.prompt_check = 0
        self.prompt_check_words: list[str] = []
        self.prompt_added = 0
        self.prompt_kind = "prompt"
        self.prompt_about = ""
        self.prompt_copied = 0
        self.prompt_latest_copy: dict | None = None
        self.prompt_undo: dict | None = None  # a dictation just cancelled, while it can still be brought back
        self.prompt_copy_flashes = 0
        self.alert_flashes = 0
        self.prompt_version = 0
        self.prompt_shows = 0
        self.prompt_process: subprocess.Popen | None = None
        self.prompt_hold: subprocess.Popen | None = None
        self.prompt_cancelled = False
        self.prompt_second_try = False  # hearing or writing an old prompt again, rather than one you've just said
        self.version = 0
        self.queue: queue.Queue = queue.Queue()
        self.queued: list[str] = []
        self.progress: dict[str, dict] = {}
        self.current_job: str | None = None
        self.current_process: subprocess.Popen | None = None
        self.cancelled: set[str] = set()
        self.listeners: list = []
        # One per open page, so a page hears about a change now and not at its next check.
        self.page_wakers: set = set()
        # Only the desktop app sets this, so tests and test copies of the app stay silent.
        self.play_sound = None
        self.deleted_recording: str | None = None
        self.recycled_recording: str | None = None
        self.unsaved_failures: dict[str, str] = {}
        self.closing = False
        self.bar_opened_up = False  # low key: you clicked the tiny character, so the full bar is out for now
        self.hotkey_errors: dict[str, str | None] = {}
        self.devices_cache: dict | None = None
        self.worker = threading.Thread(target=self._job_loop, daemon=True, name="jobs")
        self.worker.start()

    # ------------------------------------------------------------- events

    def _emit(self, event: str, **data) -> None:
        # Before the listeners, because the desktop app's opens the bar, and the bar's page should already know why.
        for wake in list(self.page_wakers):
            wake()
        for listener in list(self.listeners):
            try:
                listener(event, **data)
            except Exception:
                log.exception("Listener failed on %s", event)
        if event in EVENT_SOUNDS:
            self.sound_when_quiet(EVENT_SOUNDS[event])

    # ------------------------------------------------------------- sounds

    # Nearly every sound plays while nothing is being kept, so it can't end up in a recording. The mic really does hear them, which is why the
    # order matters, and why what comes just after a sound is left out too: the mic hears it a little after Windows says it has finished.
    # Meetings get no pause sounds, because a meeting only pauses by clicking a button in front of you.
    # There are two exceptions. A copy landing, because you can't stop talking to hear it, and it's short enough for speech to come through:
    # see _copy_landed. And a recording going wrong, which is rare, and worth a sound on top of your words: see recording_went_wrong.

    def sounds_on(self) -> bool:
        return bool(self.play_sound and self.settings["sounds"])

    def _sound(self, name: str, wait: bool = False) -> None:
        """A sound must never get in the way of a recording, so if one can't play, it just doesn't."""
        if self.sounds_on():
            try:
                self.play_sound(name, wait)
            except Exception:
                log.exception("Couldn't play the %s sound", name)

    def sound_when_quiet(self, name: str) -> None:
        """For what finishes by itself, at any moment. If anything is being recorded it stays silent, and the notice still shows."""
        if not (self.recorder or self.prompt_recorder or self.model_test or self.audio_test):
            self._sound(name)

    def recording_went_wrong(self) -> None:
        """A dead mic can cost you a whole call, and during one you may have hidden the bar, or Windows may be holding back its notices."""
        self.alert_flashes += 1
        self._sound("problem")

    def _open_with_sound(self, recorder: Recorder) -> None:
        """With computer audio in the recording, the sound plays before anything opens. With only your mic, the sound is your cue to talk,
        so the mic opens first, because it takes a moment, and what it hears is kept from when the sound ends."""
        if not self.sounds_on():
            recorder.start()
        elif recorder.mic_only:
            recorder.hold()
            recorder.start()
            self._sound("start", wait=True)
            recorder.keep_after(SOUND_TAIL)
            recorder.release()
        else:
            self._sound("start", wait=True)
            recorder.keep_after(SOUND_TAIL)
            recorder.start()

    def _end_with_sound(self, recorder: Recorder) -> None:
        """Nothing more is kept from here on, so the sound can play at once, while the slower closing down carries on behind it."""
        if self.sounds_on():
            recorder.pause()
            self._sound("finish")

    def _pause_with_sound(self, recorder: Recorder) -> None:
        if recorder.paused_at is None:
            recorder.pause()
            self._sound("pause")

    def _resume_with_sound(self, recorder: Recorder) -> None:
        if recorder.paused_at is not None and self.sounds_on():
            self._sound("resume", wait=True)
            recorder.keep_after(SOUND_TAIL)
        recorder.resume()

    def bump(self) -> None:
        self.version += 1

    # ------------------------------------------------------------- recording

    def is_recording(self) -> bool:
        return self.recorder is not None

    def is_capturing(self) -> bool:
        """Anything at all being recorded: a meeting or note, a prompt or a test clip."""
        return bool(self.recorder or self.prompt_recorder or self.model_test)

    def start_recording(self, title: str = "", mode: str = "meeting") -> dict:
        """mode is "meeting", or "solo" for talking alone, which records only the mic."""
        with self.lock:
            if self.recorder:
                raise AppError("Already recording.")
            # You've moved on, so a dictation you cancelled just now goes, rather than waiting to be brought back under a call.
            self._forget_cancelled()
            self.stop_audio_test()
            # A real call matters more than a test clip. A prompt you were dictating gets finished behind it, as if you'd pressed Finish.
            self.drop_model_test()
            self.stop_prompt()
            meta = storage.create(title, mode)
            path = storage.folder(meta["id"])
            try:
                recorder = Recorder(path, self.settings["mic_device"], self.settings["output_device"], mic_only=mode == "solo")
                self._open_with_sound(recorder)
            except Exception as exc:
                log.exception("Could not start recording")
                shutil.rmtree(path, ignore_errors=True)
                self._sound("problem")
                raise AppError(f"Recording couldn't start: {exc}") from exc
            self.recorder = recorder
            self.recording_id = meta["id"]
            self.recording_mode = mode
            storage.update_meta(meta["id"], devices=recorder.device_names())
            self.bump()
        log.info("Recording started: %s", meta["id"])
        self._emit("recording_started", meeting_id=meta["id"], mode=mode)
        return meta

    def stop_recording(self, after: str | None = None) -> str:
        """after is "notes", "save" or "delete". Left out, Settings decides: that's the shortcut, the tray and the floating bar."""
        with self.lock:
            recorder, meeting_id = self.recorder, self.recording_id
            if not recorder:
                raise AppError("Nothing is recording.")
            # Set first, so that no window can see the recording end without knowing it's being deleted, whichever window deleted it.
            if after == "delete":
                self.deleted_recording = meeting_id
            self.recorder = None
            self.recording_id = None
            self._end_with_sound(recorder)
            stats = self._stop_recorder(recorder, storage.folder(meeting_id))
            if after not in FIRST_JOB:
                after = self.settings["after_stop"]
            try:
                storage.update_meta(
                    meeting_id,
                    status="saving",
                    save_only=after != "notes",
                    discard=after == "delete",
                    duration=stats["duration"],
                    devices=stats["devices"],
                    sound_seconds=stats["sound_seconds"],
                    warnings=_everything_to_say(recorder, stats),
                )
            except OSError:
                # The disk may be what's failing. The job still tries, and if it can't, the next start picks this recording up.
                log.exception("Couldn't save how %s ended", meeting_id)
            self._enqueue(meeting_id, FIRST_JOB[after])
            self.bump()
        log.info("Recording stopped: %s, %.0f s", meeting_id, stats["duration"])
        self._emit("recording_stopped", meeting_id=meeting_id, after=after)
        return meeting_id

    def _stop_recorder(self, recorder: Recorder, path: Path) -> dict:
        """What's on the disk is safe whatever happens here, so a recorder that can't stop properly doesn't get to lose the recording."""
        try:
            return recorder.stop()
        except Exception as exc:
            log.exception("Stopping the recorder failed")
            seconds = round(storage.raw_seconds(path), 2)
            return {
                "duration": seconds,
                "sound_seconds": {"mic": seconds, "system": seconds},
                "devices": {"mic": [], "system": []},
                "notices": [f"This recording didn't end cleanly: {exc}. Everything up to that point was saved."],
            }

    def toggle_recording(self, mode: str = "meeting") -> None:
        """Each shortcut starts its own mode. Once going, the solo and prompt ones pause and resume, and the meeting one stops."""
        if self.model_test:
            self.stop_model_test()
        elif self.prompt_recorder:
            if mode == "meeting":
                self.stop_prompt()
            else:
                self.pause_or_resume_prompt()
        elif self.is_recording() and mode == "proofread":
            # The recording has the mic, so it proofreads without listening, rather than not at all.
            self.proofread()
        elif self.is_recording():
            if self.recording_mode == "meeting" and mode != "meeting":
                # One stray key shouldn't end the recording of a call.
                raise AppError(f"You're recording a meeting. Press {self.settings['hotkey']} to stop it first.")
            if self.recording_mode == "solo" and mode != "meeting":
                (self.resume if self.recorder.paused_at else self.pause)()
            else:
                self.stop_recording()
        elif mode in ("prompt", "code", "proofread"):
            self.start_prompt(kind=mode)
        else:
            self.start_recording(mode=mode)

    def finish(self) -> None:
        """The finish shortcut: whatever is going is done, whether it's paused or not."""
        if self.model_test:
            self.stop_model_test()
        elif self.prompt_recorder:
            self.stop_prompt()
        elif self.is_recording():
            self.stop_recording()

    def pause(self) -> None:
        with self.lock:
            if self.recorder:
                if self.recording_mode == "meeting":
                    self.recorder.pause()
                else:
                    self._pause_with_sound(self.recorder)
                self._emit("recording_paused")

    def resume(self) -> None:
        with self.lock:
            if self.recorder:
                if self.recording_mode == "meeting":
                    self.recorder.resume()
                else:
                    self._resume_with_sound(self.recorder)
                self._emit("recording_resumed")

    # ------------------------------------------------------------- audio test

    def start_audio_test(self) -> None:
        with self.lock:
            if self.recorder:
                raise AppError("Stop recording before testing your audio.")
            # The same check as everything else that records, so nothing ends up with two recordings at once.
            if self.prompt_recorder:
                raise AppError("Finish the prompt you're dictating first.")
            if self.model_test:
                raise AppError("Finish the model test first.")
            self.stop_audio_test()
            recorder = Recorder(None, self.settings["mic_device"], self.settings["output_device"])
            try:
                recorder.start()
            except Exception as exc:
                raise AppError(f"Audio couldn't start: {exc}") from exc
            self.audio_test = recorder
            self.audio_test_timer = threading.Timer(60, self.stop_audio_test)
            self.audio_test_timer.daemon = True
            self.audio_test_timer.start()

    def stop_audio_test(self) -> None:
        with self.lock:
            test, self.audio_test = self.audio_test, None
            if self.audio_test_timer:
                self.audio_test_timer.cancel()
                self.audio_test_timer = None
        if test:
            test.stop()

    # ------------------------------------------------------------- model tests

    def start_model_test(self, language: str, hint: str = "talking") -> dict:
        with self.lock:
            if self.recorder:
                raise AppError("Stop recording before testing the models.")
            if self.model_test:
                raise AppError("A test is already listening.")
            if self.prompt_recorder:
                raise AppError("Finish dictating your prompt first.")
            self._forget_cancelled()
            self.stop_audio_test()
            meta = modeltests.create(language, hint)
            path = modeltests.folder(meta["id"])
            try:
                recorder = Recorder(path, self.settings["mic_device"], mic_only=True)
                recorder.quiet_after, recorder.quiet_again_after = 8.0, 60.0
                recorder.start()
            except Exception as exc:
                log.exception("Could not start a model test")
                shutil.rmtree(path, ignore_errors=True)
                raise AppError(f"The microphone couldn't start: {exc}") from exc
            self.model_test = recorder
            self.model_test_id = meta["id"]
            self.model_test_timer = threading.Timer(MODEL_TEST_LIMIT, self.stop_model_test)
            self.model_test_timer.daemon = True
            self.model_test_timer.start()
        return meta

    def _take_model_test(self) -> tuple[Recorder | None, str | None]:
        recorder, test_id = self.model_test, self.model_test_id
        self.model_test = None
        self.model_test_id = None
        if self.model_test_timer:
            self.model_test_timer.cancel()
            self.model_test_timer = None
        return recorder, test_id

    def stop_model_test(self) -> str | None:
        """Hands what was said to every model. Fires by itself if a test is left running."""
        with self.lock:
            recorder, test_id = self._take_model_test()
            if not recorder:
                return None
            stats = self._stop_recorder(recorder, modeltests.folder(test_id))
            heard = stats["sound_seconds"]["mic"]
            try:
                meta = modeltests.update(test_id, status="saving", duration=stats["duration"], microphone=(stats["devices"]["mic"] or [None])[0], silent=heard < MODEL_TEST_MIN_SOUND, warnings=_everything_to_say(recorder, stats))
                self._queue_model_runs(test_id, meta["language"] if heard >= MODEL_TEST_MIN_SOUND else None, meta["hint"])
            except OSError:
                # The next start picks the clip up, because it still says it's recording.
                log.exception("Couldn't save how test %s ended", test_id)
                self.test_version += 1
        return test_id

    def drop_model_test(self) -> None:
        """Stops listening and throws the clip away. It's only a test, so it doesn't go to the Recycle Bin."""
        with self.lock:
            recorder, test_id = self._take_model_test()
            if recorder:
                self._stop_recorder(recorder, modeltests.folder(test_id))
                shutil.rmtree(modeltests.folder(test_id), ignore_errors=True)
                self.test_version += 1

    def _queue_model_runs(self, test_id: str, language: str | None, hint: str) -> None:
        """language None only tidies up the audio, for a clip with nothing in it."""
        if language:
            skip = set(self.settings["test_skip"])
            chosen = [engine for engine in engines.available() if engine["id"] not in skip] or [engines.WHISPER]
            modeltests.add_runs(test_id, chosen, language, hint)
        self.queue.put((test_id, "model_test"))
        self.test_version += 1

    def run_model_test_again(self, test_id: str, language: str, hint: str = "talking") -> None:
        with self.lock:
            meta = modeltests.load(test_id)
            if modeltests.is_busy(meta):
                raise AppError("The models are still working on this test.")
            if not storage.holds_audio(modeltests.folder(test_id)):
                raise AppError("The audio for this test is gone.")
            self.cancelled.discard(test_id)
            self._queue_model_runs(test_id, language, hint)

    def cancel_model_test(self, test_id: str) -> None:
        with self.lock:
            self.cancelled.add(test_id)
            if test_id == self.current_test and self.current_process:
                _kill_tree(self.current_process)

    def _run_model_test(self, test_id: str) -> None:
        """Every waiting model in turn, so the timings are fair. One failing doesn't stop the others."""
        self.current_test = test_id
        self.test_version += 1
        try:
            flac = storage.finalize_audio(modeltests.folder(test_id))
            modeltests.update(test_id, status="saved", error=None, playback_gain=storage.playback_gains(flac))
            self.test_version += 1
            waiting = [(index, run) for index, run in enumerate(modeltests.load(test_id)["runs"]) if run["state"] == "waiting"]
            for index, run in waiting:
                self._run_one_model(test_id, index, run)
            # You'll have gone off to do something else, so this says when to come back. Stopping it yourself needs no telling.
            if waiting and test_id not in self.cancelled and not self.closing:
                runs = modeltests.load(test_id)["runs"]
                self.sound_when_quiet("ready" if any(runs[index]["state"] == "done" for index, _ in waiting) else "problem")
        except Exception as exc:
            log.exception("Model test failed: %s", test_id)
            self.sound_when_quiet("problem")
            try:
                modeltests.give_up(test_id, f"This test couldn't go on: {exc}. Its audio is kept, so you can press Run again.")
            except Exception:
                log.exception("Couldn't save that test %s failed", test_id)
        finally:
            self.current_test = None
            self.current_process = None
            self.test_progress = None
            self.cancelled.discard(test_id)
            self.test_version += 1

    def _run_one_model(self, test_id: str, index: int, run: dict) -> None:
        if test_id in self.cancelled or self.closing:
            modeltests.update_run(test_id, index, state="stopped")
            return
        # What it's given is noted as it starts, not when it was queued, since a hint can be edited while a run waits its turn.
        hint, language = run.get("hint", "meeting"), run["language"]
        modeltests.update_run(test_id, index, state="running", hint_edit=instructions.edited_hint(run["engine"], hint, language), built_in=instructions.built_in_hints(hint, language))
        self.test_progress = {"run": index, "stage": "loading", "fraction": 0.0}
        self.test_version += 1
        filed = {}
        notes = []

        def on_event(event: dict) -> None:
            if "version" in event:
                filed["version"] = event["version"]
            if event.get("note"):
                notes.append(event["note"])
            if event.get("stage") == "transcribing":
                self.test_progress = {"run": index, "stage": "transcribing", "fraction": event.get("fraction", 0.0)}

        try:
            code, error = self._run_worker(modeltests.folder(test_id), run["engine"], run["language"], False, True, on_event, hint=run.get("hint", "meeting"), mic_only=True)
            modeltests.update_run(test_id, index, notes=notes)
            if test_id in self.cancelled or self.closing:
                modeltests.update_run(test_id, index, state="stopped")
            elif code != 0:
                modeltests.update_run(test_id, index, state="failed", error=error or "It stopped unexpectedly.")
            else:
                modeltests.finish_run(test_id, index, filed.get("version"))
        except Exception as exc:
            log.exception("%s failed on test %s", run["engine"], test_id)
            modeltests.update_run(test_id, index, state="failed", error=str(exc))
        self.test_version += 1

    # ------------------------------------------------------------- prompts

    def start_prompt(self, typed: str = "", kind: str = "prompt") -> dict:
        """kind is "prompt", "code" for the code itself, or "proofread" for proofreading with what you say about how. They go the same way
        until the AI is asked to write. Proofreading always uses what you copy, since the text is the point."""
        with self.lock:
            # You've moved on from the proofread that was waiting for you to copy something, or the dictation you cancelled.
            self._forget_cancelled()
            if self.prompt_stage == "copy":
                self._set_prompt_stage(None, None)
            if self.recorder and kind == "proofread":
                return self.proofread(typed)
            if self.recorder:
                raise AppError("Stop recording before dictating a prompt.")
            if self.model_test:
                raise AppError("Finish the model test first.")
            if self.prompt_recorder:
                raise AppError("Already listening for a prompt.")
            if self.prompt_stage in ("hearing", "writing"):
                raise AppError("Still writing your last prompt.")
            self.stop_audio_test()
            meta = prompts.create(kind)
            if self.settings["prompt_include_copied"] and kind == "prompt":
                meta = prompts.update(meta["id"], include_text=True)
            path = prompts.folder(meta["id"])
            try:
                recorder = Recorder(path, self.settings["mic_device"], mic_only=True)
                recorder.quiet_after, recorder.quiet_again_after = 8.0, 60.0
                self._open_with_sound(recorder)
            except Exception as exc:
                log.exception("Could not start listening for a prompt")
                shutil.rmtree(path, ignore_errors=True)
                self._sound("problem")
                raise AppError(f"The microphone couldn't start: {exc}") from exc
            self.prompt_recorder = recorder
            self.prompt_kind = kind
            self.prompt_cancelled = False
            self.prompt_second_try = False
            self.prompt_hold = self._start_hold(path)
            self._restart_prompt_timer()
            self.prompt_copied, self.prompt_latest_copy = 0, None
            proofread = kind == "proofread"
            use_copied = self.settings["prompt_use_copied"] or proofread
            if use_copied:
                copied = self.clipboard.recent(COPIED_JUST_NOW)
                if copied and not proofread and len(copied) > prompts.TEXT_LIMIT:
                    self._copy_refused(copied)
                elif copied:
                    self._copy_landed(prompts.add_text(meta["id"], "copied", copied), copied)
            if typed.strip():
                (prompts.replace_text(meta["id"], "typed", typed) if proofread else prompts.set_typed(meta["id"], typed))
            self._set_prompt_stage(meta["id"], "listening")
            if use_copied:
                self.clipboard.on_copy = self._on_copied_while_talking
        return meta

    def _start_hold(self, path: Path) -> subprocess.Popen | None:
        """Whisper takes over a second to load, and a prompt gets waited for, so it loads while you talk and is ready when you finish.

        It's still its own process, which ends with the prompt, so the graphics memory is only taken while a prompt is open.
        """
        model = find_whisper_model(self.settings)
        # A model that still has to be downloaded is left to the usual way, which shows the download.
        if self.settings["prompt_speech_engine"] != "whisper" or not model:
            return None
        try:
            with open(path / "worker.log", "w", encoding="utf-8") as stderr:
                return subprocess.Popen(
                    [_python(), "-m", "brushtalk.worker", "--hold", model, str(ROOT / "models"), self.settings["compute"]],
                    cwd=str(ROOT),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=stderr,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
        except OSError:
            log.exception("Couldn't get Whisper ready ahead of time")
            return None

    def _release_hold(self) -> None:
        process, self.prompt_hold = self.prompt_hold, None
        if process:
            _kill_tree(process)
            try:
                # Its log file has to be closed before the prompt's folder can go.
                process.wait(5)
            except subprocess.TimeoutExpired:
                log.warning("Whisper didn't stop when it was told to")

    def _restart_prompt_timer(self) -> None:
        """Left talking by mistake, it pauses by itself rather than recording on and on."""
        if self.prompt_timer:
            self.prompt_timer.cancel()
        self.prompt_timer = threading.Timer(PROMPT_LIMIT, self.pause_prompt)
        self.prompt_timer.daemon = True
        self.prompt_timer.start()

    def pause_prompt(self) -> None:
        with self.lock:
            if self.prompt_recorder:
                self._pause_with_sound(self.prompt_recorder)
                if self.prompt_timer:
                    self.prompt_timer.cancel()
                    self.prompt_timer = None
                self.prompt_version += 1
                self._emit("prompt_paused")

    def resume_prompt(self) -> None:
        with self.lock:
            if self.prompt_recorder:
                self._resume_with_sound(self.prompt_recorder)
                self._restart_prompt_timer()
                self.prompt_version += 1
                self._emit("prompt_resumed")

    def pause_or_resume_prompt(self) -> None:
        recorder = self.prompt_recorder
        if recorder:
            (self.resume_prompt if recorder.paused_at else self.pause_prompt)()

    def _on_copied_while_talking(self, text: str) -> None:
        """Runs for the whole prompt, pauses included: copying a passage, then talking about it, is the usual way."""
        with self.lock:
            recorder, prompt_id = self.prompt_recorder, self.prompt_id
            if recorder and prompt_id and self.prompt_kind == "proofread":
                had = bool(prompts.original(prompts.load(prompt_id)).strip())
                self._copy_landed(prompts.replace_text(prompt_id, "copied", text, at=round(recorder.elapsed(), 1)), text, "Proofreading this one instead" if had else None)
            elif recorder and prompt_id and len(text) > prompts.TEXT_LIMIT:
                self._copy_refused(text)
            elif recorder and prompt_id:
                self._copy_landed(prompts.add_text(prompt_id, "copied", text, at=round(recorder.elapsed(), 1), between_takes=recorder.paused_at is not None), text)

    def _copy_landed(self, meta: dict, text: str, said: str | None = None) -> None:
        """The bar and the window make something of this, and say what and how much: it's on its way to an AI, and it's easy to copy something without meaning to.
        The sound can land on top of your words, and in testing that changed no more of them than a different background noise did."""
        held = sum(item["kind"] == "copied" for item in meta["text"])
        about = prompts.about_copy(text)
        if said:
            about = dict(about, said=said)
        self.prompt_latest_copy = about if held > self.prompt_copied or said else dict(about, said="Already added")
        self.prompt_copied = held
        self.prompt_copy_flashes += 1
        self.prompt_version += 1
        if self.settings["copy_sound"]:
            self._sound("copied")

    def _copy_refused(self, text: str) -> None:
        """Too long to send. Cutting it would be worse, because code made from it would come back without its end, to be pasted over the
        whole. The bar says so the way it says what came in, with nothing to take back, and no copy sound, because nothing came in."""
        said = f"Too long to add: {len(text):,} characters, and the limit is {prompts.TEXT_LIMIT:,}. Copy a smaller part."
        self.prompt_latest_copy = dict(prompts.about_copy(text), said=said, added=False)
        self.prompt_copy_flashes += 1
        self.prompt_version += 1

    def undo_copy(self, prompt_id: str, key: str) -> None:
        """Takes a passage back out, right up until the AI is given it. Not off the clipboard, where you may still want it, and copying it again puts it back."""
        with self.lock:
            listening = prompt_id == self.prompt_id and self.prompt_recorder
            if not listening and prompts.load(prompt_id)["status"] != "check":
                raise AppError("The AI has already been given that prompt, so it's too late to take that back.")
            copies = [item["text"] for item in prompts.remove_copied(prompt_id, key)["text"] if item["kind"] == "copied"]
            if listening:
                self.prompt_copied = len(copies)
                self.prompt_latest_copy = prompts.about_copy(copies[-1]) if copies else None
            self.prompt_version += 1

    def set_prompt_typed(self, text: str, prompt_id: str) -> None:
        """For the prompt it was typed in. Just after you finish it still counts, because the writer hasn't started. After a cancel it's dropped,
        rather than going into whichever prompt is open by then."""
        if prompt_id == self.prompt_id and self.prompt_stage in ("listening", "hearing") and not self.prompt_cancelled:
            if self.prompt_kind == "proofread" and text.strip():
                prompts.replace_text(prompt_id, "typed", text)
            else:
                prompts.set_typed(prompt_id, text)
            self.prompt_version += 1

    def _take_prompt(self) -> tuple[Recorder | None, str | None]:
        recorder, prompt_id = self.prompt_recorder, self.prompt_id
        self.prompt_recorder = None
        self.clipboard.on_copy = None
        if self.prompt_timer:
            self.prompt_timer.cancel()
            self.prompt_timer = None
        return recorder, prompt_id

    def stop_prompt(self) -> str | None:
        """Everything after this happens on its own thread, so a prompt never waits behind a long meeting."""
        with self.lock:
            # Nothing is listening. A proofread waiting for you to copy something, as a meeting starts, keeps waiting: it doesn't need the mic.
            if not self.prompt_recorder:
                return None
            recorder, prompt_id = self._take_prompt()
            stopped = time.perf_counter()
            self._end_with_sound(recorder)
            stats = self._stop_recorder(recorder, prompts.folder(prompt_id))
            try:
                prompts.update(prompt_id, duration=stats["duration"], microphone=(stats["devices"]["mic"] or [None])[0], notes=_everything_to_say(recorder, stats))
            except OSError:
                log.exception("Couldn't save how prompt %s ended", prompt_id)
            self._set_prompt_stage(prompt_id, "hearing")
        heard = stats["sound_seconds"]["mic"] >= MODEL_TEST_MIN_SOUND
        threading.Thread(target=self._finish_prompt, args=(prompt_id, heard, stopped), daemon=True, name="prompt").start()
        return prompt_id

    def drop_prompt(self) -> None:
        """Stops listening and throws it away, after a few seconds in which Undo brings it back, or stops working on one that was already
        said. Cancelling one that's waiting to be brought back throws it away now."""
        with self.lock:
            if self.prompt_stage == "cancelled":
                self._forget_cancelled()
                return
            kind, (recorder, prompt_id) = self.prompt_kind, self._take_prompt()
            if recorder:
                stats = self._stop_recorder(recorder, prompts.folder(prompt_id))
                self._release_hold()
                self._keep_for_undo(prompt_id, kind, stats["sound_seconds"]["mic"], recorder.takes)
            elif self.prompt_stage == "copy":
                self._set_prompt_stage(None, None)
            elif self.prompt_stage in ("hearing", "writing"):
                self.prompt_cancelled = True
                if self.prompt_process:
                    _kill_tree(self.prompt_process)

    def _keep_for_undo(self, prompt_id: str, kind: str, heard: float, takes: int) -> None:
        """Five or ten takes are a lot to lose to the wrong button, so a cancelled dictation goes a few seconds later, not at once. It's marked
        cancelled first, so quitting, or a crash, before then still throws it away."""
        self._forget_cancelled()
        prompts.update(prompt_id, status="cancelled")
        timer = threading.Timer(UNDO_FOR, self._forget_cancelled, args=(prompt_id,))
        timer.daemon = True
        timer.start()
        self.prompt_undo = {"id": prompt_id, "kind": kind, "heard": heard, "takes": takes, "timer": timer}
        self._set_prompt_stage(prompt_id, "cancelled")

    def _forget_cancelled(self, prompt_id: str | None = None) -> None:
        """Time's up, or something else has started: the cancelled dictation goes for good, as cancelling used to at once.
        prompt_id is the timer's, which does nothing if that one has been brought back or already gone."""
        with self.lock:
            undo = self.prompt_undo
            if not undo or (prompt_id and undo["id"] != prompt_id):
                return
            self.prompt_undo = None
            undo["timer"].cancel()
            self._remove_prompt(undo["id"])
            if self.prompt_stage == "cancelled" and self.prompt_id == undo["id"]:
                self._set_prompt_stage(None, None)

    def undo_cancel(self) -> dict:
        """Brings back the dictation you've just cancelled, paused, as it was: Talk carries on with it, and Finish has it written."""
        with self.lock:
            undo = self.prompt_undo
            if not undo or self.prompt_stage != "cancelled":
                raise AppError("It's too late to bring that back.")
            if self.is_capturing():
                raise AppError("Something else is recording now.")
            path = prompts.folder(undo["id"])
            recorder = Recorder(path, self.settings["mic_device"], mic_only=True)
            recorder.quiet_after, recorder.quiet_again_after = 8.0, 60.0
            recorder.carry_on(undo["heard"], undo["takes"])
            try:
                recorder.start()
            except Exception as exc:
                log.exception("Couldn't bring the prompt back")
                raise AppError(f"The microphone couldn't start, so it stays cancelled: {exc}") from exc
            recorder.pause()
            self.prompt_undo = None
            undo["timer"].cancel()
            meta = prompts.update(undo["id"], status="listening")
            self.prompt_recorder, self.prompt_kind = recorder, undo["kind"]
            self.prompt_cancelled = False
            self.prompt_hold = self._start_hold(path)
            self.prompt_copied, self.prompt_latest_copy = sum(item["kind"] == "copied" for item in meta["text"]), None
            self._set_prompt_stage(undo["id"], "listening")
            if self.settings["prompt_use_copied"] or undo["kind"] == "proofread":
                self.clipboard.on_copy = self._on_copied_while_talking
            self._emit("prompt_paused")
        return meta

    # ------------------------------------------------------------- proofreading

    def proofread(self, typed: str = "") -> dict:
        """No talking, so no microphone, which means it can run during a recording. It takes text typed into the window, or what you copied just now.
        Failing those it waits for you to copy something, so that it never sends something that's merely been sitting on the clipboard."""
        with self.lock:
            self._forget_cancelled()
            # Asking again while it waits is changing your mind.
            if self.prompt_stage == "copy" and not typed.strip():
                self._set_prompt_stage(None, None)
                return {"stage": None}
            if self.prompt_recorder:
                raise AppError("Finish the prompt you're dictating first.")
            if self.prompt_stage in ("hearing", "writing"):
                raise AppError("Still writing your last one.")
            self.prompt_kind = "proofread"
            text = typed if typed.strip() else self.clipboard.recent(COPIED_JUST_NOW)
            if text:
                return self._start_proofread(text, "typed" if typed.strip() else "copied")
            self.clipboard.on_copy = self._on_copied_to_proofread
            self.prompt_timer = threading.Timer(COPY_WAIT, self._stop_waiting_for_copy)
            self.prompt_timer.daemon = True
            self.prompt_timer.start()
            self._set_prompt_stage(None, "copy")
            return {"stage": "copy"}

    def _on_copied_to_proofread(self, text: str) -> None:
        with self.lock:
            if self.prompt_stage == "copy":
                self._start_proofread(text, "copied")

    def _stop_waiting_for_copy(self) -> None:
        """Nothing has gone anywhere, so there's nothing to say about it."""
        with self.lock:
            if self.prompt_stage == "copy":
                self._set_prompt_stage(None, None)

    def _start_proofread(self, text: str, source: str) -> dict:
        if len(text) > prompts.TEXT_LIMIT:
            message = f"Too long: {len(text):,} characters, and the limit is {prompts.TEXT_LIMIT:,}. Copy a smaller part. Your clipboard hasn't changed."
            self._set_prompt_stage(None, "failed", message)
            return {"stage": "failed", "message": message}
        meta = prompts.create("proofread")
        prompts.add_text(meta["id"], source, text)
        self.prompt_cancelled = False
        self.prompt_second_try = False
        self._set_prompt_stage(meta["id"], "writing")
        self.sound_when_quiet("copied")
        self._write_on_its_own_thread(meta["id"])
        return {"stage": "writing", "id": meta["id"]}

    def _set_prompt_aside(self) -> None:
        """For quitting: nothing more happens to it now, and nothing is thrown away. The next start finds it, ready to try again."""
        with self.lock:
            recorder, prompt_id = self._take_prompt()
            if recorder:
                self._stop_recorder(recorder, prompts.folder(prompt_id))
                self._release_hold()
            if self.prompt_process:
                _kill_tree(self.prompt_process)

    def _set_prompt_stage(self, prompt_id: str | None, stage: str | None, message: str = "", check: int = 0, added: int = 0, check_words: list[str] | None = None, about: str = "") -> None:
        if self.prompt_stage == "copy" and stage != "copy":
            self._take_prompt()
        self.prompt_id = prompt_id
        self.prompt_stage = stage
        self.prompt_message = message
        self.prompt_check = check
        self.prompt_check_words = check_words or []
        self.prompt_added = added
        self.prompt_about = about
        self.prompt_version += 1
        if prompt_id and stage != "listening":
            # The window goes on to show this either way, and the next start sorts out a prompt that couldn't be marked.
            try:
                prompts.update(prompt_id, status=stage, error=message if stage == "failed" else None)
            except OSError:
                log.exception("Couldn't save the state of prompt %s", prompt_id)
        self._emit("prompt_stage", stage=stage, prompt_id=prompt_id)
        sound = PROMPT_SOUNDS.get(stage)
        # The chime means go ahead and paste, which isn't so if it never reached the clipboard, or there's something to look at first.
        if stage == "ready" and (message or check):
            sound = "problem" if message else "check"
        if sound:
            self.sound_when_quiet(sound)

    def _track_prompt_process(self, process) -> bool:
        """Says whether to go on. A cancel can arrive while a process is starting, when there's nothing yet for it to stop."""
        self.prompt_process = process
        if process and (self.prompt_cancelled or self.closing):
            _kill_tree(process)
            return False
        return True

    def _finish_prompt(self, prompt_id: str, heard: bool, stopped: float) -> None:
        try:
            flac = storage.finalize_audio(prompts.folder(prompt_id))
            prompts.update(prompt_id, playback_gain=storage.playback_gains(flac))
            # Talking is optional when proofreading: with nothing said it's proofread as it is. With nothing copied there's nothing to do.
            proofread = prompts.is_proofread(prompts.load(prompt_id))
            if proofread and not prompts.original(prompts.load(prompt_id)).strip():
                self._set_prompt_stage(prompt_id, "failed", "Nothing was copied to proofread. Your clipboard hasn't changed.")
                return
            if not heard and not proofread:
                self._set_prompt_stage(prompt_id, "empty", "The microphone didn't hear anything, so nothing was written.")
                return
            if heard and not self._hear_prompt(prompt_id, optional=proofread):
                return
            if not heard:
                # A proofread too quiet to be worth hearing: nothing was said, so it's a plain one. Noted as heard, so if writing it fails,
                # the page doesn't take that for the hearing having failed and offer to hear it again.
                prompts.update(prompt_id, spoken=[])
            timing = {"hear_seconds": round(time.perf_counter() - stopped, 1)}
            if self.settings["prompt_check_first"] and not proofread:
                # Nothing has gone to the AI, and nothing does until you press Write it.
                prompts.update(prompt_id, timing=timing)
                self._set_prompt_stage(prompt_id, "check")
                return
            self._write_prompt(prompt_id, timing, stopped)
        except Exception as exc:
            log.exception("Prompt failed: %s", prompt_id)
            self._set_prompt_stage(prompt_id, "failed", str(exc))
        finally:
            self._release_hold()
            self.prompt_process = None

    def _hear_prompt(self, prompt_id: str, optional: bool = False) -> bool:
        """Says whether there's anything to write from. It goes on saying what's wrong otherwise. optional is for when words aren't needed."""
        path = prompts.folder(prompt_id)
        meta = prompts.load(prompt_id)
        filed = {"notes": []}

        def on_event(event: dict) -> None:
            if "version" in event:
                filed["version"] = event["version"]
            if "engine_label" in event:
                filed["label"] = event["engine_label"]
            if event.get("note"):
                filed["notes"].append(event["note"])

        names = prompts.names_from_text([item["text"] for item in meta["text"]])
        held, self.prompt_hold = self.prompt_hold, None
        code, error = self._run_worker(path, self.settings["prompt_speech_engine"], self.settings["language"], False, False, on_event, hint="talking", mic_only=True, extra_terms=names, on_process=self._track_prompt_process, held=held)
        if self.prompt_cancelled:
            self._end_cancelled_prompt(prompt_id)
            return False
        if self.closing:
            return False
        if code != 0:
            self._set_prompt_stage(prompt_id, "failed", error or "The speech model stopped unexpectedly.")
            return False
        spoken = json.loads((path / "transcript.json").read_text(encoding="utf-8"))
        spoken = [{"start": line["start"], "end": line["end"], "text": line["text"]} for line in spoken]
        notes = list(dict.fromkeys([*(meta.get("notes") or []), *filed["notes"]]))
        prompts.update(prompt_id, spoken=spoken, speech_model=filed.get("label"), notes=notes)
        if not spoken and not optional:
            self._set_prompt_stage(prompt_id, "empty", "No words were heard, so nothing was written.")
            return False
        return True

    def _remove_prompt(self, prompt_id: str) -> None:
        """Windows can hold on to a stopped process's log file for a moment, and the folder can't go until it lets go."""
        path = prompts.folder(prompt_id)
        for _ in range(40):
            shutil.rmtree(path, ignore_errors=True)
            if not path.exists():
                return
            time.sleep(0.05)
        log.warning("Couldn't remove %s", path)

    def _end_cancelled_prompt(self, prompt_id: str) -> None:
        """Cancelling throws away what you've just said. Cancelling another try at an old prompt only stops that try: what's there already stays,
        and words with nothing written from them yet go back to waiting for you."""
        self.prompt_cancelled = False
        if self.prompt_second_try:
            meta = prompts.load(prompt_id)
            written = bool(meta.get("prompt"))
            if not written and prompts.spoken_text(meta).strip():
                self._set_prompt_stage(prompt_id, "check")
                return
            prompts.update(prompt_id, status="ready" if written else "failed", error=None if written else "Stopped before it finished.")
        else:
            self._remove_prompt(prompt_id)
        self._set_prompt_stage(None, None)

    def _write_prompt(self, prompt_id: str, timing: dict, stopped: float | None = None, engine: str | None = None, model: str | None = None, effort: str | None = None, adds: bool | None = None) -> None:
        self._set_prompt_stage(prompt_id, "writing")
        meta = prompts.load(prompt_id)
        try:
            attempt = prompts.write(meta, self.settings, engine, model, effort, self._track_prompt_process, adds)
        except notes_module.NotesError as exc:
            with self.lock:
                if self.prompt_cancelled:
                    self._end_cancelled_prompt(prompt_id)
                    return
                if self.closing:
                    return
                # Words aren't code, and you may be about to paste this somewhere that runs it. And the text you're proofreading is already yours.
                if prompts.is_code(meta) or prompts.is_proofread(meta):
                    self._set_prompt_stage(prompt_id, "failed", f"{exc} Your clipboard hasn't changed.")
                    return
                # Your own words are still better than nothing to paste.
                copied = self.clipboard.write(prompts.spoken_text(meta))
                ending = "Your words as spoken are on the clipboard instead." if copied else "Your words as spoken couldn't reach the clipboard either, so open it and copy them from there."
                self._set_prompt_stage(prompt_id, "failed", f"{exc} {ending}")
                return
        # The headline stays the first pass. Later attempts show their own time in the list.
        if stopped is not None or "write_seconds" not in timing:
            timing = dict(timing, write_seconds=attempt["seconds"])
        if stopped is not None:
            timing["total_seconds"] = round(time.perf_counter() - stopped, 1)
        # Cancel takes the same lock, so it lands before this, and nothing reaches your clipboard, or after it, when it's done.
        with self.lock:
            if self.prompt_cancelled:
                self._end_cancelled_prompt(prompt_id)
                return
            meta = prompts.update(
                prompt_id,
                attempts=meta["attempts"] + [attempt],
                prompt=attempt["prompt"],
                title=attempt["title"] or meta.get("title", ""),
                added=attempt["added"],
                suggestions=attempt["suggestions"],
                unsure=attempt["unsure"],
                language=attempt.get("language"),
                timing=timing,
            )
            self._finish_with_clipboard(prompt_id, meta)

    def _finish_with_clipboard(self, prompt_id: str, meta: dict) -> None:
        words = [item["word"] for item in prompts.checks(meta)]
        # Code's notes are on its page, and only what it can do gets in the way of pasting it, or that warning would come up all the time and stop meaning anything.
        count = len(words) + (0 if prompts.is_code(meta) else len(meta.get("unsure") or []))
        message = "" if self.clipboard.write(prompts.to_paste(meta)) else "It couldn't reach the clipboard. Open it and press Copy."
        about = _about_code(meta) if prompts.is_code(meta) else _about_edits(meta) if prompts.is_proofread(meta) else ""
        self._set_prompt_stage(prompt_id, "ready", message, count, len(meta.get("added") or []), words, about)

    def hear_prompt_again(self, prompt_id: str) -> None:
        """A prompt whose hearing failed, or that was cut off by quitting, from the audio it kept. Then it's written as usual."""
        with self.lock:
            if self.prompt_recorder or self.prompt_stage in ("hearing", "writing"):
                raise AppError("Wait for the prompt you're working on to finish.")
            if not storage.holds_audio(prompts.folder(prompt_id)):
                raise AppError("The audio for this prompt is gone.")
            self.prompt_cancelled = False
            self.prompt_second_try = True
            self.prompt_kind = prompts.load(prompt_id).get("kind", "prompt")
            self._set_prompt_stage(prompt_id, "hearing")
        threading.Thread(target=self._finish_prompt, args=(prompt_id, True, time.perf_counter()), daemon=True, name="prompt").start()

    def write_prompt_again(self, prompt_id: str, engine: str | None, model: str | None, effort: str | None, adds: bool | None = None) -> None:
        """Another attempt from the same words, kept beside the others."""
        with self.lock:
            if self.prompt_recorder or self.prompt_stage in ("hearing", "writing"):
                raise AppError("Wait for the prompt you're working on to finish.")
            meta = prompts.load(prompt_id)
            if not (prompts.original(meta) if prompts.is_proofread(meta) else prompts.spoken_text(meta)).strip():
                raise AppError("There's nothing to write from.")
            self.prompt_cancelled = False
            self.prompt_second_try = True
            self.prompt_kind = meta.get("kind", "prompt")
            self._set_prompt_stage(prompt_id, "writing")
        self._write_on_its_own_thread(prompt_id, engine, model, effort, adds)

    def _write_on_its_own_thread(self, prompt_id: str, engine: str | None = None, model: str | None = None, effort: str | None = None, adds: bool | None = None) -> None:
        def work():
            try:
                self._write_prompt(prompt_id, prompts.load(prompt_id).get("timing") or {}, None, engine, model, effort, adds)
            except Exception as exc:
                log.exception("Writing failed: %s", prompt_id)
                self._set_prompt_stage(prompt_id, "failed", str(exc))

        threading.Thread(target=work, daemon=True, name="prompt").start()

    def copy_prompt(self, prompt_id: str) -> bool:
        return self.clipboard.write(prompts.to_paste(prompts.load(prompt_id)))

    def forget_prompt(self, prompt_id: str) -> None:
        """It's been deleted, so the bar can't go on asking you to check it or offering to show it."""
        with self.lock:
            if prompt_id == self.prompt_id and not self.prompt_recorder:
                self._set_prompt_stage(None, None)

    def show_prompt_in_window(self, prompt_id: str | None) -> None:
        self.prompt_shows += 1
        self.prompt_id = prompt_id or self.prompt_id

    # ------------------------------------------------------------- state

    def low_key(self) -> bool:
        return self.settings["on_screen"] != "bar"

    def moves(self) -> bool:
        """Low key is about not catching the eye, so nothing moves in it, whatever Let things move says."""
        return bool(self.settings["motion"]) and not self.low_key()

    def snapshot(self) -> dict:
        recorder, meeting_id = self.recorder, self.recording_id
        recording = {"active": False}
        if recorder and meeting_id:
            recording = dict(recorder.status(), active=True, meeting_id=meeting_id, mode=self.recording_mode)
        test = None
        if self.audio_test:
            status = self.audio_test.status()
            test = {
                "levels": status["levels"],
                "devices": status["devices"],
                "heard": {
                    "mic": self.audio_test.mic.sound_seconds > 0.3,
                    "system": self.audio_test.system.sound_seconds > 0.3,
                },
            }
        clip, clip_id = self.model_test, self.model_test_id
        listening = self.prompt_recorder
        return {
            "recording": recording,
            "audio_test": test,
            "prompt": {
                "recording": listening.status() if listening else None,
                "id": self.prompt_id,
                "stage": self.prompt_stage,
                "kind": self.prompt_kind,
                "about": self.prompt_about,
                "message": self.prompt_message,
                "check": self.prompt_check,
                "check_words": self.prompt_check_words,
                "added": self.prompt_added,
                "copied": self.prompt_copied,
                "latest_copy": self.prompt_latest_copy,
                "copy_flashes": self.prompt_copy_flashes,
                "check_first": self.settings["prompt_check_first"],
                "version": self.prompt_version,
                "shows": self.prompt_shows,
            },
            "model_test": {
                "recording": dict(clip.status(), id=clip_id) if clip and clip_id else None,
                "current": self.current_test,
                "progress": self.test_progress,
                "version": self.test_version,
            },
            "jobs": {"current": self.current_job, "queued": list(self.queued), "progress": dict(self.progress)},
            "version": self.version,
            "hotkey": self.settings["hotkey"],
            "hotkey_solo": self.settings["hotkey_solo"],
            "hotkey_prompt": self.settings["hotkey_prompt"],
            "hotkey_code": self.settings["hotkey_code"],
            "hotkey_proofread": self.settings["hotkey_proofread"],
            "hotkey_proofread_text": self.settings["hotkey_proofread_text"],
            "hotkey_errors": self.hotkey_errors,
            "look": {"theme": self.settings["theme"], "motion": self.moves()},
            "bar": {"on_screen": self.settings["on_screen"], "opened_up": self.bar_opened_up},
            "alerts": self.alert_flashes,
            "deleted_recording": self.deleted_recording,
            "recycled_recording": self.recycled_recording,
            "unsaved_failures": dict(self.unsaved_failures),
        }

    def devices(self) -> dict:
        """While recording, PortAudio can't be restarted, so the last list is shown."""
        if not self.recorder and not self.audio_test and not self.model_test and not self.prompt_recorder:
            try:
                self.devices_cache = list_devices()
            except AudioStuck as exc:
                if self.devices_cache is None:
                    raise AppError(str(exc)) from exc
        devices = dict(self.devices_cache or {"mics": [], "outputs": [], "default_mic": None, "default_output": None})
        saved = self.settings["mic_device"]
        selected = "default"
        if saved != "default":
            selected = next((m for m in devices["mics"] if device_key(m) == device_key(saved)), saved)
            if selected not in devices["mics"]:
                devices["mics"] = devices["mics"] + [selected]
                devices["mic_missing"] = True
        devices["selected_mic"] = selected
        saved_out = self.settings["output_device"]
        selected_out = "all"
        if saved_out != "all":
            selected_out = next((o for o in devices["outputs"] if device_key(o) == device_key(saved_out)), saved_out)
            if selected_out not in devices["outputs"]:
                devices["outputs"] = devices["outputs"] + [selected_out]
        devices["selected_output"] = selected_out
        return devices

    def update_settings(self, patch: dict) -> dict:
        with self.lock:
            self.settings = save_settings(patch)
        self._emit("settings_changed", patch=patch)
        return self.settings

    # ------------------------------------------------------------- jobs

    def _enqueue(self, meeting_id: str, start: str) -> None:
        self.queued.append(meeting_id)
        self.progress[meeting_id] = {"stage": "queued", "fraction": 0.0, "started": time.time()}
        self.queue.put((meeting_id, start))
        self.bump()

    def process(self, meeting_id: str, start: str, engine: str | None = None) -> None:
        with self.lock:
            if meeting_id == self.recording_id:
                raise AppError("That meeting is still recording.")
            if meeting_id == self.current_job or meeting_id in self.queued:
                raise AppError("That meeting is already being processed.")
            if start == "notes" and not storage.load_transcript(meeting_id):
                raise AppError("There's no transcript to write notes from.")
            if start != "notes" and not (storage.audio_path(meeting_id) or storage.has_raw_audio(meeting_id)):
                raise AppError("The audio for this meeting has been deleted.")
            status = "notes" if start == "notes" else "saving"
            if start == "compare":
                # Tried alongside what's there: the current transcript and notes stay exactly as they are.
                storage.file_existing_transcript(meeting_id)
                storage.update_meta(meeting_id, prior_status=storage.load_meta(meeting_id)["status"], compare_engine=engine)
            storage.update_meta(meeting_id, status=status, error=None, failed_stage=None, save_only=start == "save")
            self.cancelled.discard(meeting_id)
            self._enqueue(meeting_id, start)

    def cancel(self, meeting_id: str) -> None:
        with self.lock:
            self.cancelled.add(meeting_id)
            if meeting_id == self.current_job and self.current_process:
                _kill_tree(self.current_process)

    def _job_loop(self) -> None:
        while True:
            meeting_id, start = self.queue.get()
            if meeting_id is None:
                return
            # This is the only thread that runs jobs, so whatever goes wrong with one, the next still gets its turn.
            try:
                if start == "model_test":
                    self._run_model_test(meeting_id)
                else:
                    self._run_job(meeting_id, start)
            except Exception:
                log.exception("A job ended badly: %s", meeting_id)

    def _run_job(self, meeting_id: str, start: str) -> None:
        if meeting_id in self.queued:
            self.queued.remove(meeting_id)
        self.current_job = meeting_id
        title = "Meeting"
        try:
            title = storage.load_meta(meeting_id)["title"]
            if meeting_id in self.cancelled:
                raise JobFailed(start, "Stopped.")
            self._process(meeting_id, start)
        except JobFailed as exc:
            if self.closing:
                log.info("Left %s to finish on the next start", meeting_id)
            elif start == "compare":
                log.warning("Trying another model failed for %s: %s", meeting_id, exc.message)
                self._end_compare(meeting_id, None if meeting_id in self.cancelled else exc.message)
            else:
                log.warning("Job failed for %s at %s: %s", meeting_id, exc.stage, exc.message)
                self._job_failed(meeting_id, exc.stage, exc.message, title)
        except Exception as exc:
            log.exception("Job crashed for %s", meeting_id)
            self._job_failed(meeting_id, start, str(exc), title)
        finally:
            self.current_job = None
            self.current_process = None
            self.progress.pop(meeting_id, None)
            self.cancelled.discard(meeting_id)
            self.bump()

    def _job_failed(self, meeting_id: str, stage: str, message: str, title: str) -> None:
        """This writes to the same disk that may just have failed, so if it can't be saved, the windows and the tray still get told."""
        stopped = meeting_id in self.cancelled
        message = "Stopped." if stopped else message
        try:
            storage.update_meta(meeting_id, status="failed", error=message, failed_stage=stage)
        except Exception:
            log.exception("Couldn't save that %s failed", meeting_id)
            self.unsaved_failures[meeting_id] = f"{title}: {message}"
        if not stopped:
            self._emit("job_failed", meeting_id=meeting_id, title=title, message=message)

    def _end_compare(self, meeting_id: str, problem: str | None = None) -> None:
        meta = storage.load_meta(meeting_id)
        warnings = meta.get("warnings", []) + ([problem] if problem else [])
        storage.update_meta(meeting_id, status=meta.get("prior_status") or "done", prior_status=None, compare_engine=None, warnings=warnings)

    def _process(self, meeting_id: str, start: str) -> None:
        if start == "compare":
            self._transcribe(meeting_id, storage.load_meta(meeting_id).get("compare_engine"), compare=True)
            self._end_compare(meeting_id)
            self._emit("notes_ready", meeting_id=meeting_id, title=storage.load_meta(meeting_id)["title"], message="Another transcript is ready to compare.")
            return
        if start in ("save", "discard"):
            # Saved first even when it's being deleted, so what lands in the Recycle Bin can still be played.
            storage.finalize_audio(storage.folder(meeting_id))
            storage.update_meta(meeting_id, status="saved", discard=False)
            if start == "discard":
                try:
                    storage.delete_meeting(meeting_id)
                except OSError as exc:
                    raise JobFailed("save", f"This recording was saved, but it couldn't go to the Recycle Bin: {exc}") from exc
                self.recycled_recording = meeting_id
                self._emit("recording_recycled", meeting_id=meeting_id)
            return
        if start == "transcribe":
            self._transcribe(meeting_id)
        # A cancel can arrive between stages, when there's no process for it to stop. Nothing goes to the notes engine after that.
        if self.closing:
            return
        if meeting_id in self.cancelled:
            self._job_failed(meeting_id, "notes", "Stopped.", "")
            return
        lines = storage.load_transcript(meeting_id)
        if not lines:
            meta = storage.update_meta(meeting_id, status="done")
            self._emit("notes_ready", meeting_id=meeting_id, title=meta["title"], message="No speech was found.")
            return
        if self.settings["notes_engine"] == "none":
            meta = storage.update_meta(meeting_id, status="done")
            self._emit("notes_ready", meeting_id=meeting_id, title=meta["title"], message="Transcript ready.")
            return
        self._write_notes(meeting_id, lines)

    def _track_job_process(self, process) -> bool:
        """Says whether to go on. A cancel can arrive while a process is starting, when there's nothing yet for it to stop."""
        self.current_process = process
        if process and (self.closing or self.current_job in self.cancelled or self.current_test in self.cancelled):
            _kill_tree(process)
            return False
        return True

    def _run_worker(self, path: Path, engine: str, language: str, speakers: bool, compare: bool, on_event, hint: str = "meeting", mic_only: bool = False, extra_terms=(), on_process=None, held: subprocess.Popen | None = None) -> tuple[int, str | None]:
        """One transcription, as its own process, or by the one in held if it's still there. Returns its exit code and the error it reported, if any."""
        on_process = on_process or self._track_job_process
        model = find_whisper_model(self.settings)
        model_dir = ROOT / "models"
        model_dir.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as terms:
            terms.write("\n".join([self.settings["terms"], *extra_terms]))
        command = [
            _python(),
            "-m",
            "brushtalk.worker",
            str(path),
            "--model",
            model or MODEL_NAME,
            "--download-root",
            str(model_dir),
            "--language",
            language,
            "--chinese",
            self.settings["chinese_script"],
            "--compute",
            self.settings["compute"],
            "--terms-file",
            terms.name,
            "--engine",
            engine,
            "--hint",
            hint,
        ]
        if speakers:
            command.append("--speakers")
        if compare:
            command.append("--compare")
        if mic_only:
            command.append("--mic-only")
        log_path = path / "worker.log"
        try:
            code, error, finished = self._use_held(held, command[3:], on_event, on_process) if held else (0, None, False)
            # A process that was waiting can have gone in the meantime, and then this is done the usual way.
            if not finished and not error and not (held and self.prompt_cancelled):
                with open(log_path, "w", encoding="utf-8") as stderr:
                    process = subprocess.Popen(
                        command,
                        cwd=str(ROOT),
                        stdout=subprocess.PIPE,
                        stderr=stderr,
                        encoding="utf-8",
                        errors="replace",
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    on_process(process)
                    code, error, _ = _follow(process, on_event)
        finally:
            Path(terms.name).unlink(missing_ok=True)
        on_process(None)
        if code == 0:
            log_path.unlink(missing_ok=True)
        return code, error

    def _use_held(self, process: subprocess.Popen, arguments: list[str], on_event, on_process) -> tuple[int, str | None, bool]:
        try:
            if process.poll() is not None:
                return process.returncode, None, False
            process.stdin.write(json.dumps(arguments) + "\n")
            process.stdin.close()
        except OSError:
            return 1, None, False
        on_process(process)
        return _follow(process, on_event)

    def _transcribe(self, meeting_id: str, engine: str | None = None, compare: bool = False) -> None:
        path = storage.folder(meeting_id)
        if not find_whisper_model(self.settings):
            self.progress[meeting_id] = {"stage": "loading", "fraction": 0.0, "note": "Downloading the speech model, about 1.6 GB, the first time only."}
        self.progress[meeting_id] = dict(self.progress.get(meeting_id, {}), stage="saving", fraction=0.0)
        solo = storage.load_meta(meeting_id).get("mode") == "solo"
        code, error = self._run_worker(
            path,
            engine or self.settings["speech_engine"],
            self.settings["language"],
            self.settings["speakers"],
            compare,
            lambda event: self._on_worker_event(meeting_id, event, compare),
            hint="talking" if solo else "meeting",
            mic_only=solo,
        )
        if code != 0:
            raise JobFailed("transcribe", error or "Transcription stopped unexpectedly. Press Try again.")

    def _on_worker_event(self, meeting_id: str, event: dict, compare: bool = False) -> None:
        current = dict(self.progress.get(meeting_id, {}))
        stage = event.get("stage")
        if stage == "saving":
            storage.update_meta(meeting_id, status="saving")
            current.update(stage="saving", fraction=0.0)
        elif stage == "loading":
            storage.update_meta(meeting_id, status="transcribing")
            current.update(stage="loading", fraction=0.0)
        elif stage == "transcribing":
            current.update(stage="transcribing", fraction=event.get("fraction", 0.0), track=event.get("track"))
        if "duration" in event:
            storage.update_meta(meeting_id, duration=event["duration"])
            self.bump()
        if "device" in event:
            current["device"] = event["device"]
            if not compare:
                storage.update_meta(meeting_id, compute_device=event["device"])
        if "engine_label" in event:
            storage.update_meta(meeting_id, transcribed_with=event["engine_label"], transcript_engine=event["engine"])
        if "version" in event and not compare:
            storage.update_meta(meeting_id, transcript_version=event["version"])
        if event.get("hint"):
            current["note"] = event["hint"]
        if event.get("note"):
            current["note"] = event["note"]
            self._add_warning(meeting_id, event["note"])
        for warning in event.get("warnings", []):
            self._add_warning(meeting_id, warning)
        self.progress[meeting_id] = current

    def _add_warning(self, meeting_id: str, text: str) -> None:
        meta = storage.load_meta(meeting_id)
        if text not in meta.get("warnings", []):
            storage.update_meta(meeting_id, warnings=meta.get("warnings", []) + [text])

    def _write_notes(self, meeting_id: str, lines: list[dict]) -> None:
        meta = storage.update_meta(meeting_id, status="notes")
        self.progress[meeting_id] = {"stage": "notes", "fraction": 0.0, "started": time.time()}
        self.bump()

        title = meta["title"] if meta.get("title_source") == "user" else ""
        try:
            result = notes_module.generate(with_names(lines, meta.get("speaker_names")), self.settings, title, self._track_job_process, meta.get("mode", "meeting"))
        except notes_module.NotesError as exc:
            raise JobFailed("notes", str(exc)) from exc
        path = storage.folder(meeting_id)
        storage.file_existing_notes(meeting_id)
        storage.keep_original(
            meeting_id, result["markdown"], result["raw"], engine=result["engine"], model=result["model"], effort=result["effort"]
        )
        if (path / "notes.md").exists():
            shutil.copyfile(path / "notes.md", path / "notes.previous.md")
        storage.save_notes(meeting_id, result["markdown"])
        changes = {
            "status": "done",
            "notes_engine": result["engine"],
            "notes_model": result["model"],
            "notes_effort": result["effort"],
            "unverified": result["unverified"],
            "notes_edited": False,
            "notes_stale": False,
            # So that after Just switch to another transcript, the page can say these came from the one before.
            "notes_from": meta.get("transcript_version"),
        }
        if meta.get("title_source") != "user" and result["title"]:
            changes.update(title=result["title"], title_source="notes")
        meta = storage.update_meta(meeting_id, **changes)
        log.info("Notes written for %s by %s", meeting_id, result["engine"])
        self._emit("notes_ready", meeting_id=meeting_id, title=meta["title"], message="Your notes are ready.")

    def recover(self) -> None:
        """Pick up after a crash or a quit: nothing that reached the disk gets lost. One item that can't be picked up doesn't stop the others, or the app opening."""
        self.unsaved_failures.update(modeltests.recover())
        self.unsaved_failures.update(prompts.recover())
        for meta in storage.list_meetings():
            try:
                self._recover_meeting(meta)
            except Exception as exc:
                log.exception("Couldn't pick up %s", meta["id"])
                self.unsaved_failures[meta["id"]] = f"{meta.get('title', 'A recording')} couldn't be picked up after the app closed, but its files are still there: {exc}"

    def _recover_meeting(self, meta: dict) -> None:
        meeting_id, status = meta["id"], meta.get("status")
        if status == "recording":
            path = storage.folder(meeting_id)
            if storage.audio_path(meeting_id) and not storage.has_raw_audio(meeting_id):
                # It stopped and saved properly, and only this file never heard, because the disk was failing at the time. What happens next is up to you.
                storage.update_meta(meeting_id, status="saved", save_only=True, duration=round(storage.saved_seconds(path), 2))
                return
            duration = storage.raw_seconds(path)
            if duration < 1 and not storage.has_saved_work(path):
                # Started and died straight away: nothing worth keeping.
                shutil.rmtree(path, ignore_errors=True)
                return
            note = "This recording was cut off by a crash or shutdown. Everything up to that point was saved."
            after = self.settings["after_stop"]
            storage.update_meta(
                meeting_id,
                status="saving",
                save_only=after != "notes",
                duration=round(duration, 2),
                warnings=meta.get("warnings", []) + [note],
            )
            log.info("Recovered interrupted recording %s, %.0f s", meeting_id, duration)
            self._enqueue(meeting_id, FIRST_JOB[after])
        elif status in ("saving", "transcribing") and meta.get("compare_engine"):
            self._end_compare(meeting_id)
        elif status in ("saving", "transcribing"):
            self._enqueue(meeting_id, "discard" if meta.get("discard") else "save" if meta.get("save_only") else "transcribe")
        elif status == "notes":
            self._enqueue(meeting_id, "notes")

    def shutdown(self) -> None:
        """Stop recording cleanly. Unfinished jobs carry on at the next start, and only Cancel ever throws a prompt away."""
        self.closing = True
        self.stop_audio_test()
        self.drop_model_test()
        self._set_prompt_aside()
        # Cancelled already: quitting before the time to undo is up doesn't keep it.
        self._forget_cancelled()
        if self.recorder:
            try:
                self.stop_recording()
            except Exception:
                log.exception("Stopping the recording on exit failed")
        with self.lock:
            if self.current_process:
                _kill_tree(self.current_process)


def _about_code(meta: dict) -> str:
    """What the bar says about it, as a last check that it's what you expected, since you may paste it without looking."""
    lines = meta.get("prompt", "").count("\n") + 1
    notes = len(meta.get("unsure") or [])
    about = f"{lines} {'line' if lines == 1 else 'lines'}"
    if meta.get("language"):
        about = f"{meta['language']}, {about}"
    return f"{about} · {notes} {'note' if notes == 1 else 'notes'}" if notes else about


def _about_edits(meta: dict) -> str:
    """So that when nothing changed you know it's because nothing needed to. Only the very same text gets that: a change the count can't
    see, such as spacing, still says it was edited."""
    before, after = prompts.original(meta), meta.get("prompt", "")
    if before == after:
        return "No changes needed"
    made = prompts.edits_made(before, after)
    return f"{made} {'edit' if made == 1 else 'edits'}" if made else "Edited"


def _everything_to_say(recorder: Recorder, stats: dict) -> list[str]:
    """The recording's warnings, with anything still wrong when it stopped, so that doesn't vanish with the recorder."""
    warnings = list(stats["notices"])
    error = getattr(recorder, "error", None)
    if isinstance(error, str) and error not in warnings:
        warnings.append(error)
    return warnings


def _follow(process: subprocess.Popen, on_event) -> tuple[int, str | None, bool]:
    """Passes on what a worker reports until it's done. Returns its exit code, the error it reported, and whether it finished."""
    error, finished = None, False
    for raw in process.stdout:
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        error = event.get("error", error)
        finished = finished or event.get("stage") == "done"
        on_event(event)
    return process.wait(), error, finished


def _python() -> str:
    """python.exe rather than pythonw.exe, so the worker has a real stdout to report through."""
    exe = Path(sys.executable)
    candidate = exe.with_name("python.exe")
    return str(candidate if candidate.exists() else exe)


_kill_tree = notes_module.kill_tree
