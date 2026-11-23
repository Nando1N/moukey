# macos through quartz. receiving posts CGEvents, capturing is an active event tap that
# swallows the real mouse and keyboard while the cursor is on the other computer.
# experimental: written from apple's headers and docs, it still needs a real mac to try it.
# everything needs the accessibility permission. without it the tap can't be created and
# posted events are dropped without any error, so permissions_ok() is there to check first

import logging
import subprocess
import threading
import time

try:
    import Quartz
except ImportError:
    # lets the tests load the pure parts (key table, ctrl/cmd swap, geometry) anywhere
    Quartz = None

from moukey import edges

# pictures and files on the clipboard live in their own file, like on windows
from moukey.backends.macos_clip import (  # noqa: F401
    clip_kind,
    clip_seq,
    read_files,
    read_image,
    write_files,
    write_image,
)

log = logging.getLogger("moukey")

# CGEventType numbers from CGEventTypes.h (same values pyobjc exposes as kCGEvent...)
LEFT_DOWN, LEFT_UP, RIGHT_DOWN, RIGHT_UP = 1, 2, 3, 4
MOVED, LEFT_DRAGGED, RIGHT_DRAGGED = 5, 6, 7
KEY_DOWN, KEY_UP, FLAGS_CHANGED = 10, 11, 12
SCROLL = 22
OTHER_DOWN, OTHER_UP, OTHER_DRAGGED = 25, 26, 27
TAP_TIMEOUT, TAP_USER_INPUT = 0xFFFFFFFE, 0xFFFFFFFF

MOVES = {MOVED, LEFT_DRAGGED, RIGHT_DRAGGED, OTHER_DRAGGED}
DOWNS = {LEFT_DOWN, RIGHT_DOWN, OTHER_DOWN}
UPS = {LEFT_UP, RIGHT_UP, OTHER_UP}
TAPPED = MOVES | DOWNS | UPS | {SCROLL, KEY_DOWN, KEY_UP, FLAGS_CHANGED}

# CGEventField numbers
CLICK_STATE = 1
BUTTON_NUMBER = 3
DELTA_X, DELTA_Y = 4, 5
KEYCODE = 9
SCROLL_Y, SCROLL_X = 11, 12
SCROLL_CONTINUOUS = 88
SCROLL_POINT_Y, SCROLL_POINT_X = 96, 97
USER_DATA = 42

# stamped on every event we post, so our own tap lets them through
MAGIC = 0x4D6F754B  # "MouK"

# quartz button numbers. 3 and 4 are the side buttons, all "other" mouse events
BUTTON_NUMBERS = {"left": 0, "right": 1, "middle": 2, "back": 3, "forward": 4}
BUTTON_NAMES = {n: name for name, n in BUTTON_NUMBERS.items()}

# a windows notch is 3 lines by default, one quartz line is a lot less
LINES_PER_NOTCH = 3
# trackpads scroll in points, this many points count as one wheel notch
POINTS_PER_NOTCH = 40
# same default as windows, and it's the other side's hand doing the clicking anyway
DOUBLE_CLICK = 0.5

