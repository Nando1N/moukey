# the pure parts of the mac backend, they run on any OS. the parts that talk to quartz
# need a real mac and are skipped elsewhere
import sys
from types import SimpleNamespace

import pytest

from moukey.backends import macos
from moukey.backends.scancodes import CODES

on_mac = pytest.mark.skipif(sys.platform != "darwin", reason="needs macos")


def test_every_protocol_key_has_a_mac_key():
    assert set(macos.KEYCODES) == set(CODES)


def test_keycodes_round_trip():
    for name in CODES:
        assert macos.protocol_name(macos.mac_code(name)) == name


def test_mac_keycodes_are_unique():
    assert len(macos.KEY_NAMES) == len(macos.KEYCODES)


def test_some_known_positions():
    assert macos.mac_code("a") == 0x00  # kVK_ANSI_A
    assert macos.mac_code("c") == 0x08
    assert macos.mac_code("esc") == 0x35
    assert macos.mac_code("enter") == 0x24
    assert macos.mac_code("backspace") == 0x33
    assert macos.mac_code("delete") == 0x75
    assert macos.mac_code("up") == 0x7E
    assert macos.mac_code("f1") == 0x7A


def test_ctrl_from_windows_presses_command():
    assert macos.mac_code("ctrl_l") == 0x37  # kVK_Command
    assert macos.mac_code("ctrl_r") == 0x36  # kVK_RightCommand


def test_windows_key_from_windows_presses_control():
    assert macos.mac_code("meta_l") == 0x3B  # kVK_Control
    assert macos.mac_code("meta_r") == 0x3E


def test_command_here_goes_out_as_ctrl():
    assert macos.protocol_name(0x37) == "ctrl_l"
    assert macos.protocol_name(0x36) == "ctrl_r"


def test_control_here_goes_out_as_windows_key():
    assert macos.protocol_name(0x3B) == "meta_l"
    assert macos.protocol_name(0x3E) == "meta_r"


def test_option_is_alt_both_ways():
    assert macos.mac_code("alt_l") == 0x3A
    assert macos.protocol_name(0x3A) == "alt_l"
    assert macos.protocol_name(0x3D) == "alt_r"


def test_fn_and_unknown_keys_send_nothing():
    assert macos.protocol_name(0x3F) is None  # fn
    assert macos.mac_code("no_such_key") is None


def test_modifier_down_uses_the_side_bits():
    left_shift = macos.SHIFT | 0x02
    assert macos.modifier_down(0x38, left_shift)
    # right shift let go while the left one is still held
    assert not macos.modifier_down(0x3C, left_shift)
    assert not macos.modifier_down(0x38, 0)


def test_modifier_down_without_side_bits():
    assert macos.modifier_down(0x37, macos.COMMAND)
    assert not macos.modifier_down(0x37, macos.SHIFT)


def test_flags_for_held_modifiers():
    assert macos.flags_for(set()) == 0
    flags = macos.flags_for({0x37, 0x38})
    assert flags & macos.COMMAND and flags & macos.SHIFT
    assert not flags & macos.CONTROL


def test_panic_uses_physical_control_not_command():
    assert macos.MODIFIERS[0x3B] == "ctrl"
    assert 0x37 not in macos.MODIFIERS


def test_side_buttons():
    assert macos.BUTTON_NUMBERS["back"] == 3
    assert macos.BUTTON_NUMBERS["forward"] == 4
    assert macos.BUTTON_NAMES[3] == "back"
    assert macos.BUTTON_NAMES[4] == "forward"
    assert macos.button_types(3) == (macos.OTHER_DOWN, macos.OTHER_UP)
    assert macos.button_types(0) == (macos.LEFT_DOWN, macos.LEFT_UP)


def test_every_protocol_button_maps():
    from moukey.protocol import BUTTONS

    assert set(macos.BUTTON_NUMBERS) == BUTTONS


def test_moving_with_a_button_down_is_a_drag():
    assert macos.move_type(set()) == (macos.MOVED, 0)
    assert macos.move_type({0}) == (macos.LEFT_DRAGGED, 0)
    assert macos.move_type({1}) == (macos.RIGHT_DRAGGED, 1)
    assert macos.move_type({3}) == (macos.OTHER_DRAGGED, 3)


MAIN = (0, 0, 1440, 900)
LEFT = (-1920, -180, 1920, 1080)  # bigger screen on the left, sticking out above
ABOVE = (0, -1080, 1920, 1080)


def test_main_display_first_and_negative_coords_kept():
    found = [(7, (-1920.0, -180.0, 1920.0, 1080.0)), (1, (0.0, 0.0, 1440.0, 900.0))]
    assert macos.arrange(found, 1) == [MAIN, LEFT]


def test_display_above_main():
    found = [(2, (0.0, -1080.0, 1920.0, 1080.0)), (1, (0.0, 0.0, 1440.0, 900.0))]
    assert macos.arrange(found, 1) == [MAIN, ABOVE]


def test_mirrored_displays_count_once():
    found = [(1, (0.0, 0.0, 1440.0, 900.0)), (2, (0.0, 0.0, 1440.0, 900.0))]
    assert macos.arrange(found, 1) == [MAIN]


def test_clamp_keeps_points_on_a_screen():
    screens = [MAIN, LEFT, ABOVE]
    assert macos.clamp(screens, -100, -150, (0, 0)) == (-100, -150)
    assert macos.clamp(screens, 100, -500, (0, 0)) == (100, -500)
    # past the right edge of main
    assert macos.clamp(screens, 2000, 100, (1400, 100)) == (1439, 100)
    # below main, coming from main
    assert macos.clamp(screens, 50, 950, (50, 890)) == (50, 899)
    # off the left screen's far edge
    assert macos.clamp(screens, -2500, 0, (-1900, 0)) == (-1920, 0)


