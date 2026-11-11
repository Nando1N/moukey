import ctypes

from pynput import keyboard, mouse

WM_MOUSEMOVE = 0x0200
WM_MOUSEWHEEL = 0x020A
WM_MOUSEHWHEEL = 0x020E
WHEEL_DELTA = 120
LLMHF_INJECTED = 0x01

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

user32 = ctypes.windll.user32
_mouse = mouse.Controller()


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


def emergency_hotkey(callback) -> keyboard.GlobalHotKeys:
    # keyboard isn't grabbed yet, so this always reaches us
    hk = keyboard.GlobalHotKeys({"<ctrl>+<alt>+<shift>+<esc>": callback})
    hk.start()
    return hk


def _wheel(data) -> int:
    delta = ctypes.c_short(data.mouseData >> 16).value
    # touchpads send small deltas, still count them as one notch
    if delta == 0:
        return 0
    return delta // WHEEL_DELTA or (1 if delta > 0 else -1)


class Capture:
    """grabs the real mouse while the cursor is on the other computer"""

    def __init__(self, on_local_move, on_remote_event):
        self.on_local_move = on_local_move
        self.on_remote_event = on_remote_event
        self.remote = False
        w, h = screen_size()
        self.park = (w // 2, h // 2)
        self.listener = mouse.Listener(win32_event_filter=self._filter)

    def start(self) -> None:
        self.listener.start()

    def stop(self) -> None:
        self.remote = False
        self.listener.stop()

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
