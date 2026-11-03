"""Local web server behind the window. It only answers on 127.0.0.1, and only with this run's token."""
from __future__ import annotations

import asyncio
import html
import logging
import os
import shutil
import subprocess
from datetime import date
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from . import __version__, checks, engines, instructions, modeltests, notes, overview, prompts, storage
from .config import LOG_DIR, UI_DIR, write_text_safely
from .controller import AppError, Controller
from .transcript import with_names

log = logging.getLogger(__name__)

CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "media-src 'self'; connect-src 'self' ws://127.0.0.1:*; font-src 'self'; base-uri 'none'; form-action 'none'"
)


def _meeting_or_404(meeting_id: str) -> dict:
    try:
        return storage.load_meta(meeting_id)
    except (ValueError, OSError) as exc:
        raise HTTPException(404, "That meeting doesn't exist.") from exc


def _test_or_404(test_id: str) -> dict:
    try:
        return modeltests.load(test_id)
    except (ValueError, OSError) as exc:
        raise HTTPException(404, "That test doesn't exist.") from exc


def _prompt_or_404(prompt_id: str) -> dict:
    try:
        return prompts.load(prompt_id)
    except (ValueError, OSError) as exc:
        raise HTTPException(404, "That prompt doesn't exist.") from exc


def _with_playback_gain(meeting_id: str, meta: dict) -> dict:
    """Worked out once per recording, the first time it's opened."""
    path = storage.audio_path(meeting_id)
    if not path or "playback_gain" in meta:
        return meta
    try:
        return storage.update_meta(meeting_id, playback_gain=storage.playback_gains(path))
    except (OSError, RuntimeError, ValueError):
        log.exception("Couldn't measure the audio for %s", meeting_id)
        return meta


