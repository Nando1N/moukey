# runs against a real x server. in ci that's xvfb (see .github/workflows/testes.yml),
# anywhere else without one these tests are skipped
import os
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux") or not os.environ.get("DISPLAY"),
    reason="needs linux with an x server",
)


@pytest.fixture
def x11():
    from moukey.backends import linux_x11

    return linux_x11


def test_monitors(x11):
    screens = x11.monitors()
    assert screens
    x, y, w, h = screens[0]
    assert w > 0 and h > 0


def test_cursor_goes_where_we_say(x11):
    x11.move_to(300, 200)
    assert x11.position() == (300, 200)
    x11.move(10, -5)
    assert x11.position() == (310, 195)


def test_keys_and_buttons_dont_blow_up(x11):
    x11.key("a", True)
    x11.key("a", False)
    x11.key("nao-existe", True)
    x11.button("left", True)
    x11.button("left", False)
    x11.scroll(0, -1)


def test_capture_notices_the_cursor_moving(x11):
    seen = []
    cap = x11.Capture(lambda x, y: seen.append((x, y)) or False, lambda *a, **k: None, lambda: None)
    cap.start()
    try:
        time.sleep(0.3)
        x11.move_to(50, 60)
        x11.move(5, 0)
        for _ in range(50):
            if seen:
                break
            time.sleep(0.05)
        # pynput moves through xtest too, so the record loop sees it like a real mouse
        assert seen
    finally:
        cap.stop()


def test_grab_parks_the_cursor_and_release_brings_it_back(x11):
    moves = []
    cap = x11.Capture(lambda x, y: False, lambda kind, **f: moves.append((kind, f)), lambda: None)
    cap.start()
    try:
        time.sleep(0.3)
        cap.grab()
        assert cap.remote
        assert x11.position() == cap.park
        cap.release(100, 100)
        assert not cap.remote
        assert x11.position() == (100, 100)
    finally:
        cap.stop()
