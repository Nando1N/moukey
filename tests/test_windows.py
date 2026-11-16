import sys
from types import SimpleNamespace

import pytest

if sys.platform != "win32":
    pytest.skip("windows backend", allow_module_level=True)

from moukey.backends import windows  # noqa: E402


def side_click(which, down):
    msg = windows.WM_XBUTTONDOWN if down else windows.WM_XBUTTONUP
    return msg, SimpleNamespace(flags=0, mouseData=which << 16, pt=SimpleNamespace(x=0, y=0))


@pytest.fixture
def grabbed(monkeypatch):
    sent = []
    cap = windows.Capture(lambda x, y: False, lambda kind, **kw: sent.append((kind, kw)), None)
    monkeypatch.setattr(cap.listener, "suppress_event", lambda: None)
    cap.remote = True
    return cap, sent


def test_side_buttons_go_to_the_other_computer(grabbed):
    cap, sent = grabbed
    cap._filter(*side_click(1, True))
    cap._filter(*side_click(1, False))
    cap._filter(*side_click(2, True))
    assert sent == [
        ("button", {"button": "back", "down": True}),
        ("button", {"button": "back", "down": False}),
        ("button", {"button": "forward", "down": True}),
    ]


def test_side_buttons_stay_local_when_not_grabbed(grabbed):
    cap, sent = grabbed
    cap.remote = False
    assert cap._filter(*side_click(1, True)) is True
    assert sent == []


def test_every_button_name_can_be_pressed():
    from moukey.protocol import BUTTONS

    assert BUTTONS <= set(windows.PYNPUT_BUTTONS)
