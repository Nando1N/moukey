import ctypes
import json
import os
import sys
import webbrowser
from pathlib import Path

import webview
from webview.dom import DOMEventHandler

from moukey import APP_NAME, __version__, backends
from moukey.core import App
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

    def set_side(self, peer_id: str, side: str) -> None:
        self.app.set_side(str(peer_id), str(side))

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


def main() -> None:
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
        if link["role"] == "controlling":
            return f"Controlando {link['name']}"
        return f"Controlado por {link['name']}"

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