# mac virtual keycodes (kVK_* in Events.h) by physical position, the same names the
# protocol uses. the modifier keys here are by position too: command sits where the
# windows key is, which is also what macos does with a pc keyboard plugged in
KEYCODES = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04, "g": 0x05, "z": 0x06,
    "x": 0x07, "c": 0x08, "v": 0x09, "b": 0x0B, "q": 0x0C, "w": 0x0D, "e": 0x0E,
    "r": 0x0F, "y": 0x10, "t": 0x11, "o": 0x1F, "u": 0x20, "i": 0x22, "p": 0x23,
    "l": 0x25, "j": 0x26, "k": 0x28, "n": 0x2D, "m": 0x2E,
    "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "5": 0x17, "6": 0x16, "7": 0x1A,
    "8": 0x1C, "9": 0x19, "0": 0x1D,
    "equal": 0x18, "minus": 0x1B, "bracket_right": 0x1E, "bracket_left": 0x21,
    "quote": 0x27, "semicolon": 0x29, "backslash": 0x2A, "comma": 0x2B, "slash": 0x2C,
    "period": 0x2F, "grave": 0x32,
    # TODO: on iso keyboards macos swaps these two (section key vs grave), check on a real one
    "intl_backslash": 0x0A,
    "intl_ro": 0x5E,  # jis underscore, same spot as the abnt2 /? key
    "kp_comma": 0x5F,
    "enter": 0x24, "tab": 0x30, "space": 0x31, "backspace": 0x33, "esc": 0x35,
    "meta_r": 0x36, "meta_l": 0x37, "shift_l": 0x38, "caps_lock": 0x39, "alt_l": 0x3A,
    "ctrl_l": 0x3B, "shift_r": 0x3C, "alt_r": 0x3D, "ctrl_r": 0x3E,
    "kp_decimal": 0x41, "kp_multiply": 0x43, "kp_plus": 0x45, "num_lock": 0x47,
    "kp_divide": 0x4B, "kp_enter": 0x4C, "kp_minus": 0x4E,
    "kp_0": 0x52, "kp_1": 0x53, "kp_2": 0x54, "kp_3": 0x55, "kp_4": 0x56,
    "kp_5": 0x57, "kp_6": 0x58, "kp_7": 0x59, "kp_8": 0x5B, "kp_9": 0x5C,
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76, "f5": 0x60, "f6": 0x61,
    "f7": 0x62, "f8": 0x64, "f9": 0x65, "f10": 0x6D, "f11": 0x67, "f12": 0x6F,
    # apple's big keyboards have f13/f14 where print screen and scroll lock are
    "print_screen": 0x69, "scroll_lock": 0x6B,
    "menu": 0x6E,
    "insert": 0x72,  # the old help key sits where insert is
    "home": 0x73, "page_up": 0x74, "delete": 0x75, "end": 0x77, "page_down": 0x79,
    "left": 0x7B, "right": 0x7C, "down": 0x7D, "up": 0x7E,
}  # fmt: skip
KEY_NAMES = {code: name for name, code in KEYCODES.items()}

# shortcuts should feel native on both sides: ctrl+c on windows has to be cmd+c here and
# cmd+c here has to be ctrl+c there. so ctrl and the windows key trade places on the way
# in and on the way out. it's its own inverse, one table does both directions
SWAP = {"ctrl_l": "meta_l", "ctrl_r": "meta_r", "meta_l": "ctrl_l", "meta_r": "ctrl_r"}


def mac_code(name: str) -> int | None:
    """protocol name coming in -> mac keycode to press"""
    return KEYCODES.get(SWAP.get(name, name))


def protocol_name(code: int) -> str | None:
    """mac keycode pressed here -> protocol name to send"""
    name = KEY_NAMES.get(code)
    return SWAP.get(name, name) if name else None


SHIFT, CONTROL, OPTION, COMMAND = 0x20000, 0x40000, 0x80000, 0x100000
CAPS_LOCK = 0x39
# keycode -> (left/right bit from IOLLEvent.h, general CGEventFlags mask)
MOD_FLAGS = {
    0x38: (0x02, SHIFT),
    0x3C: (0x04, SHIFT),
    0x3B: (0x01, CONTROL),
    0x3E: (0x2000, CONTROL),
    0x3A: (0x20, OPTION),
    0x3D: (0x40, OPTION),
    0x37: (0x08, COMMAND),
    0x36: (0x10, COMMAND),
}
SIDE_BITS = 0x207F


def modifier_down(code: int, flags: int) -> bool:
    # macos only says "flags changed", the left/right bits tell which key and which way
    bit, mask = MOD_FLAGS[code]
    if flags & SIDE_BITS:
        return bool(flags & bit)
    # some virtual keyboards leave the side bits out, the general mask is all we get
    return bool(flags & mask)


def flags_for(held: set[int]) -> int:
    flags = 0
    for code in held:
        bit, mask = MOD_FLAGS[code]
        flags |= bit | mask
    return flags


# the physical control key, not command: cmd+option+shift+esc is force quit on a mac
PANIC = {"ctrl", "alt", "shift"}  # + esc
MODIFIERS = {0x3B: "ctrl", 0x3E: "ctrl", 0x3A: "alt", 0x3D: "alt", 0x38: "shift", 0x3C: "shift"}