def create_app(controller: Controller, token: str, port: int, desktop=None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Guard(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # A web page in any browser can reach localhost. The host check stops DNS rebinding,
            # and the token stops everything else from touching recordings.
            if request.headers.get("host") not in allowed_hosts:
                return PlainTextResponse("Forbidden", status_code=403)
            if request.url.path.startswith("/api/"):
                supplied = request.headers.get("x-token") or request.query_params.get("token")
                if supplied != token:
                    return JSONResponse({"detail": "Not allowed."}, status_code=401)
            response = await call_next(request)
            response.headers["Content-Security-Policy"] = CSP
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Content-Type-Options"] = "nosniff"
            if not request.url.path.endswith("/audio"):
                response.headers["Cache-Control"] = "no-store"
            return response

    app.add_middleware(Guard)

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(OSError)
    async def disk_error(request: Request, exc: OSError):
        # Most likely a full or failing disk, and the person typing needs to know their words weren't saved.
        log.exception("Couldn't do %s", request.url.path)
        return JSONResponse({"detail": f"That couldn't be saved: {exc}"}, status_code=500)

    # ------------------------------------------------------------- pages

    def page(name: str) -> HTMLResponse:
        """The page with your look written into it, so a window opens in the right colours from its first moment."""
        settings = controller.settings
        choice = f'<html lang="en" data-look-theme="{html.escape(str(settings["theme"]), quote=True)}" data-look-motion="{"on" if controller.moves() else "off"}">'
        return HTMLResponse((UI_DIR / name).read_text(encoding="utf-8").replace('<html lang="en">', choice, 1))

    @app.get("/")
    def index():
        return page("index.html")

    @app.get("/mini")
    def mini():
        return page("mini.html")

    app.mount("/static", StaticFiles(directory=UI_DIR), name="static")

    # ------------------------------------------------------------- recording

    @app.get("/api/state")
    def state():
        return controller.snapshot()

    @app.post("/api/recording/start")
    def start(body: dict = Body(default={})):
        return controller.start_recording(str(body.get("title", "")), "solo" if body.get("mode") == "solo" else "meeting")

    @app.post("/api/recording/stop")
    def stop(body: dict = Body(default={})):
        return {"meeting_id": controller.stop_recording(body.get("after"))}

    @app.post("/api/recording/pause")
    def pause():
        controller.pause()
        return {"ok": True}

    @app.post("/api/recording/resume")
    def resume():
        controller.resume()
        return {"ok": True}

    # ------------------------------------------------------------- meetings

    @app.get("/api/meetings")
    def meetings(q: str = ""):
        return storage.list_meetings(q)

    @app.get("/api/meetings/{meeting_id}")
    def meeting(meeting_id: str):
        meta = _with_playback_gain(meeting_id, _meeting_or_404(meeting_id))
        return {
            "meta": meta,
            "notes": storage.load_notes(meeting_id),
            "my_notes": storage.load_my_notes(meeting_id),
            "originals": storage.list_originals(meeting_id),
            "transcript": storage.load_transcript(meeting_id),
            "transcripts": storage.list_transcript_versions(meeting_id),
            "has_audio": storage.audio_path(meeting_id) is not None,
        }

    @app.patch("/api/meetings/{meeting_id}")
    def patch_meeting(meeting_id: str, body: dict = Body(...)):
        _meeting_or_404(meeting_id)
        changes = {}
        if "title" in body:
            title = str(body["title"]).strip()
            if not title:
                raise HTTPException(400, "A meeting needs a name.")
            changes.update(title=title[:200], title_source="user")
        if "notes" in body:
            storage.file_existing_notes(meeting_id)
            storage.save_notes(meeting_id, str(body["notes"]))
            if body.get("edited", True):
                changes["notes_edited"] = True
        if "my_notes" in body:
            storage.save_my_notes(meeting_id, str(body["my_notes"]))
        if "speaker_names" in body:
            names = {str(key): str(value).strip()[:80] for key, value in dict(body["speaker_names"]).items() if str(value).strip()}
            changes["speaker_names"] = names
        meta = storage.update_meta(meeting_id, **changes) if changes else storage.load_meta(meeting_id)
        if set(body) != {"my_notes"}:
            controller.bump()
        return meta

    @app.get("/api/meetings/{meeting_id}/transcripts/{name}")
    def transcript_version(meeting_id: str, name: str):
        _meeting_or_404(meeting_id)
        try:
            return storage.load_transcript_version(meeting_id, name)
        except (ValueError, OSError) as exc:
            raise HTTPException(404, "That version doesn't exist.") from exc

    @app.post("/api/meetings/{meeting_id}/transcripts/{name}/use")
    def use_transcript_version(meeting_id: str, name: str):
        _meeting_or_404(meeting_id)
        if meeting_id == controller.current_job or meeting_id in controller.queued:
            raise HTTPException(409, "Wait for this meeting to finish processing.")
        try:
            version = storage.load_transcript_version(meeting_id, name)
        except (ValueError, OSError) as exc:
            raise HTTPException(404, "That version doesn't exist.") from exc
        storage.write_transcript(meeting_id, version["lines"])
        meta = storage.update_meta(
            meeting_id,
            transcript_version=name,
            transcribed_with=version.get("label"),
            transcript_engine=version.get("engine"),
            speaker_names={},
        )
        controller.bump()
        return meta

    @app.get("/api/engines")
    def get_engines():
        return {"engines": engines.available(), "has_diarizer": engines.diarizer() is not None}

    @app.get("/api/overview")
    def get_overview():
        return overview.overview()

    @app.post("/api/meetings/{meeting_id}/task")
    def set_task(meeting_id: str, body: dict = Body(...)):
        _meeting_or_404(meeting_id)
        if not overview.set_task(meeting_id, int(body["line"]), str(body["raw"]), bool(body["done"])):
            raise HTTPException(409, "Those notes have changed. Open the meeting to tick it there.")
        controller.bump()
        return {"ok": True}

    @app.get("/api/meetings/{meeting_id}/originals/{name}")
    def original(meeting_id: str, name: str):
        _meeting_or_404(meeting_id)
        try:
            return {"text": storage.load_original(meeting_id, name)}
        except (ValueError, OSError) as exc:
            raise HTTPException(404, "That version doesn't exist.") from exc

    @app.post("/api/meetings/{meeting_id}/originals/{name}/restore")
    def restore_original(meeting_id: str, name: str):
        meta = _meeting_or_404(meeting_id)
        if meeting_id == controller.current_job or meeting_id in controller.queued:
            raise HTTPException(409, "Wait for this meeting to finish processing.")
        try:
            text = storage.load_original(meeting_id, name)
        except (ValueError, OSError) as exc:
            raise HTTPException(404, "That version doesn't exist.") from exc
        current = storage.load_notes(meeting_id)
        if current is not None:
            write_text_safely(storage.folder(meeting_id) / "notes.previous.md", current)
        storage.save_notes(meeting_id, text)
        meta = storage.update_meta(meeting_id, notes_edited=False, unverified=text.count("[unverified]"))
        controller.bump()
        return meta

    @app.delete("/api/meetings/{meeting_id}")
    def delete_meeting(meeting_id: str):
        _meeting_or_404(meeting_id)
        if meeting_id == controller.recording_id:
            raise HTTPException(409, "Stop recording first.")
        if meeting_id == controller.current_job or meeting_id in controller.queued:
            raise HTTPException(409, "Wait for this meeting to finish processing, or stop it first.")
        storage.delete_meeting(meeting_id)
        controller.bump()
        return {"ok": True}

    @app.get("/api/storage")
    def storage_use():
        """What the recordings take, for Settings."""
        folders = lambda root: [path for path in root.iterdir() if path.is_dir()] if root.exists() else []
        root = storage.meetings_dir()
        return {
            "meetings": storage.audio_use(folders(root)),
            "prompts": storage.audio_use(folders(prompts.prompts_dir())),
            "tests": storage.audio_use(folders(modeltests.tests_dir())),
            "drive": root.anchor.rstrip("\\") or str(root),
            "free": shutil.disk_usage(root).free,
        }

    @app.post("/api/old-audio")
    def old_audio(body: dict = Body(...)):
        """How much meeting audio is older than so many months, and with delete, that audio goes to the Recycle Bin. The transcripts and
        notes stay, and a meeting being recorded or worked on is left alone."""
        months = body.get("months")
        if not isinstance(months, int) or isinstance(months, bool) or months < 1:
            raise HTTPException(400, "Choose how many months.")
        busy = {controller.current_job, controller.recording_id, *controller.queued}
        found = [item for item in storage.old_audio(months) if item["id"] not in busy]
        if body.get("delete"):
            for item in found:
                storage.delete_audio(item["id"])
            controller.bump()
        return {"count": len(found), "bytes": sum(item["bytes"] for item in found), "before": storage.months_before(date.today(), months).isoformat()}

    @app.post("/api/meetings/{meeting_id}/delete-audio")
    def delete_audio(meeting_id: str):
        _meeting_or_404(meeting_id)
        if meeting_id == controller.current_job:
            raise HTTPException(409, "Wait for this meeting to finish processing.")
        storage.delete_audio(meeting_id)
        controller.bump()
        return {"ok": True}

    @app.post("/api/meetings/{meeting_id}/process")
    def process(meeting_id: str, body: dict = Body(...)):
        _meeting_or_404(meeting_id)
        start = body.get("from")
        if start not in ("save", "transcribe", "notes", "compare"):
            raise HTTPException(400, "Unknown step.")
        controller.process(meeting_id, start, body.get("engine"))
        return {"ok": True}

    @app.post("/api/meetings/{meeting_id}/cancel")
    def cancel(meeting_id: str):
        controller.cancel(meeting_id)
        return {"ok": True}

    @app.post("/api/meetings/{meeting_id}/reveal")
    def reveal(meeting_id: str):
        _meeting_or_404(meeting_id)
        subprocess.Popen(["explorer", str(storage.folder(meeting_id))])
        return {"ok": True}

    @app.get("/api/meetings/{meeting_id}/audio")
    def audio(meeting_id: str):
        _meeting_or_404(meeting_id)
        path = storage.audio_path(meeting_id)
        if not path:
            raise HTTPException(404, "There's no audio for this meeting.")
        return FileResponse(path, media_type="audio/flac")

    @app.get("/api/meetings/{meeting_id}/prompt")
    def prompt(meeting_id: str):
        _meeting_or_404(meeting_id)
        settings = controller.settings
        meta = storage.load_meta(meeting_id)
        lines = with_names(storage.load_transcript(meeting_id), meta.get("speaker_names"))
        return {"prompt": notes.build_prompt(lines, settings["terms"], settings["extra_instructions"], language=settings["notes_language"], script=settings["chinese_script"], mode=meta.get("mode", "meeting"))}

    # ------------------------------------------------------------- model tests

    @app.get("/api/model-tests")
    def model_tests():
        return {"tests": modeltests.summaries(), "scores": modeltests.scoreboard(), "engines": engines.available()}

    @app.post("/api/model-tests/start")
    def model_test_start(body: dict = Body(default={})):
        language = body.get("language")
        if language not in modeltests.LANGUAGES:
            raise HTTPException(400, "Unknown language.")
        return controller.start_model_test(language, body.get("hint") if body.get("hint") in modeltests.HINTS else "talking")

    @app.post("/api/model-tests/stop")
    def model_test_stop():
        return {"id": controller.stop_model_test()}

    @app.post("/api/model-tests/discard")
    def model_test_discard():
        controller.drop_model_test()
        return {"ok": True}

    @app.get("/api/model-tests/{test_id}")
    def model_test(test_id: str):
        _test_or_404(test_id)
        return modeltests.detail(test_id)

    @app.post("/api/model-tests/{test_id}/score")
    def model_test_score(test_id: str, body: dict = Body(...)):
        meta = _test_or_404(test_id)
        index, score = body.get("run"), body.get("score")
        if not isinstance(index, int) or not 0 <= index < len(meta["runs"]) or score not in (None, 1, 2, 3, 4, 5):
            raise HTTPException(400, "Unknown run or score.")
        return modeltests.update_run(test_id, index, score=score)

    @app.post("/api/model-tests/{test_id}/run")
    def model_test_run(test_id: str, body: dict = Body(...)):
        _test_or_404(test_id)
        language = body.get("language")
        if language not in modeltests.LANGUAGES:
            raise HTTPException(400, "Unknown language.")
        controller.run_model_test_again(test_id, language, body.get("hint") if body.get("hint") in modeltests.HINTS else "talking")
        return {"ok": True}

    @app.post("/api/model-tests/{test_id}/cancel")
    def model_test_cancel(test_id: str):
        _test_or_404(test_id)
        controller.cancel_model_test(test_id)
        return {"ok": True}

    @app.delete("/api/model-tests/{test_id}")
    def model_test_delete(test_id: str):
        if modeltests.is_busy(_test_or_404(test_id)):
            raise HTTPException(409, "Wait for the models to finish, or stop them first.")
        modeltests.delete(test_id)
        return {"ok": True}

    @app.get("/api/model-tests/{test_id}/audio")
    def model_test_audio(test_id: str):
        _test_or_404(test_id)
        path = modeltests.audio_path(test_id)
        if not path:
            raise HTTPException(404, "There's no audio for this test.")
        return FileResponse(path, media_type="audio/flac")

    # ------------------------------------------------------------- prompts

    @app.get("/api/prompts")
    def get_prompts():
        # One you've just cancelled is only waiting to be brought back or to go, so it isn't listed.
        return {"prompts": [item for item in prompts.list_prompts() if item["status"] != "cancelled"]}

    @app.post("/api/prompts/start")
    def prompt_start(body: dict = Body(default={})):
        return controller.start_prompt(str(body.get("typed", "")), body.get("kind") if body.get("kind") in ("code", "proofread") else "prompt")

    @app.post("/api/proofread")
    def proofread(body: dict = Body(default={})):
        return controller.proofread(str(body.get("text", "")))

    @app.post("/api/prompts/stop")
    def prompt_stop():
        return {"id": controller.stop_prompt()}

    @app.post("/api/prompts/pause")
    def prompt_pause():
        controller.pause_prompt()
        return {"ok": True}

    @app.post("/api/prompts/resume")
    def prompt_resume():
        controller.resume_prompt()
        return {"ok": True}

    @app.post("/api/prompts/cancel")
    def prompt_cancel():
        controller.drop_prompt()
        return {"ok": True}

    @app.post("/api/prompts/undo-cancel")
    def prompt_undo_cancel():
        return {"id": controller.undo_cancel()["id"]}

    @app.post("/api/prompts/typed")
    def prompt_typed(body: dict = Body(...)):
        controller.set_prompt_typed(str(body.get("text", "")), str(body.get("id", "")))
        return {"ok": True}

    @app.post("/api/prompts/undo-copy")
    def prompt_undo_copy(body: dict = Body(...)):
        prompt_id = str(body.get("id", ""))
        _prompt_or_404(prompt_id)
        controller.undo_copy(prompt_id, str(body.get("key", "")))
        return {"ok": True}

    @app.get("/api/prompts/{prompt_id}")
    def prompt_detail(prompt_id: str):
        _prompt_or_404(prompt_id)
        return prompts.detail(prompt_id)

    @app.patch("/api/prompts/{prompt_id}")
    def prompt_patch(prompt_id: str, body: dict = Body(...)):
        meta = _prompt_or_404(prompt_id)
        changes = {}
        if "prompt" in body:
            changes["prompt"] = str(body["prompt"])
        if "spoken" in body:
            spoken = str(body["spoken"])
            changes["spoken_edited"] = None if spoken == "\n".join(line["text"] for line in meta.get("spoken", [])) else spoken
        if "include_text" in body:
            changes["include_text"] = bool(body["include_text"])
        if "attempt" in body:
            index = body["attempt"]
            if not isinstance(index, int) or not 0 <= index < len(meta["attempts"]):
                raise HTTPException(400, "Unknown attempt.")
            attempt = meta["attempts"][index]
            changes.update(prompt=attempt["prompt"], added=attempt["added"], suggestions=attempt["suggestions"], unsure=attempt["unsure"], language=attempt.get("language"), used_suggestions=[])
        prompts.update(prompt_id, **changes)
        copied = controller.copy_prompt(prompt_id) if "include_text" in body or "attempt" in body else None
        return dict(prompts.detail(prompt_id), copied=copied)

    @app.post("/api/prompts/{prompt_id}/copy")
    def prompt_copy(prompt_id: str):
        _prompt_or_404(prompt_id)
        if not controller.copy_prompt(prompt_id):
            raise HTTPException(409, "The clipboard is busy. Try again.")
        return {"ok": True}

    @app.post("/api/prompts/{prompt_id}/suggestion")
    def prompt_suggestion(prompt_id: str, body: dict = Body(...)):
        meta = _prompt_or_404(prompt_id)
        index = body.get("index")
        suggestions = meta.get("suggestions") or []
        if not isinstance(index, int) or not 0 <= index < len(suggestions):
            raise HTTPException(400, "Unknown suggestion.")
        used = meta.get("used_suggestions") or []
        copied = None
        if index not in used:
            prompts.update(prompt_id, prompt=f"{meta['prompt'].rstrip()}\n\n{suggestions[index]}", used_suggestions=used + [index])
            copied = controller.copy_prompt(prompt_id)
        return dict(prompts.detail(prompt_id), copied=copied)

    @app.post("/api/prompts/{prompt_id}/hear")
    def prompt_hear(prompt_id: str):
        _prompt_or_404(prompt_id)
        controller.hear_prompt_again(prompt_id)
        return {"ok": True}

    @app.post("/api/prompts/{prompt_id}/write")
    def prompt_write(prompt_id: str, body: dict = Body(default={})):
        _prompt_or_404(prompt_id)
        adds = body.get("adds")
        controller.write_prompt_again(prompt_id, body.get("engine"), body.get("model"), body.get("effort"), adds if isinstance(adds, bool) else None)
        return {"ok": True}

    @app.delete("/api/prompts/{prompt_id}")
    def prompt_delete(prompt_id: str):
        meta = _prompt_or_404(prompt_id)
        if meta["status"] in prompts.BUSY:
            raise HTTPException(409, "Wait for this prompt to finish.")
        prompts.delete(prompt_id)
        controller.forget_prompt(prompt_id)
        return {"ok": True}

    @app.get("/api/prompts/{prompt_id}/audio")
    def prompt_audio(prompt_id: str):
        _prompt_or_404(prompt_id)
        path = prompts.audio_path(prompt_id)
        if not path:
            raise HTTPException(404, "There's no audio for this prompt.")
        return FileResponse(path, media_type="audio/flac")

    # ------------------------------------------------------------- hints and prompts

    @app.get("/api/instructions")
    def get_instructions():
        return {"groups": instructions.overview()}

    @app.patch("/api/instructions/{key}")
    def patch_instruction(key: str, body: dict = Body(...)):
        if key not in instructions.ORIGINALS:
            raise HTTPException(404, "There's no such text.")
        return instructions.save(key, str(body.get("text", "")))

    @app.post("/api/instructions/{key}/restore")
    def restore_instruction(key: str):
        if key not in instructions.ORIGINALS:
            raise HTTPException(404, "There's no such text.")
        return instructions.restore(key)

    @app.get("/api/instructions-preview/{which}")
    def preview_instructions(which: str):
        if which in ("prompt", "code", "proofread"):
            return {"text": prompts.sample_request(controller.settings, which)}
        if which in ("meeting", "solo"):
            return {"text": notes.sample_prompt(controller.settings, which)}
        raise HTTPException(404, "There's no such preview.")

    # ------------------------------------------------------------- settings and setup

    @app.get("/api/settings")
    def get_settings():
        return controller.settings

    @app.patch("/api/settings")
    def patch_settings(body: dict = Body(...)):
        result = dict(controller.update_settings(body))
        if desktop:
            for key in ("hotkey", "hotkey_solo", "hotkey_prompt", "hotkey_code", "hotkey_proofread", "hotkey_proofread_text", "hotkey_finish"):
                if key in body:
                    result[f"{key}_error"] = desktop.hotkeys.errors.get(key) if desktop.hotkeys else None
        return result

    @app.get("/api/devices")
    def devices():
        return controller.devices()

    @app.get("/api/checks")
    def run_checks():
        return checks.run_checks()

    @app.post("/api/audio-test/start")
    def audio_test_start():
        controller.start_audio_test()
        return {"ok": True}

    @app.post("/api/audio-test/stop")
    def audio_test_stop():
        controller.stop_audio_test()
        return {"ok": True}

    @app.get("/api/about")
    def about():
        return {"version": __version__, "meetings_dir": str(storage.meetings_dir()), "logs": str(LOG_DIR)}

    @app.post("/api/open-folder")
    def open_folder(body: dict = Body(...)):
        target = {"meetings": storage.meetings_dir(), "logs": Path(LOG_DIR)}.get(body.get("which"))
        if not target:
            raise HTTPException(400, "Unknown folder.")
        target.mkdir(parents=True, exist_ok=True)
        os.startfile(str(target))
        return {"ok": True}

    # ------------------------------------------------------------- desktop

    @app.post("/api/show")
    def show():
        if desktop:
            desktop.show_main()
        return {"ok": True}

    @app.post("/api/mini")
    def mini_action(body: dict = Body(...)):
        if body.get("action") == "open-prompt":
            controller.show_prompt_in_window(body.get("id"))
        if desktop:
            if body.get("action") in ("open", "open-prompt"):
                desktop.show_main()
            elif body.get("action") == "hide":
                desktop.hide_mini()
            elif body.get("action") == "open-up":
                desktop.open_up_bar(True)
            elif body.get("action") == "close-up":
                desktop.open_up_bar(False)
            elif body.get("action") == "dragged":
                desktop.remember_bar_place()
        return {"ok": True}

    @app.post("/api/quit")
    def quit_app():
        if desktop:
            desktop.quit()
        return {"ok": True}

    # ------------------------------------------------------------- live state

    @app.websocket("/ws")
    async def live(ws: WebSocket):
        if ws.query_params.get("token") != token or ws.headers.get("host") not in allowed_hosts:
            await ws.close(code=1008)
            return
        await ws.accept()
        loop = asyncio.get_running_loop()
        changed = asyncio.Event()

        def wake() -> None:
            try:
                loop.call_soon_threadsafe(changed.set)
            except RuntimeError:  # the app is closing
                pass

        controller.page_wakers.add(wake)
        try:
            while True:
                # Cleared before the snapshot, so a change landing between the two sends another one, not none.
                changed.clear()
                snapshot = controller.snapshot()
                await ws.send_json(snapshot)
                busy = snapshot["recording"]["active"] or snapshot["audio_test"] or snapshot["model_test"]["recording"] or snapshot["prompt"]["recording"]
                try:
                    await asyncio.wait_for(changed.wait(), 0.08 if busy else 0.5)
                except TimeoutError:
                    pass
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            controller.page_wakers.discard(wake)

    return app
