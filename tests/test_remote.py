from moukey.clipboard import Clipboard
from moukey.protocol import decode, encode
from moukey.remote import run_receiver


def quiet_clip(board=None):
    board = board if board is not None else {"text": ""}
    return Clipboard(lambda: board["text"], lambda t: board.update(text=t))


def test_clipboard_is_applied_even_without_the_mouse():
    board = {"text": ""}
    ch = FakeChannel([("clipboard", {"text": "senha do wifi"})])
    run_receiver(ch, FakeScreen(), quiet_clip(board))
    assert board["text"] == "senha do wifi"
    assert ch.sent == []


class FakeChannel:
    def __init__(self, incoming):
        self.incoming = [encode(kind, **fields) for kind, fields in incoming]
        self.sent = []

    def recv(self):
        if not self.incoming:
            raise ConnectionError
        return self.incoming.pop(0)

    def send(self, data):
        self.sent.append(decode(data))


class FakeScreen:
    def __init__(self, w=1366, h=768):
        self.w, self.h = w, h
        self.x, self.y = 0, 0
        self.calls = []

    def screen_size(self):
        return self.w, self.h

    def position(self):
        return self.x, self.y

    def move_to(self, x, y):
        self.x, self.y = x, y

    def move(self, dx, dy):
        # clamp like a real screen does
        self.x = min(max(self.x + dx, 0), self.w - 1)
        self.y = min(max(self.y + dy, 0), self.h - 1)

    def button(self, name, down):
        self.calls.append(("button", name, down))

    def scroll(self, dx, dy):
        self.calls.append(("scroll", dx, dy))

    def key(self, name, down):
        self.calls.append(("key", name, down))


def test_enter_places_cursor_on_the_edge():
    screen = FakeScreen()
    run_receiver(FakeChannel([("enter", {"at": 0.5, "edge": "left"})]), screen, quiet_clip())
    assert (screen.x, screen.y) == (2, 384)


def test_clicks_and_scroll_only_while_controlled():
    screen = FakeScreen()
    ch = FakeChannel(
        [
            ("button", {"button": "left", "down": True}),
            ("enter", {"at": 0.0, "edge": "left"}),
            ("button", {"button": "left", "down": True}),
            ("scroll", {"dx": 0, "dy": -1}),
        ]
    )
    run_receiver(ch, screen, quiet_clip())
    # the last one is the held button being let go when the connection ends
    assert screen.calls == [
        ("button", "left", True),
        ("scroll", 0, -1),
        ("button", "left", False),
    ]


def test_keys_are_typed_while_controlled():
    screen = FakeScreen()
    ch = FakeChannel(
        [
            ("enter", {"at": 0.5, "edge": "left"}),
            ("key", {"key": "ctrl_l", "down": True}),
            ("key", {"key": "c", "down": True}),
            ("key", {"key": "c", "down": False}),
            ("key", {"key": "ctrl_l", "down": False}),
        ]
    )
    run_receiver(ch, screen, quiet_clip())
    assert screen.calls == [
        ("key", "ctrl_l", True),
        ("key", "c", True),
        ("key", "c", False),
        ("key", "ctrl_l", False),
    ]


def test_held_keys_are_released_when_control_leaves():
    screen = FakeScreen()
    ch = FakeChannel(
        [
            ("enter", {"at": 0.5, "edge": "left"}),
            ("key", {"key": "shift_l", "down": True}),
            ("button", {"button": "left", "down": True}),
            ("leave", {"at": 0.5}),
        ]
    )
    run_receiver(ch, screen, quiet_clip())
    assert ("key", "shift_l", False) in screen.calls
    assert ("button", "left", False) in screen.calls


def test_held_keys_are_released_when_connection_drops():
    screen = FakeScreen()
    ch = FakeChannel(
        [("enter", {"at": 0.5, "edge": "left"}), ("key", {"key": "alt_l", "down": True})]
    )
    run_receiver(ch, screen, quiet_clip())
    assert screen.calls[-1] == ("key", "alt_l", False)


def test_pushing_back_through_the_edge_gives_control_back():
    screen = FakeScreen()
    ch = FakeChannel(
        [
            ("enter", {"at": 0.25, "edge": "left"}),
            ("move", {"dx": 50, "dy": 0}),
            ("move", {"dx": -60, "dy": 0}),
            ("move", {"dx": -5, "dy": 0}),
            ("move", {"dx": 100, "dy": 0}),  # arrives late, must be ignored
        ]
    )
    run_receiver(ch, screen, quiet_clip())
    assert [m["t"] for m in ch.sent] == ["leave"]
    assert abs(ch.sent[0]["at"] - 0.25) < 0.01
    assert screen.x == 0
