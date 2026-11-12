import ctypes
import json
import sys
from pathlib import Path

import webview

from moukey import APP_NAME, __version__, backends
from moukey.core import App


def ui_dir() -> Path:
    # inside the exe, pyinstaller unpacks data files under sys._MEIPASS
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "moukey" / "ui"


class Api:
    """what the javascript side is allowed to call"""

    def __init__(self):
        self.app: App | None = None

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

    def push(state: dict) -> None:
        try:
            window.evaluate_js(f"window.moukey && window.moukey.render({json.dumps(state)})")
        except Exception:
            # the page may still be loading or already closing, the next push fixes it
            pass

    def started() -> None:
        api.app = App(backend, push)
        push(api.app.state())

    def closing() -> None:
        if api.app:
            api.app.close()

    window.events.closing += closing
    window.events.shown += lambda: dark_title_bar(window)
    webview.start(started)


if __name__ == "__main__":
    main()
