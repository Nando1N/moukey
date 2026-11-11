from ponte.protocol import decode, encode
from ponte.remote import run_receiver


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


def test_enter_places_cursor_on_the_edge():
    screen = FakeScreen()
    run_receiver(FakeChannel([("enter", {"y": 0.5, "edge": "left"})]), screen)
    assert (screen.x, screen.y) == (2, 384)


def test_clicks_and_scroll_only_while_controlled():
    screen = FakeScreen()
    ch = FakeChannel(
        [
            ("button", {"button": "left", "down": True}),
            ("enter", {"y": 0.0, "edge": "left"}),
            ("button", {"button": "left", "down": True}),
            ("scroll", {"dx": 0, "dy": -1}),
        ]
    )
    run_receiver(ch, screen)
    assert screen.calls == [("button", "left", True), ("scroll", 0, -1)]


def test_pushing_back_through_the_edge_gives_control_back():
    screen = FakeScreen()
    ch = FakeChannel(
        [
            ("enter", {"y": 0.25, "edge": "left"}),
            ("move", {"dx": 50, "dy": 0}),
            ("move", {"dx": -60, "dy": 0}),
            ("move", {"dx": -5, "dy": 0}),
            ("move", {"dx": 100, "dy": 0}),  # arrives late, must be ignored
        ]
    )
    run_receiver(ch, screen)
    assert [m["t"] for m in ch.sent] == ["leave"]
    assert abs(ch.sent[0]["y"] - 0.25) < 0.01
    assert screen.x == 0