def arrange(displays, main) -> list[tuple[int, int, int, int]]:
    """(display id, (x, y, w, h)) from quartz -> int rects, the main display first"""
    # quartz global coordinates already start at the top left of the main display with y
    # going down, like windows, so a screen on the left or above just has negative numbers
    rects = []
    for _, r in sorted(displays, key=lambda item: item[0] != main):
        rect = tuple(round(v) for v in r)
        # software mirroring lists both displays with the same bounds
        if rect not in rects:
            rects.append(rect)
    return rects


def clamp(screens, x: int, y: int, prev) -> tuple[int, int]:
    # windows keeps the cursor on a screen by itself. here we do it, or the edge check in
    # remote.py would see a cursor floating outside every display
    if edges.inside(screens, x, y):
        return x, y
    rx, ry, rw, rh = edges.inside(screens, *prev) or screens[0]
    return min(max(x, rx), rx + rw - 1), min(max(y, ry), ry + rh - 1)


def click_count(last, number: int, now: float, pos) -> int:
    # quartz doesn't work out double clicks for posted events, we have to say it's the 2nd
    if last is None:
        return 1
    b, when, (lx, ly), count = last
    near = abs(pos[0] - lx) <= 4 and abs(pos[1] - ly) <= 4
    return count + 1 if b == number and now - when <= DOUBLE_CLICK and near else 1


def notches(rest: float, points: float, step: float = POINTS_PER_NOTCH) -> tuple[int, float]:
    total = rest + points
    n = int(total / step)
    return n, total - n * step


def move_type(held: set[int]) -> tuple[int, int]:
    # moving with a button down is a drag, otherwise nothing gets dragged on the mac
    if 0 in held:
        return LEFT_DRAGGED, 0
    if 1 in held:
        return RIGHT_DRAGGED, 1
    if held:
        return OTHER_DRAGGED, min(held)
    return MOVED, 0


def button_types(number: int) -> tuple[int, int]:
    if number == 0:
        return LEFT_DOWN, LEFT_UP
    if number == 1:
        return RIGHT_DOWN, RIGHT_UP
    return OTHER_DOWN, OTHER_UP


_src = None
_screens: list[tuple] = []
_buttons: set[int] = set()
_mods: set[int] = set()
_last_click = None
_moved = None  # (x, y, when) of the last move we posted


def _source():
    global _src
    if _src is None:
        _src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        # by default posting freezes the real mouse and keyboard for a quarter second
        Quartz.CGEventSourceSetLocalEventsSuppressionInterval(_src, 0.0)
    return _src


def _post(ev) -> None:
    Quartz.CGEventSetIntegerValueField(ev, USER_DATA, MAGIC)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"


def permissions_ok() -> bool:
    try:
        import HIServices
    except ImportError:
        return False
    return bool(HIServices.AXIsProcessTrusted())


def ask_permissions() -> None:
    try:
        import HIServices

        # apple's own dialog, with a button to the right place in system settings
        HIServices.AXIsProcessTrustedWithOptions({HIServices.kAXTrustedCheckOptionPrompt: True})
    except ImportError:
        pass
    subprocess.Popen(["open", SETTINGS_URL])


def init() -> None:
    if not permissions_ok():
        log.warning("no accessibility permission, asking for it")
        ask_permissions()


def screen_size() -> tuple[int, int]:
    r = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
    return round(r.size.width), round(r.size.height)


def monitors() -> list[tuple[int, int, int, int]]:
    """every display as (x, y, width, height) in points, the main one first"""
    global _screens
    err, ids, count = Quartz.CGGetActiveDisplayList(16, None, None)
    if err or not count:
        return [(0, 0, *screen_size())]
    found = []
    for d in ids[:count]:
        r = Quartz.CGDisplayBounds(d)
        found.append((d, (r.origin.x, r.origin.y, r.size.width, r.size.height)))
    _screens = arrange(found, Quartz.CGMainDisplayID())
    return list(_screens)


def position() -> tuple[int, int]:
    # a posted event lands a moment later, right after a move we trust our own number
    if _moved and time.monotonic() - _moved[2] < 0.1:
        return _moved[0], _moved[1]
    loc = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    return int(loc.x), int(loc.y)


