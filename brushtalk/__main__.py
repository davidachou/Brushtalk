"""Starts Brushtalk. A second launch just brings the running one forward."""
from __future__ import annotations

import argparse
import ctypes
import json
import logging
import logging.handlers
import secrets
import socket
import sys
import threading
import time
import urllib.request

from .config import DATA, INSTANCE_PATH, LOG_DIR, write_json


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    # At INFO level the server logs each connection's URL, which includes this run's token.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def bring_existing_forward() -> bool:
    try:
        info = json.loads(INSTANCE_PATH.read_text(encoding="utf-8"))
        request = urllib.request.Request(
            f"http://127.0.0.1:{info['port']}/api/show", method="POST", headers={"X-Token": info["token"]}
        )
        urllib.request.urlopen(request, timeout=3)
        return True
    except Exception:
        return False


def get_whisper() -> int:
    """For setup: the speech model now, rather than on the first recording, which would have to wait for it."""
    from faster_whisper.utils import download_model

    from .config import MODEL_NAME, ROOT, find_whisper_model, load_settings

    if find_whisper_model(load_settings()):
        print("Whisper is on this PC already.")
        return 0
    print("Downloading Whisper, about 1.6 GB. This happens once.", flush=True)
    try:
        download_model(MODEL_NAME, cache_dir=str(ROOT / "models"))
    except Exception as exc:
        print(f"It didn't download: {exc}")
        return 1
    print("Whisper is ready.")
    return 0


def print_checks() -> int:
    """For setup: what the checks in Settings say, as text."""
    from .checks import run_checks

    sys.stdout.reconfigure(errors="replace")
    marks = {"ok": "OK  ", "warn": "NOTE", "fail": "FIX "}
    for item in run_checks():
        print(f"   {marks.get(item['status'], '    ')} {item['label']}: {item['detail']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="brushtalk")
    parser.add_argument("--background", action="store_true", help="start hidden in the tray")
    parser.add_argument("--headless", action="store_true", help="server only, for testing")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--token", default="")
    parser.add_argument("--install-shortcuts", action="store_true")
    parser.add_argument("--get-whisper", action="store_true", help="for setup: download the speech model now")
    parser.add_argument("--check", action="store_true", help="for setup: what's ready on this PC, as Settings shows it")
    args = parser.parse_args()

    if args.install_shortcuts:
        from .desktop import install_shortcuts

        for path in install_shortcuts():
            print("Created", path)
        return 0
    if args.get_whisper:
        return get_whisper()
    if args.check:
        return print_checks()

    DATA.mkdir(parents=True, exist_ok=True)
    setup_logging()
    log = logging.getLogger("brushtalk")

    if not args.headless:
        # The mutex is held for the life of the process, and Windows frees it even after a crash. The old name is for a copy started before the
        # app was renamed: two copies would share one data folder, and this one would take recordings still going in the other as cut off.
        mutexes, already_running = [], False
        for name in ("Local\\KKA.Brushtalk", "Local\\KKA.NoteTaker"):
            mutexes.append(ctypes.windll.kernel32.CreateMutexW(None, False, name))
            already_running = already_running or ctypes.windll.kernel32.GetLastError() == 183
        if already_running:
            if not args.background:
                bring_existing_forward()
            return 0
        _ = mutexes

    import uvicorn

    from .controller import Controller
    from .server import create_app

    port = args.port or free_port()
    token = args.token or secrets.token_urlsafe(24)
    url = f"http://127.0.0.1:{port}/?token={token}"

    controller = Controller()
    desktop = None
    if not args.headless:
        from .desktop import Desktop

        desktop = Desktop(controller, url, start_hidden=args.background)

    app = create_app(controller, token, port, desktop)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None, access_log=False))
    thread = threading.Thread(target=server.run, daemon=True, name="server")
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    # Neither of these is worth not opening for. A full disk is when you most need to see what's going on.
    try:
        write_json(INSTANCE_PATH, {"port": port, "token": token})
    except OSError:
        log.exception("Couldn't note where this copy of the app is")
    log.info("Started on port %s", port)
    try:
        controller.recover()
    except Exception:
        log.exception("Picking up after the last run failed")

    try:
        if args.headless:
            print(url, flush=True)
            thread.join()
        else:
            try:
                desktop.run()
            except Exception:
                log.exception("The window couldn't open; falling back to the browser")
                import webbrowser

                webbrowser.open(url)
                thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        controller.shutdown()
        server.should_exit = True
        INSTANCE_PATH.unlink(missing_ok=True)
        log.info("Stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
