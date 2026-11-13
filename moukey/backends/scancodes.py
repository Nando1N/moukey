# physical key positions as PC set 1 scan codes. extended keys carry the 0xE0
# prefix in the high byte. we send positions, not characters, so the receiving
# side applies its own layout and shortcuts like ctrl+c keep working.
# linux evdev codes match the non extended ones, which helps later

_ROWS = {
    0x01: "esc",
    0x0E: "backspace",
    0x0F: "tab",
    0x1C: "enter",
    0x1D: "ctrl_l",
    0x2A: "shift_l",
    0x36: "shift_r",
    0x38: "alt_l",
    0x39: "space",
    0x3A: "caps_lock",
    0x46: "scroll_lock",
    0x0C: "minus",
    0x0D: "equal",
    0x1A: "bracket_left",
    0x1B: "bracket_right",
    0x27: "semicolon",
    0x28: "quote",
    0x29: "grave",
    0x2B: "backslash",
    0x33: "comma",
    0x34: "period",
    0x35: "slash",
    0x56: "intl_backslash",  # extra key left of z on abnt2 and iso keyboards
    0x73: "intl_ro",  # the /? key next to right shift on abnt2
    0x37: "kp_multiply",
    0x4A: "kp_minus",
    0x4E: "kp_plus",
    0x53: "kp_decimal",
    0x7E: "kp_comma",
    0xE01C: "kp_enter",
    0xE035: "kp_divide",
    0xE045: "num_lock",
    0xE01D: "ctrl_r",
    0xE038: "alt_r",
    0xE037: "print_screen",
    0xE047: "home",
    0xE048: "up",
    0xE049: "page_up",
    0xE04B: "left",
    0xE04D: "right",
    0xE04F: "end",
    0xE050: "down",
    0xE051: "page_down",
    0xE052: "insert",
    0xE053: "delete",
    0xE05B: "meta_l",
    0xE05C: "meta_r",
    0xE05D: "menu",
}

_letters = {0x10: "qwertyuiop", 0x1E: "asdfghjkl", 0x2C: "zxcvbnm"}
for start, row in _letters.items():
    for i, ch in enumerate(row):
        _ROWS[start + i] = ch

for i, ch in enumerate("1234567890"):
    _ROWS[0x02 + i] = ch

for i in range(10):
    _ROWS[0x3B + i] = f"f{i + 1}"
_ROWS[0x57] = "f11"
_ROWS[0x58] = "f12"

for n, code in enumerate((0x52, 0x4F, 0x50, 0x51, 0x4B, 0x4C, 0x4D, 0x47, 0x48, 0x49)):
    _ROWS[code] = f"kp_{n}"

NAMES: dict[int, str] = dict(_ROWS)
CODES: dict[str, int] = {name: code for code, name in NAMES.items()}

# linux works with evdev codes (X keycodes are those + 8). the plain set 1 codes are the
# same numbers, the extended ones and two abnt2 keys need a lookup
_EXTENDED_TO_EVDEV = {
    0xE01C: 96,
    0xE01D: 97,
    0xE035: 98,
    0xE037: 99,
    0xE038: 100,
    0xE045: 69,
    0xE047: 102,
    0xE048: 103,
    0xE049: 104,
    0xE04B: 105,
    0xE04D: 106,
    0xE04F: 107,
    0xE050: 108,
    0xE051: 109,
    0xE052: 110,
    0xE053: 111,
    0xE05B: 125,
    0xE05C: 126,
    0xE05D: 127,
}
_PLAIN_TO_EVDEV = {0x73: 89, 0x7E: 121}


def evdev_code(name: str) -> int | None:
    code = CODES.get(name)
    if code is None:
        return None
    if code > 0xFF:
        return _EXTENDED_TO_EVDEV.get(code)
    return _PLAIN_TO_EVDEV.get(code, code)


_NAME_BY_EVDEV = {evdev_code(name): name for name in CODES}


def name_for_evdev(code: int) -> str | None:
    return _NAME_BY_EVDEV.get(code)