def _move(x: int, y: int, dx: int, dy: int) -> None:
    global _moved
    x, y = clamp(_screens or monitors(), x, y, position())
    kind, number = move_type(_buttons)
    ev = Quartz.CGEventCreateMouseEvent(_source(), kind, (x, y), number)
    # games and some apps read the raw deltas, not the position
    Quartz.CGEventSetIntegerValueField(ev, DELTA_X, dx)
    Quartz.CGEventSetIntegerValueField(ev, DELTA_Y, dy)
    _post(ev)
    _moved = (x, y, time.monotonic())


def move_to(x: int, y: int) -> None:
    px, py = position()
    _move(x, y, x - px, y - py)


def move(dx: int, dy: int) -> None:
    x, y = position()
    _move(x + dx, y + dy, dx, dy)


def button(name: str, down: bool) -> None:
    global _last_click
    number = BUTTON_NUMBERS[name]
    x, y = position()
    if down:
        _buttons.add(number)
        now = time.monotonic()
        count = click_count(_last_click, number, now, (x, y))
        _last_click = (number, now, (x, y), count)
    else:
        _buttons.discard(number)
        same = _last_click is not None and _last_click[0] == number
        count = _last_click[3] if same else 1
    press, let_go = button_types(number)
    ev = Quartz.CGEventCreateMouseEvent(_source(), press if down else let_go, (x, y), number)
    Quartz.CGEventSetIntegerValueField(ev, BUTTON_NUMBER, number)
    Quartz.CGEventSetIntegerValueField(ev, CLICK_STATE, count)
    _post(ev)


def scroll(dx: int, dy: int) -> None:
    # quartz's horizontal axis is positive to the left, the protocol's to the right
    ev = Quartz.CGEventCreateScrollWheelEvent(
        _source(),
        Quartz.kCGScrollEventUnitLine,
        2,
        dy * LINES_PER_NOTCH,
        -dx * LINES_PER_NOTCH,
    )
    _post(ev)


def key(name: str, down: bool) -> None:
    code = mac_code(name)
    if code is None:
        return
    # TODO: a posted caps lock press probably doesn't toggle the caps lock state
    ev = Quartz.CGEventCreateKeyboardEvent(_source(), code, down)
    if code in MOD_FLAGS:
        if down:
            _mods.add(code)
        else:
            _mods.discard(code)
        Quartz.CGEventSetType(ev, FLAGS_CHANGED)
    # posted events don't pick up modifiers on their own, every key carries the full set
    Quartz.CGEventSetFlags(ev, flags_for(_mods))
    _post(ev)


def autostart_available() -> bool:
    # TODO: a login item through SMAppService, once the app is signed
    return False


def autostart_enabled() -> bool:
    return False


def set_autostart(on: bool) -> None:
    pass


def reveal(path: str) -> None:
    # opens finder with the file already selected
    subprocess.Popen(["open", "-R", str(path)])


def _warp(x: int, y: int, frozen: bool) -> None:
    Quartz.CGWarpMouseCursorPosition((x, y))
    # re-associating right after a warp skips the quarter second macos freezes the
    # real mouse for. frozen = the mouse only reports deltas, the cursor stays put
    Quartz.CGAssociateMouseAndMouseCursorPosition(True)
    if frozen:
        Quartz.CGAssociateMouseAndMouseCursorPosition(False)


