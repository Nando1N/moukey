# linux with x11. for now this side only receives: a windows pc can drive a linux
# notebook, but the linux mouse doesn't cross over yet. grabbing the pointer on x11
# without freezing the desktop needs testing on real machines first
# TODO: capture on x11 (XGrabPointer + XRecord), then wayland through evdev/uinput

from pynput import mouse
from Xlib import X, display
from Xlib.ext import xtest

from moukey.backends.scancodes import evdev_code

_display = display.Display()
_mouse = mouse.Controller()

PYNPUT_BUTTONS = {
    "left": mouse.Button.left,
    "right": mouse.Button.right,
    "middle": mouse.Button.middle,
}


def init() -> None:
    pass


def screen_size() -> tuple[int, int]:
    root = _display.screen().root.get_geometry()
    return root.width, root.height


def monitors() -> list[tuple[int, int, int, int]]:
    try:
        found = _display.screen().root.xrandr_get_monitors().monitors
    except Exception:
        # randr 1.5 missing, treat the whole screen as one monitor
        return [(0, 0, *screen_size())]
    found = sorted(found, key=lambda m: not m.primary)
    return [(m.x, m.y, m.width_in_pixels, m.height_in_pixels) for m in found] or [
        (0, 0, *screen_size())
    ]


def position() -> tuple[int, int]:
    x, y = _mouse.position
    return int(x), int(y)


def move_to(x: int, y: int) -> None:
    _mouse.position = (x, y)


def move(dx: int, dy: int) -> None:
    _mouse.move(dx, dy)


def button(name: str, down: bool) -> None:
    if down:
        _mouse.press(PYNPUT_BUTTONS[name])
    else:
        _mouse.release(PYNPUT_BUTTONS[name])


def scroll(dx: int, dy: int) -> None:
    _mouse.scroll(dx, dy)


def key(name: str, down: bool) -> None:
    code = evdev_code(name)
    if code is None:
        return
    # x keycodes are evdev codes + 8, the receiving side applies its own layout
    xtest.fake_input(_display, X.KeyPress if down else X.KeyRelease, code + 8)
    _display.sync()


class Capture:
    """does nothing yet, see the note at the top"""

    def __init__(self, on_local_move, on_remote_event, on_panic):
        self.remote = False
        self.park = (0, 0)

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def grab(self) -> None:
        pass

    def release(self, x: int, y: int) -> None:
        self.remote = False
