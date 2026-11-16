import socket
import sys
import threading

import pytest

# importing the window pulls in the tray, which wants a real display on linux
if sys.platform != "win32":
    pytest.skip("window only runs on windows for now", allow_module_level=True)

webapp = pytest.importorskip("moukey.webapp")
from moukey.backends import windows  # noqa: E402


def test_second_copy_cant_get_the_door(monkeypatch):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    monkeypatch.setattr(webapp, "SHOW_PORT", port)

    first = webapp.claim_door()
    assert first is not None
    try:
        assert webapp.claim_door() is None
        # and the second copy can still knock to bring the window back
        assert webapp.wake_running_copy()
    finally:
        first.close()


def test_wake_reaches_the_window(monkeypatch):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    monkeypatch.setattr(webapp, "SHOW_PORT", port)

    door = webapp.claim_door()
    shown = []
    got_it = threading.Event()
    webapp.listen_for_wake(door, lambda: (shown.append(1), got_it.set()))
    assert webapp.wake_running_copy()
    assert got_it.wait(2)
    assert shown == [1]


class FakeKey:
    def __init__(self, version):
        self.version = version

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_registry(monkeypatch, versions):
    def open_key(root, path):
        if path not in versions:
            raise OSError("not there")
        return FakeKey(versions[path])

    monkeypatch.setattr(windows.winreg, "OpenKey", open_key)
    monkeypatch.setattr(windows.winreg, "QueryValueEx", lambda key, name: (key.version, 1))


def test_finds_webview2(monkeypatch):
    fake_registry(monkeypatch, {rf"SOFTWARE\WOW6432Node\{windows.WEBVIEW2}": "131.0.2903.70"})
    assert windows.has_webview2()


def test_no_webview2(monkeypatch):
    fake_registry(monkeypatch, {})
    assert not windows.has_webview2()


def test_uninstalled_webview2_leaves_zero_version(monkeypatch):
    # uninstalling leaves the key behind with this version
    fake_registry(monkeypatch, {rf"SOFTWARE\{windows.WEBVIEW2}": "0.0.0.0"})
    assert not windows.has_webview2()


def test_no_window_without_webview2(monkeypatch):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    monkeypatch.setattr(webapp, "SHOW_PORT", port)
    monkeypatch.setattr(webapp, "setup_log", lambda: None)

    asked = []

    class Backend:
        def has_webview2(self):
            return False

        def ask_webview2(self):
            asked.append(1)

    monkeypatch.setattr(webapp.backends, "load", Backend)
    monkeypatch.setattr(webapp.webview, "create_window", lambda *a, **k: pytest.fail("opened"))
    webapp.main()
    assert asked == [1]
    # and the door is free again, so opening after installing works
    door = webapp.claim_door()
    assert door is not None
    door.close()


def test_api_has_no_public_fields():
    # pywebview exposes every public attribute to the page and walks into it
    api = webapp.Api()
    api._window = object()
    assert [name for name in vars(api) if not name.startswith("_")] == []
