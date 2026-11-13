import socket
import threading

import pytest

webapp = pytest.importorskip("moukey.webapp")


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
