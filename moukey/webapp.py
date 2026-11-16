import ctypes
import json
import logging
import os
import socket
import sys
import threading
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

import webview
from webview.dom import DOMEventHandler

from moukey import APP_NAME, __version__, backends
from moukey.core import App
from moukey.keys import config_dir
from moukey.tray import start_tray


def ui_dir() -> Path:
    # inside the exe, pyinstaller unpacks data files under sys._MEIPASS
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "moukey" / "ui"


class Api:
    """what the javascript side is allowed to call"""

    def __init__(self):
        self.app: App | None = None
        self.window = None

    def state(self) -> dict:
        return self.app.state() if self.app else {}

    def version(self) -> str:
        return __version__

    def connect(self, peer_id: str) -> None:
        self.app.connect(str(peer_id))

    def disconnect(self) -> None:
        self.app.disconnect()

    def set_offset(self, peer_id: str, x: int, y: int) -> None:
        self.app.set_offset(str(peer_id), int(x), int(y))

    def connect_ip(self, ip: str) -> str:
        return self.app.connect_ip(str(ip))

    def answer(self, ok: bool) -> None:
        self.app.answer(bool(ok))

    def set_option(self, name: str, value: bool) -> None:
        self.app.set_option(str(name), bool(value))

    def set_autostart(self, on: bool) -> None:
        self.app.set_autostart(bool(on))

    def forget(self, key_hex: str) -> None:
        self.app.forget(str(key_hex))

    def choose_files(self) -> int:
        paths = self.window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True)
        return self.app.send_files(list(paths or []))

    def cancel_transfer(self, tid: str) -> None:
        self.app.cancel_transfer(str(tid))

    def clear_transfers(self) -> None:
        self.app.clear_transfers()

    def open_downloads(self) -> None:
        folder = self.app.files.folder
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def copy_clip(self, clip_id: int) -> None:
        self.app.copy_clip(int(clip_id))

    def clear_clips(self) -> None:
        self.app.clear_clips()

    def open_link(self, url: str) -> None:
        # only our own pages, the page can't make us open anything else
        if url in ("https://github.com/Nando1N/moukey", "https://rsms.me/inter/"):
            webbrowser.open(url)


def dark_title_bar(window) -> None:
    # windows draws a white title bar by default, which looks off on a dark app
    if sys.platform != "win32":
        return
    try:
        hwnd = window.native.Handle.ToInt32()
        on = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))
    except (AttributeError, OSError):
        pass


# a tiny local-only door so a second MouKey can ask the first one to show itself
SHOW_PORT = 47476


def claim_door() -> socket.socket | None:
    # grabbing the port is the lock itself. it has to happen before the window exists,
    # otherwise two quick launches both get through and fight over the same webview2 folder
    try:
        return socket.create_server(("127.0.0.1", SHOW_PORT))
    except OSError:
        return None


def wake_running_copy() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", SHOW_PORT), timeout=1) as sock:
            sock.sendall(b"show")
        return True
    except OSError:
        return False


def listen_for_wake(server: socket.socket, on_show) -> None:
    def loop():
        while True:
            conn, _ = server.accept()
            with conn:
                if conn.recv(16) == b"show":
                    on_show()

    threading.Thread(target=loop, daemon=True).start()


def setup_log() -> None:
    # only connection events end up here, never keys, clipboard or files
    folder = config_dir()
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / "moukey.log", maxBytes=200_000, backupCount=1)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger = logging.getLogger("moukey")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.info("moukey %s starting", __version__)

    # a crash in a background thread used to vanish and leave a half started copy behind
    def log_crash(args) -> None:
        where = args.thread.name if args.thread else "thread"
        info = (args.exc_type, args.exc_value, args.exc_traceback)
        logger.error("crash in %s", where, exc_info=info)

    threading.excepthook = log_crash


def main() -> None:
    door = claim_door()
    if door is None:
        # opening the exe again should bring back the window, not start a second copy
        wake_running_copy()
        return
    setup_log()
    backend = backends.load()
    api = Api()
    window = webview.create_window(
        APP_NAME,
        url=str(ui_dir() / "index.html"),
        js_api=api,
        width=980,
        height=640,
        min_size=(820, 560),
        background_color="#0B0B12",
    )

    api.window = window
    tray = {"icon": None, "quitting": False, "told": False}

    def push(state: dict) -> None:
        if tray["icon"] is not None:
            tray["icon"].update_menu()
        try:
            window.evaluate_js(f"window.moukey && window.moukey.render({json.dumps(state)})")
        except Exception:
            # the page may still be loading or already closing, the next push fixes it
            pass

    def status() -> str:
        link = api.app.link if api.app else None
        if link is None:
            return "Não conectado"
        if link["away"]:
            return f"Controlando {link['name']}"
        if link["guest"]:
            return f"Controlado por {link['name']}"
        return f"Conectado com {link['name']}"

    def quit_app() -> None:
        tray["quitting"] = True
        if api.app:
            api.app.close()
        if tray["icon"] is not None:
            tray["icon"].stop()
        window.destroy()

    def on_drop(event) -> None:
        files = event.get("dataTransfer", {}).get("files", [])
        paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
        if api.app and paths:
            api.app.send_files(paths)

    def started() -> None:
        listen_for_wake(door, window.show)
        api.app = App(backend, push)
        # dropping files on the window sends them, the browser alone can't see full paths
        window.dom.document.events.dragover += DOMEventHandler(lambda e: None, True, True)
        window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
        tray["icon"] = start_tray(
            ui_dir() / "img" / "icon-64.png",
            status,
            on_open=window.show,
            on_pause=api.app.disconnect,
            on_quit=quit_app,
        )
        push(api.app.state())

    def closing():
        if tray["quitting"]:
            return True
        # closing the window only hides it, the mouse keeps working from the tray
        window.hide()
        if not tray["told"] and tray["icon"] is not None:
            tray["told"] = True
            tray["icon"].notify("O MouKey continua rodando aqui. Para sair, use o menu do ícone.")
        return False

    window.events.closing += closing
    window.events.shown += lambda: dark_title_bar(window)
    webview.start(started)


if __name__ == "__main__":
    main()
