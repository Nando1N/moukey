import ctypes
import sys
import winreg
from ctypes import wintypes

from pynput import keyboard, mouse

from moukey.backends.scancodes import CODES, NAMES

WM_MOUSEMOVE = 0x0200
WM_MOUSEWHEEL = 0x020A
WM_MOUSEHWHEEL = 0x020E
WHEEL_DELTA = 120
LLMHF_INJECTED = 0x01

WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
LLKHF_EXTENDED = 0x01
LLKHF_INJECTED = 0x10

BUTTON_MSGS = {
    0x0201: ("left", True),
    0x0202: ("left", False),
    0x0204: ("right", True),
    0x0205: ("right", False),
    0x0207: ("middle", True),
    0x0208: ("middle", False),
}

PYNPUT_BUTTONS = {
    "left": mouse.Button.left,
    "right": mouse.Button.right,
    "middle": mouse.Button.middle,
}

PANIC = {"ctrl", "alt", "shift"}  # + esc
MODIFIERS = {
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "alt_l": "alt",
    "alt_r": "alt",
    "shift_l": "shift",
    "shift_r": "shift",
}

user32 = ctypes.windll.user32
_mouse = mouse.Controller()


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class INPUT(ctypes.Structure):
    # the union needs the mouse struct too, or sizeof(INPUT) comes out wrong
    # and SendInput quietly does nothing
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x01
KEYEVENTF_KEYUP = 0x02
KEYEVENTF_SCANCODE = 0x08


def init() -> None:
    # without this, windows reports a fake smaller resolution on scaled
    # displays (125%, 150%) and the cursor lands in the wrong place
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        user32.SetProcessDPIAware()


def screen_size() -> tuple[int, int]:
    # TODO: multiple monitors, this is only the primary one
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


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
    code = CODES.get(name)
    if code is None:
        return
    flags = KEYEVENTF_SCANCODE
    if code > 0xFF:
        flags |= KEYEVENTF_EXTENDEDKEY
    if not down:
        flags |= KEYEVENTF_KEYUP
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.u.ki = KEYBDINPUT(0, code & 0xFF, flags, 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_available() -> bool:
    # only makes sense for the installed exe, not when running from source
    return getattr(sys, "frozen", False)


def autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, "MouKey")
            return True
    except OSError:
        return False


def set_autostart(on: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if on:
            winreg.SetValueEx(key, "MouKey", 0, winreg.REG_SZ, f'"{sys.executable}"')
        else:
            try:
                winreg.DeleteValue(key, "MouKey")
            except FileNotFoundError:
                pass


def _wheel(data) -> int:
    delta = ctypes.c_short(data.mouseData >> 16).value
    # touchpads send small deltas, still count them as one notch
    if delta == 0:
        return 0
    return delta // WHEEL_DELTA or (1 if delta > 0 else -1)


class Capture:
    """grabs the real mouse and keyboard while the cursor is on the other computer"""

    def __init__(self, on_local_move, on_remote_event, on_panic):
        self.on_local_move = on_local_move
        self.on_remote_event = on_remote_event
        self.on_panic = on_panic
        self.remote = False
        self.held: set[str] = set()
        w, h = screen_size()
        self.park = (w // 2, h // 2)
        self.listener = mouse.Listener(win32_event_filter=self._filter)
        self.keys = keyboard.Listener(win32_event_filter=self._key_filter)

    def start(self) -> None:
        self.listener.start()
        self.keys.start()

    def stop(self) -> None:
        self.remote = False
        self.listener.stop()
        self.keys.stop()

    def grab(self) -> None:
        # the cursor sits still in the middle and we read how far the user
        # tried to move it. parked on the edge it would get clamped
        self.remote = True
        move_to(*self.park)

    def release(self, x: int, y: int) -> None:
        self.remote = False
        move_to(x, y)

    def _filter(self, msg, data):
        # runs inside a windows hook. it must return fast, or windows silently
        # drops the hook, so no network calls in here
        if data.flags & LLMHF_INJECTED:
            return True

        if not self.remote:
            # if this move just crossed over, swallow it too, otherwise windows
            # applies it after grab() and the cursor leaves the parking spot
            if msg == WM_MOUSEMOVE and self.on_local_move(data.pt.x, data.pt.y):
                self.listener.suppress_event()
            return True

        if msg == WM_MOUSEMOVE:
            dx, dy = data.pt.x - self.park[0], data.pt.y - self.park[1]
            if dx or dy:
                self.on_remote_event("move", dx=dx, dy=dy)
        elif msg in BUTTON_MSGS:
            name, down = BUTTON_MSGS[msg]
            self.on_remote_event("button", button=name, down=down)
        elif msg == WM_MOUSEWHEEL:
            self.on_remote_event("scroll", dx=0, dy=_wheel(data))
        elif msg == WM_MOUSEHWHEEL:
            self.on_remote_event("scroll", dx=_wheel(data), dy=0)
        self.listener.suppress_event()

    def _key_filter(self, msg, data):
        if data.flags & LLKHF_INJECTED:
            return True

        code = data.scanCode | (0xE000 if data.flags & LLKHF_EXTENDED else 0)
        name = NAMES.get(code)
        down = msg in (WM_KEYDOWN, WM_SYSKEYDOWN)

        if name in MODIFIERS:
            if down:
                self.held.add(MODIFIERS[name])
            else:
                self.held.discard(MODIFIERS[name])
        # checked before anything else so it works even if the rest is broken
        if name == "esc" and down and PANIC <= self.held:
            self.on_panic()
            self.keys.suppress_event()

        if not self.remote:
            return True
        if name is not None:
            self.on_remote_event("key", key=name, down=down)
        # unknown keys are swallowed too, typing on the wrong machine is worse
        self.keys.suppress_event()