def test_double_click_count():
    first = macos.click_count(None, 0, 10.0, (5, 5))
    assert first == 1
    second = macos.click_count((0, 10.0, (5, 5), 1), 0, 10.2, (6, 5))
    assert second == 2
    # too slow, too far or another button starts over
    assert macos.click_count((0, 10.0, (5, 5), 1), 0, 11.0, (5, 5)) == 1
    assert macos.click_count((0, 10.0, (5, 5), 1), 0, 10.2, (50, 5)) == 1
    assert macos.click_count((0, 10.0, (5, 5), 1), 1, 10.2, (5, 5)) == 1


def test_trackpad_scroll_adds_up_to_notches():
    n, rest = macos.notches(0, 15)
    assert n == 0
    n, rest = macos.notches(rest, 30)
    assert n == 1 and rest == 5
    n, rest = macos.notches(0, -85)
    assert n == -2 and rest == -5


def fake_quartz(fields, flags=0):
    return SimpleNamespace(
        CGEventGetIntegerValueField=lambda ev, f: fields.get(f, 0),
        CGEventGetFlags=lambda ev: flags,
        CGEventGetLocation=lambda ev: SimpleNamespace(x=720.0, y=450.0),
    )


@pytest.fixture
def grabbed(monkeypatch):
    monkeypatch.setattr(macos, "monitors", lambda: [MAIN])
    sent = []
    panics = []
    cap = macos.Capture(
        lambda x, y: False, lambda kind, **kw: sent.append((kind, kw)), lambda: panics.append(1)
    )
    cap.remote = True
    return cap, sent, panics


def feed(monkeypatch, cap, kind, fields, flags=0):
    monkeypatch.setattr(macos, "Quartz", fake_quartz(fields, flags))
    return cap._on_event(None, kind, object(), None)


def test_side_buttons_go_to_the_other_computer(monkeypatch, grabbed):
    cap, sent, _ = grabbed
    assert feed(monkeypatch, cap, macos.OTHER_DOWN, {macos.BUTTON_NUMBER: 3}) is None
    feed(monkeypatch, cap, macos.OTHER_UP, {macos.BUTTON_NUMBER: 3})
    feed(monkeypatch, cap, macos.OTHER_DOWN, {macos.BUTTON_NUMBER: 4})
    assert sent == [
        ("button", {"button": "back", "down": True}),
        ("button", {"button": "back", "down": False}),
        ("button", {"button": "forward", "down": True}),
    ]


def test_command_c_goes_out_as_ctrl_c(monkeypatch, grabbed):
    cap, sent, _ = grabbed
    cmd = macos.COMMAND | 0x08
    feed(monkeypatch, cap, macos.FLAGS_CHANGED, {macos.KEYCODE: 0x37}, cmd)
    feed(monkeypatch, cap, macos.KEY_DOWN, {macos.KEYCODE: 0x08}, cmd)
    feed(monkeypatch, cap, macos.KEY_UP, {macos.KEYCODE: 0x08}, cmd)
    feed(monkeypatch, cap, macos.FLAGS_CHANGED, {macos.KEYCODE: 0x37}, 0)
    assert sent == [
        ("key", {"key": "ctrl_l", "down": True}),
        ("key", {"key": "c", "down": True}),
        ("key", {"key": "c", "down": False}),
        ("key", {"key": "ctrl_l", "down": False}),
    ]


def test_our_own_events_pass_through(monkeypatch, grabbed):
    cap, sent, _ = grabbed
    ev = feed(monkeypatch, cap, macos.KEY_DOWN, {macos.KEYCODE: 0x08, macos.USER_DATA: macos.MAGIC})
    assert ev is not None
    assert sent == []


def test_nothing_is_swallowed_when_not_grabbed(monkeypatch, grabbed):
    cap, sent, _ = grabbed
    cap.remote = False
    assert feed(monkeypatch, cap, macos.KEY_DOWN, {macos.KEYCODE: 0x08}) is not None
    assert feed(monkeypatch, cap, macos.OTHER_DOWN, {macos.BUTTON_NUMBER: 3}) is not None
    assert sent == []


def test_moves_send_the_raw_deltas(monkeypatch, grabbed):
    cap, sent, _ = grabbed
    assert feed(monkeypatch, cap, macos.MOVED, {macos.DELTA_X: 5, macos.DELTA_Y: -2}) is None
    assert sent == [("move", {"dx": 5, "dy": -2})]


def test_panic_shortcut(monkeypatch, grabbed):
    cap, sent, panics = grabbed
    held = macos.CONTROL | 0x01 | macos.OPTION | 0x20 | macos.SHIFT | 0x02
    for code in (0x3B, 0x3A, 0x38):
        feed(monkeypatch, cap, macos.FLAGS_CHANGED, {macos.KEYCODE: code}, held)
    assert feed(monkeypatch, cap, macos.KEY_DOWN, {macos.KEYCODE: 0x35}, held) is None
    assert panics == [1]


def test_caps_lock_is_a_full_press(monkeypatch, grabbed):
    cap, sent, _ = grabbed
    feed(monkeypatch, cap, macos.FLAGS_CHANGED, {macos.KEYCODE: 0x39}, 0x10000)
    assert sent == [
        ("key", {"key": "caps_lock", "down": True}),
        ("key", {"key": "caps_lock", "down": False}),
    ]


@on_mac
def test_monitors_on_a_real_mac():
    screens = macos.monitors()
    assert screens
    x, y, w, h = screens[0]
    assert (x, y) == (0, 0) and w > 0 and h > 0


@on_mac
def test_clipboard_counter_on_a_real_mac():
    from moukey.backends import macos_clip

    assert isinstance(macos_clip.clip_seq(), int)
