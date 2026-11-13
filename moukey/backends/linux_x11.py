# linux with x11. receiving goes through XTest, capturing through XRecord plus a pointer
# and keyboard grab while the cursor is on the other computer.
# experimental: it passes the tests but still needs more real machines to try it
# TODO: wayland through evdev/uinput

import threading

from pynput import mouse
from Xlib import X, display
from Xlib.ext import record, xtest
from Xlib.protocol import rq

from moukey.backends.scancodes import evdev_code, name_for_evdev

_display = display.Display()
_mouse = mouse.Controller()

PYNPUT_BUTTONS = {
    "left": mouse.Button.left,
    "right": mouse.Button.right,
    "middle": mouse.Button.middle,
}

# x11 button numbers. 4 to 7 are the wheel, one press per notch
X_BUTTONS = {1: "left", 2: "middle", 3: "right"}
X_WHEEL = {4: (0, 1), 5: (0, -1), 6: (-1, 0), 7: (1, 0)}

PANIC = {"ctrl", "alt", "shift"}  # + esc
MODIFIERS = {
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "alt_l": "alt",
    "alt_r": "alt",
    "shift_l": "shift",
    "shift_r": "shift",
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
    """watches the real mouse and keyboard, and grabs them while the cursor is over there"""

    def __init__(self, on_local_move, on_remote_event, on_panic):
        self.on_local_move = on_local_move
        self.on_remote_event = on_remote_event
        self.on_panic = on_panic
        self.remote = False
        self.held: set[str] = set()
        w, h = screen_size()
        self.park = (w // 2, h // 2)
        # xlib connections aren't meant to be shared between threads: one for the
        # record loop, one for grabs and warps
        self._rec = display.Display()
        self._ctl = display.Display()
        self._root = self._ctl.screen().root
        self._ctx = None

    def start(self) -> None:
        self._ctx = self._rec.record_create_context(
            0,
            [record.AllClients],
            [
                {
                    "core_requests": (0, 0),
                    "core_replies": (0, 0),
                    "ext_requests": (0, 0, 0, 0),
                    "ext_replies": (0, 0, 0, 0),
                    "delivered_events": (0, 0),
                    "device_events": (X.KeyPress, X.MotionNotify),
                    "errors": (0, 0),
                    "client_started": False,
                    "client_died": False,
                }
            ],
        )
        threading.Thread(
            target=self._rec.record_enable_context, args=(self._ctx, self._on_record), daemon=True
        ).start()

    def stop(self) -> None:
        if self.remote:
            self._ungrab()
        self.remote = False
        if self._ctx is not None:
            self._ctl.record_disable_context(self._ctx)
            self._ctl.flush()
            self._ctx = None

    def grab(self) -> None:
        self.remote = True
        self._root.grab_pointer(
            False,
            X.PointerMotionMask | X.ButtonPressMask | X.ButtonReleaseMask,
            X.GrabModeAsync,
            X.GrabModeAsync,
            X.NONE,
            X.NONE,
            X.CurrentTime,
        )
        self._root.grab_keyboard(False, X.GrabModeAsync, X.GrabModeAsync, X.CurrentTime)
        self._warp(*self.park)

    def release(self, x: int, y: int) -> None:
        self.remote = False
        self._ungrab()
        self._warp(x, y)

    def _ungrab(self) -> None:
        self._ctl.ungrab_pointer(X.CurrentTime)
        self._ctl.ungrab_keyboard(X.CurrentTime)
        self._ctl.sync()

    def _warp(self, x: int, y: int) -> None:
        self._root.warp_pointer(x, y)
        self._ctl.sync()

    def _on_record(self, reply) -> None:
        if reply.category != record.FromServer or reply.client_swapped or not reply.data:
            return
        data = reply.data
        while data:
            event, data = rq.EventField(None).parse_binary_value(
                data, self._rec.display, None, None
            )
            self._handle(event)

    def _handle(self, ev) -> None:
        if ev.type == X.MotionNotify:
            x, y = ev.root_x, ev.root_y
            if not self.remote:
                # crossing an edge makes run_link call grab() from in here
                self.on_local_move(x, y)
                return
            dx, dy = x - self.park[0], y - self.park[1]
            # our own warp back to the parking spot shows up here too, with no movement
            if dx or dy:
                self.on_remote_event("move", dx=dx, dy=dy)
                self._warp(*self.park)
        elif ev.type in (X.ButtonPress, X.ButtonRelease):
            if not self.remote:
                return
            down = ev.type == X.ButtonPress
            if ev.detail in X_BUTTONS:
                self.on_remote_event("button", button=X_BUTTONS[ev.detail], down=down)
            elif ev.detail in X_WHEEL and down:
                dx, dy = X_WHEEL[ev.detail]
                self.on_remote_event("scroll", dx=dx, dy=dy)
        elif ev.type in (X.KeyPress, X.KeyRelease):
            name = name_for_evdev(ev.detail - 8)
            down = ev.type == X.KeyPress
            if name in MODIFIERS:
                if down:
                    self.held.add(MODIFIERS[name])
                else:
                    self.held.discard(MODIFIERS[name])
            if name == "esc" and down and PANIC <= self.held:
                self.on_panic()
                return
            if self.remote and name is not None:
                self.on_remote_event("key", key=name, down=down)