class Capture:
    """grabs the real mouse and keyboard while the cursor is on the other computer"""

    def __init__(self, on_local_move, on_remote_event, on_panic):
        self.on_local_move = on_local_move
        self.on_remote_event = on_remote_event
        self.on_panic = on_panic
        self.remote = False
        self.held: set[str] = set()
        x, y, w, h = monitors()[0]
        self.park = (x + w // 2, y + h // 2)
        self._tap = None
        self._loop = None
        self._ready = threading.Event()
        self._rest = [0.0, 0.0]  # trackpad scroll that didn't add up to a notch yet

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()
        self._ready.wait(2)

    def _run(self) -> None:
        mask = 0
        for kind in TAPPED:
            mask |= 1 << kind
        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            mask,
            self._on_event,
            None,
        )
        if self._tap is None:
            # no accessibility permission. this mac still receives, it just can't send
            log.warning("could not create the event tap, accessibility permission missing?")
            self._ready.set()
            return
        source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(self._loop, source, Quartz.kCFRunLoopDefaultMode)
        Quartz.CGEventTapEnable(self._tap, True)
        self._ready.set()
        Quartz.CFRunLoopRun()

    def stop(self) -> None:
        if self.remote:
            Quartz.CGAssociateMouseAndMouseCursorPosition(True)
        self.remote = False
        if self._tap is not None:
            Quartz.CGEventTapEnable(self._tap, False)
        if self._loop is not None:
            Quartz.CFRunLoopStop(self._loop)

    def grab(self) -> None:
        # same parking trick as windows, plus the cursor stops following the mouse
        self.remote = True
        _warp(*self.park, frozen=True)

    def release(self, x: int, y: int) -> None:
        self.remote = False
        _warp(x, y, frozen=False)

    def _on_event(self, proxy, kind, ev, refcon):
        # runs on the tap thread. macos turns the tap off if this is slow, so no network
        if kind in (TAP_TIMEOUT, TAP_USER_INPUT):
            Quartz.CGEventTapEnable(self._tap, True)
            return ev
        if Quartz.CGEventGetIntegerValueField(ev, USER_DATA) == MAGIC:
            return ev
        if kind in (KEY_DOWN, KEY_UP, FLAGS_CHANGED):
            return self._key(kind, ev)

        if not self.remote:
            if kind in MOVES:
                loc = Quartz.CGEventGetLocation(ev)
                if self.on_local_move(int(loc.x), int(loc.y)):
                    return None
            return ev

        field = Quartz.CGEventGetIntegerValueField
        if kind in MOVES:
            # the deltas keep coming even with the cursor frozen in the parking spot
            dx, dy = field(ev, DELTA_X), field(ev, DELTA_Y)
            if dx or dy:
                self.on_remote_event("move", dx=dx, dy=dy)
            loc = Quartz.CGEventGetLocation(ev)
            if abs(loc.x - self.park[0]) > 50 or abs(loc.y - self.park[1]) > 50:
                # the freeze didn't hold (it may not while another app is in front)
                _warp(*self.park, frozen=True)
        elif kind in DOWNS or kind in UPS:
            name = BUTTON_NAMES.get(field(ev, BUTTON_NUMBER))
            if name:
                self.on_remote_event("button", button=name, down=kind in DOWNS)
        elif kind == SCROLL:
            dx, dy = self._wheel(ev)
            if dx or dy:
                self.on_remote_event("scroll", dx=dx, dy=dy)
        return None

    def _wheel(self, ev) -> tuple[int, int]:
        field = Quartz.CGEventGetIntegerValueField
        if field(ev, SCROLL_CONTINUOUS):
            dy, self._rest[1] = notches(self._rest[1], field(ev, SCROLL_POINT_Y))
            dx, self._rest[0] = notches(self._rest[0], field(ev, SCROLL_POINT_X))
        else:
            dy, dx = field(ev, SCROLL_Y), field(ev, SCROLL_X)
        return -dx, dy

    def _key(self, kind, ev):
        code = Quartz.CGEventGetIntegerValueField(ev, KEYCODE)
        name = protocol_name(code)
        toggle = False
        if kind != FLAGS_CHANGED:
            down = kind == KEY_DOWN
        elif code in MOD_FLAGS:
            down = modifier_down(code, Quartz.CGEventGetFlags(ev))
        elif code == CAPS_LOCK:
            # one event per press, no separate release
            down, toggle = True, True
        else:
            # fn and friends, nothing to send
            return ev

        if code in MODIFIERS:
            if down:
                self.held.add(MODIFIERS[code])
            else:
                self.held.discard(MODIFIERS[code])
        # checked before anything else so it works even if the rest is broken
        if name == "esc" and down and PANIC <= self.held:
            self.on_panic()
            return None

        if not self.remote:
            return ev
        if name is not None:
            self.on_remote_event("key", key=name, down=down)
            if toggle:
                self.on_remote_event("key", key=name, down=False)
        # unknown keys are swallowed too, typing on the wrong machine is worse
        return None
